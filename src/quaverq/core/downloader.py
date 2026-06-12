"""音乐下载核心逻辑: 文件名清洗 + 流式下载器 (断点续传) + 标签嵌入.

下载产物是用户文档 (音频 + .lrc + 封面旁路文件 + 内嵌标签), 由
bridge.DownloadController 编排; 本模块不依赖 Qt (见本目录 README "模块边界").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .models import Song

if TYPE_CHECKING:
    import threading

logger = logging.getLogger(__name__)

# Windows 非法字符 \ / : * ? " < > | 与 C0 控制字符 (Linux 仅 / 与 NUL 非法,
# 取并集保证同一首歌在两平台产出同名文件)
_INVALID_CHARS_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# Windows 保留设备名 (整名命中时文件不可创建, 大小写不敏感)
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# 文件名主干字节上限: 常见文件系统单名 255 字节, 预留扩展名/旁路后缀余量
_MAX_FILENAME_BYTES = 200


def sanitize_filename(name: str, *, max_bytes: int = _MAX_FILENAME_BYTES) -> str:
    """把歌名/歌手名清洗为跨平台安全的文件名主干 (不含扩展名).

    规则: 非法字符替换 ``_``; 去首尾空格与尾部点 (Windows 限制); 按 UTF-8 字节
    截断且不切断多字节字符; 全空回退 ``untitled``; Windows 保留名加 ``_`` 前缀.
    """
    # 先 strip 原始输入: 首尾的控制字符/空白直接丢弃, 不留下替换出的 "_"
    cleaned = _INVALID_CHARS_RE.sub("_", str(name or "").strip())
    cleaned = cleaned.strip().rstrip(" .")

    encoded = cleaned.encode("utf-8")
    if len(encoded) > max_bytes:
        cleaned = encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip(" .")

    if not cleaned:
        return "untitled"
    if cleaned.upper() in _WINDOWS_RESERVED:
        return f"_{cleaned}"
    return cleaned


# vkey 音质标签 -> 落盘扩展名 (与 service._QUALITY_FILE 的 ext 列一致)
_QUALITY_EXTENSIONS = {
    "MASTER": "flac",
    "ATMOS_2": "flac",
    "FLAC": "flac",
    "MP3_320": "mp3",
    "OGG_192": "ogg",
    "MP3_128": "mp3",
}


def quality_extension(quality_label: str) -> str:
    """音质标签对应的文件扩展名 (不含点); 未知标签回退 mp3."""
    return _QUALITY_EXTENSIONS.get(quality_label, "mp3")


@dataclass
class DownloadTask:
    """一次下载任务的状态 (bridge 层 model 的行数据).

    status: pending → running → done / exists / failed / canceled.
    received/total 单位字节, total=0 表示长度未知.
    """

    song: Song
    quality_preference: str
    status: str = "pending"
    received: int = 0
    total: int = 0
    quality_label: str = ""  # 实际命中档位 (SongUrl.quality)
    dest_path: str = ""
    error: str = ""


# ------------------------------------------------------------------ 流式下载器

# stream=True 下 curl_cffi 把 float timeout 映射为 CONNECTTIMEOUT + LOW_SPEED_TIME
# (低于 1 B/s 持续 N 秒才断), 不是总超时 —— 大文件 (FLAC ~50MB) 慢网不会被切断.
_DOWNLOAD_TIMEOUT_SEC = 30


def embed_tags(
    audio_path: Path,
    *,
    title: str,
    artists: list[str],
    album: str = "",
    cover_path: Path | None = None,
) -> None:
    """把标题/歌手/专辑 (+ 可选封面) 嵌入音频标签; 按扩展名分发, 不识别的静默跳过.

    mp3 走 ID3v2 (不解析音频帧, 对任意字节文件可前置标签块); flac/ogg 要求合法
    容器头, 坏文件抛 mutagen 错误 —— 调用方按"非致命"处理. ogg 只写文字 tag
    (Vorbis 内嵌封面需 base64 METADATA_BLOCK_PICTURE, 复杂度收益比低, 不做).
    """
    audio_path = Path(audio_path)
    suffix = audio_path.suffix.lower()
    cover_bytes = b""
    if cover_path is not None and Path(cover_path).is_file():
        cover_bytes = Path(cover_path).read_bytes()

    if suffix == ".mp3":
        from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

        try:
            tags = ID3(audio_path)
        except ID3NoHeaderError:
            tags = ID3()
        if title:
            tags.add(TIT2(encoding=3, text=[title]))
        if artists:
            tags.add(TPE1(encoding=3, text=list(artists)))
        if album:
            tags.add(TALB(encoding=3, text=[album]))
        if cover_bytes:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))
        tags.save(audio_path)
    elif suffix == ".flac":
        from mutagen.flac import FLAC, Picture

        audio = FLAC(audio_path)
        if title:
            audio["title"] = [title]
        if artists:
            audio["artist"] = list(artists)
        if album:
            audio["album"] = [album]
        if cover_bytes:
            picture = Picture()
            picture.type = 3  # front cover
            picture.mime = "image/jpeg"
            picture.data = cover_bytes
            audio.clear_pictures()
            audio.add_picture(picture)
        audio.save()
    elif suffix == ".ogg":
        from mutagen.oggvorbis import OggVorbis

        audio = OggVorbis(audio_path)
        if title:
            audio["title"] = [title]
        if artists:
            audio["artist"] = list(artists)
        if album:
            audio["album"] = [album]
        audio.save()


def _total_from_content_range(value: str) -> int:
    """``Content-Range: bytes N-M/Total`` -> Total; 解析失败返 0."""
    try:
        return int(value.rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return 0


class DownloadError(RuntimeError):
    """下载失败 (HTTP 非 2xx / 传输异常)."""


class DownloadCanceled(Exception):
    """下载被调用方取消 (cancel 事件置位)."""


@dataclass
class Downloader:
    """同步流式下载器 (调用方放 ``asyncio.to_thread``).

    QQ CDN 有 JA3 指纹风控, 必须与 StreamProxy 同路: curl_cffi 官方浏览器
    TLS 指纹出网; 经 ``.part`` 临时文件写入、完成后原子改名, 中断保留
    ``.part`` 供下次断点续传 (Range).
    """

    impersonate: str = "chrome"
    timeout: float = _DOWNLOAD_TIMEOUT_SEC

    def download_file(
        self,
        url: str,
        dest: Path,
        *,
        progress_cb: Callable[[int, int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> None:
        """下载 ``url`` 到 ``dest``; ``progress_cb(received, total)`` 的 total=0 表示长度未知.

        断点续传: 已有非空 ``.part`` 时带 ``Range`` 请求, 服务器返 206 则从断点追加
        (received 从断点起算, total 为全量大小); 返 200 (不支持 Range) 重头写;
        返 416 (断点无效, 远端文件已变) 丢弃 ``.part`` 重下. 取消 / 失败均**保留**
        ``.part`` 供下次续传. ``cancel`` 在 chunk 间检查, 置位抛 :class:`DownloadCanceled`;
        其余非 2xx 抛 :class:`DownloadError`.
        """
        from curl_cffi import requests as creq

        if cancel is not None and cancel.is_set():
            raise DownloadCanceled

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")

        resume_from = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from > 0 else {}

        resp = creq.get(
            url,
            headers=headers,
            impersonate=self.impersonate,
            stream=True,
            timeout=self.timeout,
        )
        if resp.status_code == 416:
            # 断点超出远端文件长度 (文件已变更): 丢弃后重下.
            # 第二次请求不带 Range, 不可能再 416, 无递归风险.
            resp.close()
            part.unlink(missing_ok=True)
            self.download_file(url, dest, progress_cb=progress_cb, cancel=cancel)
            return
        try:
            if resp.status_code not in (200, 206):
                raise DownloadError(f"HTTP {resp.status_code}")

            if resp.status_code == 206 and resume_from > 0:
                mode = "ab"
                received = resume_from
                total = _total_from_content_range(resp.headers.get("Content-Range", "")) or (
                    resume_from + int(resp.headers.get("Content-Length") or 0)
                )
            else:
                # 200: 服务器忽略 Range (或本来就没带断点), 重头写
                mode = "wb"
                received = 0
                total = int(resp.headers.get("Content-Length") or 0)

            with part.open(mode) as fh:
                # chunk 大小由 curl 内部缓冲决定 (iter_content 的 size 参数在
                # curl_cffi 中无效且会刷 CurlCffiWarning)
                for chunk in resp.iter_content():
                    if cancel is not None and cancel.is_set():
                        raise DownloadCanceled  # 保留 .part 供续传
                    if not chunk:
                        continue
                    fh.write(chunk)
                    received += len(chunk)
                    if progress_cb is not None:
                        progress_cb(received, total)
            part.replace(dest)
        finally:
            resp.close()
