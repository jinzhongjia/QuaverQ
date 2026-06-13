"""批量歌词审计: 拉取 100 首歌的歌词, 检查翻译匹配 / 字符过滤问题.

串行拉取, 每首歌间隔 1.5s 防风控.

跑法: uv run python scripts/debug_lyric_audit.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from quaverq.core.lyric import parse_lrc, parse_qrc
from quaverq.core.service import QuaverService

DELAY_SEC = 1.5
TARGET = 100

# 检测特殊字符 (非常规歌词内容)
_SPECIAL_CHAR_RE = re.compile(r"[<>&\x00-\x08\x0b\x0c\x0e-\x1f]")
# 检测 HTML 残留
_HTML_RE = re.compile(r"<[^>]+>")
# 检测 QRC XML 残留
_XML_RE = re.compile(r'<\?xml|<QrcInfos|<Lyric_\d|LyricContent=')
# 检测 "//" 分隔符残留
_DOUBLE_SLASH_RE = re.compile(r"^//\s*$")


async def main() -> None:
    svc = QuaverService()
    cred = svc.load_cached_credential_sync()
    if cred is None:
        print("ERROR: no cached credential; 请先在 app 内扫码登录")
        return

    await svc.connect()
    svc.set_credential_sync(cred)
    print(f"ct={svc._ct_value}, 开始拉取排行榜歌单...")

    # 拉两个热门排行榜凑 100 首
    song_mids: list[tuple[str, str]] = []  # (mid, title)

    # 巅峰榜热歌 (tid=26)
    try:
        top = await svc.get_top_detail(26, limit=60)
        for s in top.songs:
            if s.mid and len(song_mids) < TARGET:
                artist = s.singers[0].name if s.singers else "?"
                song_mids.append((s.mid, f"{s.name} - {artist}"))
        print(f"  巅峰热歌榜: {len(top.songs)} 首")
    except Exception as e:
        print(f"  巅峰热歌榜拉取失败: {e}")

    await asyncio.sleep(DELAY_SEC)

    # 飙升榜 (tid=62) 补足
    if len(song_mids) < TARGET:
        try:
            top2 = await svc.get_top_detail(62, limit=60)
            for s in top2.songs:
                if s.mid and len(song_mids) < TARGET:
                    existing = {m for m, _ in song_mids}
                    if s.mid not in existing:
                        artist = s.singers[0].name if s.singers else "?"
                        song_mids.append((s.mid, f"{s.name} - {artist}"))
            print(f"  飙升榜: {len(top2.songs)} 首")
        except Exception as e:
            print(f"  飙升榜拉取失败: {e}")

    print(f"\n共 {len(song_mids)} 首待审计\n")
    print("=" * 80)

    # 统计
    total = 0
    has_lyric = 0
    has_trans = 0
    has_words = 0  # 逐字 (QRC)

    issues: list[str] = []

    for i, (mid, title) in enumerate(song_mids):
        total += 1
        prefix = f"[{i+1:3d}/{len(song_mids)}]"

        try:
            ly = await svc.get_lyric(mid, with_translation=True)
        except Exception as e:
            issues.append(f"{prefix} {title} | FETCH_ERROR: {e}")
            print(f"{prefix} {title} | ERROR: {e}")
            await asyncio.sleep(DELAY_SEC)
            continue

        if not ly.lines:
            print(f"{prefix} {title} | 无歌词 (纯音乐?)")
            await asyncio.sleep(DELAY_SEC)
            continue

        has_lyric += 1
        line_count = len(ly.lines)
        word_lines = sum(1 for ln in ly.lines if ln.words)
        trans_lines = sum(1 for ln in ly.lines if ln.translation)

        if word_lines > 0:
            has_words += 1
        if ly.has_translation:
            has_trans += 1

        # ---- 检查项 ----

        # 1. 翻译标记 vs 实际翻译行数
        if ly.has_translation and trans_lines == 0:
            issues.append(f"{prefix} {title} | TRANS_FLAG_MISMATCH: has_translation=True 但 0 行有翻译")

        if ly.has_translation and trans_lines > 0:
            match_rate = trans_lines / line_count * 100
            if match_rate < 50:
                issues.append(
                    f"{prefix} {title} | LOW_TRANS_MATCH: "
                    f"{trans_lines}/{line_count} 行匹配 ({match_rate:.0f}%)"
                )

        # 2. 歌词文本中的异常字符
        for j, ln in enumerate(ly.lines):
            if _HTML_RE.search(ln.text):
                issues.append(f"{prefix} {title} | HTML_IN_TEXT L{j}: {ln.text[:60]}")
                break
            if _XML_RE.search(ln.text):
                issues.append(f"{prefix} {title} | XML_IN_TEXT L{j}: {ln.text[:60]}")
                break
            if _SPECIAL_CHAR_RE.search(ln.text):
                issues.append(
                    f"{prefix} {title} | SPECIAL_CHAR L{j}: "
                    f"{repr(ln.text[:60])}"
                )
                break
            if _DOUBLE_SLASH_RE.match(ln.text):
                issues.append(f"{prefix} {title} | DOUBLE_SLASH L{j}: '//' 未被过滤")
                break

        # 3. 翻译文本异常字符
        for j, ln in enumerate(ly.lines):
            if ln.translation:
                if _HTML_RE.search(ln.translation):
                    issues.append(f"{prefix} {title} | HTML_IN_TRANS L{j}: {ln.translation[:60]}")
                    break
                if _SPECIAL_CHAR_RE.search(ln.translation):
                    issues.append(
                        f"{prefix} {title} | SPECIAL_CHAR_TRANS L{j}: "
                        f"{repr(ln.translation[:60])}"
                    )
                    break

        # 4. 逐字歌词: 文本拼接 vs 行文本一致性
        for j, ln in enumerate(ly.lines):
            if ln.words:
                joined = "".join(w.text for w in ln.words)
                if joined != ln.text:
                    issues.append(
                        f"{prefix} {title} | WORD_JOIN_MISMATCH L{j}: "
                        f"'{joined[:40]}' != '{ln.text[:40]}'"
                    )
                    break

        # 5. 时间戳单调递增
        for j in range(1, len(ly.lines)):
            if ly.lines[j].timestamp_ms < ly.lines[j - 1].timestamp_ms:
                issues.append(
                    f"{prefix} {title} | TS_NOT_MONOTONIC L{j}: "
                    f"{ly.lines[j-1].timestamp_ms} -> {ly.lines[j].timestamp_ms}"
                )
                break

        # 6. 空文本行 (非间奏) 检查: 有 words 但拼出空文本
        empty_text_with_words = sum(1 for ln in ly.lines if ln.words and not ln.text.strip())
        if empty_text_with_words > 0:
            issues.append(f"{prefix} {title} | EMPTY_TEXT_WITH_WORDS: {empty_text_with_words} 行")

        # 输出摘要
        flags = []
        if word_lines > 0:
            flags.append("QRC")
        if ly.has_translation:
            flags.append(f"翻译{trans_lines}/{line_count}")
        status = " ".join(flags) if flags else "LRC"
        print(f"{prefix} {title} | {line_count}行 {status}")

        await asyncio.sleep(DELAY_SEC)

    # ---- 汇总报告 ----
    print("\n" + "=" * 80)
    print("汇总报告")
    print("=" * 80)
    print(f"总计: {total} 首")
    print(f"有歌词: {has_lyric}")
    print(f"有逐字(QRC): {has_words}")
    print(f"有翻译: {has_trans}")
    print()

    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for iss in issues:
            print(f"  !! {iss}")
    else:
        print("未发现问题")

    await svc.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
