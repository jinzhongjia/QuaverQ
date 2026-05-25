"""QQ 音乐服务层 (qqmusic-api-python 0.6.1).

关键设计:
- 用 0.6.x Client 类 + pydantic 返回模型
- get_song_url 走 **bypass 路径**: 自拼 musicu.fcg JSON, 不经过库的 get_song_urls,
  避免 0.6 默认 ct=11 触发地区版权风控.
- ct 在 service 启动时从合法白名单 random.choice 选一个, 实例生命周期固定,
  既避免高风险值 (1/3/4/11/18/23/27/46), 也防止固定值被未来收紧.

ct 风控背景见 findings.md 第三节; 整体落地节奏见 docs/design.md §14.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from qqmusic_api import Client, Credential
from qqmusic_api.models.login import QRCodeLoginEvents, QRLoginType
from qqmusic_api.modules.search import SearchType
from qqmusic_api.modules.singer import TabType

from .cache import Cache
from .lyric import parse_lrc
from .models import (
    Album,
    ArtistDetail,
    Lyric,
    LyricLine,
    Playlist,
    Singer,
    Song,
    SongUrl,
    TopList,
)

if TYPE_CHECKING:
    from collections.abc import Callable as _Cb  # noqa: F401

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers


def _cover_url(album_mid: str, size: int = 300) -> str:
    if not album_mid:
        return ""
    return f"https://y.qq.com/music/photo_new/T002R{size}x{size}M000{album_mid}.jpg"


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(s: str | None, *, max_len: int = 120) -> str:
    """去 HTML 标签 + 折空白 + 截断 (UI 显示用的文本规整)."""
    if not s:
        return ""
    txt = _HTML_TAG_RE.sub(" ", s)        # <br>/<em> 等 → 空格
    txt = _WS_RE.sub(" ", txt).strip()    # 多空白 → 单空格
    if len(txt) > max_len:
        txt = txt[:max_len].rstrip() + "…"
    return txt


def _credential_from_dict(d: dict[str, Any]) -> Credential:
    """从 dict 构造 Credential (0.6 是 pydantic, 用 model_validate; 容忍多余字段)."""
    # pydantic v2 默认拒绝 extra; 这里手动过滤已知字段
    known = set(Credential.model_fields.keys())
    base = {k: v for k, v in d.items() if k in known}
    return Credential.model_validate(base)


def _credential_to_dict(c: Credential) -> dict[str, Any]:
    return c.model_dump(mode="json")


# ---------------------------------------------------------------- service


@dataclass
class QuaverService:
    """QQ 音乐 API 门面层 (0.6.1, 含 vkey bypass).

    用法:
        svc = QuaverService(cache=cache)
        await svc.connect()
        svc.set_credential_sync(cached_cred)
        url = await svc.get_song_url(song, quality_preference="high")
    """

    credential: Credential | None = None
    cache: Cache | None = None
    on_qrcode: Callable[[bytes, str], None] | None = None

    _client: Client | None = field(default=None, init=False, repr=False)
    # bypass 路径用的 ct 值, 实例生命周期内固定 (见 _SAFE_CT_VALUES)
    _ct_value: int = field(default=0, init=False, repr=False)
    # 实例级内存 cache: 短期 ad-hoc 数据 (recommend 等) 不适合 SQLite TTL 表
    # key → (timestamp, value); 重启失效
    _memo: dict[str, tuple[float, Any]] = field(
        default_factory=dict, init=False, repr=False
    )

    # 内存 cache 默认 TTL: 推荐数据每天/每小时换换, 10 分钟够
    _MEMO_TTL_SEC = 600

    # ------------------------------------------------------------------
    # bypass / 反风控
    # ------------------------------------------------------------------

    # 合法 ct 候选池 (排除 findings.md 列出的风控值 1/3/4/11/18/23/27/46)
    # 反风控原则: 1) 不固定一个值 2) 避开"客户端热门"值
    _SAFE_CT_VALUES = (
        2, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17,
        19, 20, 21, 22, 24, 25, 26, 28, 29, 30,
    )

    # vkey 接口 filename 前缀 + 扩展名 (mid 双拼)
    # 见 findings 第五节: filename=`{prefix}{mid}{mid}.{ext}`
    _QUALITY_FILE: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "FLAC":    ("F000", "flac"),
            "MP3_320": ("M800", "mp3"),
            "OGG_192": ("O600", "ogg"),
            "MP3_128": ("M500", "mp3"),
        },
        init=False, repr=False,
    )

    # 各档音质偏好的降级顺序 (字符串 label, 不依赖 qqmusic SongFileType)
    _QUALITY_PROFILES = {
        "high":     ("FLAC", "MP3_320", "OGG_192", "MP3_128"),
        "balanced": ("MP3_320", "OGG_192", "MP3_128"),
        "standard": ("MP3_128", "OGG_192"),
    }
    _DEFAULT_QUALITY = "balanced"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "QuaverService":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """初始化 Client + 随机选定本次会话用的 ct 值."""
        self._client = Client(credential=self.credential)
        # 反风控: 每次启动从合法池中随机, 但实例生命周期内固定一个
        self._ct_value = random.choice(self._SAFE_CT_VALUES)
        logger.info(
            "QQMusic 服务初始化 (qqmusic-api 0.6.1, vkey bypass ct=%d)",
            self._ct_value,
        )

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.exception("close Client 异常")
            self._client = None
        logger.info("QQMusic 服务断开")

    @property
    def client(self) -> Client:
        if self._client is None:
            raise RuntimeError("服务未连接, 请先 await connect()")
        return self._client

    @property
    def is_authenticated(self) -> bool:
        c = self._effective_credential()
        return c is not None and bool(c.musickey)

    def _effective_credential(self) -> Credential | None:
        if self._client is not None:
            return self._client.credential
        return self.credential

    async def get_credential(self) -> Credential | None:
        return self._effective_credential()

    async def set_credential(self, cred: Credential | None) -> None:
        self._assign_credential(cred)

    def set_credential_sync(self, cred: Credential | None) -> None:
        self._assign_credential(cred)

    def _assign_credential(self, cred: Credential | None) -> None:
        """None → 空 Credential (避免 0.6 内部 cred.musicid 访问 None 报错)."""
        self.credential = cred
        if self._client is not None:
            self._client.credential = cred if cred is not None else Credential()

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------

    async def login_by_qrcode(
        self, login_type: QRLoginType = QRLoginType.QQ
    ) -> bool:
        if self._client is None:
            raise RuntimeError("服务未连接")
        qr = await self._client.login.get_qrcode(login_type)
        if self.on_qrcode:
            self.on_qrcode(qr.data, qr.qr_type.name.lower())
        logger.info("二维码已获取 (类型: %s)", qr.qr_type.name)

        import anyio

        while True:
            result = await self._client.login.check_qrcode(qr)
            event = result.event
            if event == QRCodeLoginEvents.DONE:
                assert result.credential is not None
                self.credential = result.credential
                self._assign_credential(result.credential)
                logger.info("登录成功")
                return True
            if event == QRCodeLoginEvents.TIMEOUT:
                logger.warning("二维码已过期")
                return False
            if event == QRCodeLoginEvents.REFUSE:
                logger.warning("用户拒绝授权")
                return False
            if event == QRCodeLoginEvents.SCAN:
                logger.info("已扫码, 等待确认...")
            elif event == QRCodeLoginEvents.CONF:
                logger.info("确认中...")
            await anyio.sleep(1.5)

    async def check_login_expired(self) -> bool:
        if self._client is None:
            return True
        try:
            return await self._client.login.check_expired()
        except Exception as exc:
            logger.warning("check_expired 失败: %s", exc)
            return True

    # ------------------------------------------------------------------
    # 搜索 (0.6 SearchByTypeResponse 含 song/singer/album/songlist 等 list)
    # ------------------------------------------------------------------

    async def search_songs(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Song]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.SONG, num=limit, page=page, highlight=False
        )
        return [self._to_song(item) for item in (resp.song or [])]

    async def search_singers(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Singer]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.SINGER, num=limit, page=page, highlight=False
        )
        return [self._to_singer(item) for item in (resp.singer or [])]

    async def search_albums(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Album]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.ALBUM, num=limit, page=page, highlight=False
        )
        return [self._to_album_brief(item) for item in (resp.album or [])]

    async def search_playlists(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Playlist]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.SONGLIST, num=limit, page=page, highlight=False
        )
        return [self._to_playlist_brief(item) for item in (resp.songlist or [])]

    async def search(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Song]:
        return await self.search_songs(keyword, page=page, limit=limit)

    # ------------------------------------------------------------------
    # 详情拉取
    # ------------------------------------------------------------------

    async def get_album_detail(
        self, album_mid: str, *, song_limit: int = 100
    ) -> Album:
        if self.cache is not None:
            cached = self.cache.get_album(album_mid)
            if cached is not None and cached.songs:
                return cached

        # 0.6.1 client method 返回 Request 对象, 不是直接的 awaitable
        # asyncio.gather 不能用; 顺序 await
        detail_resp = await self.client.album.get_detail(album_mid)
        songs_resp = await self.client.album.get_song(
            album_mid, num=song_limit, page=1
        )

        bi = getattr(detail_resp, "album", None)
        company_singers = getattr(detail_resp, "singers", None) or []
        singers: list[Singer] = []
        for s in company_singers:
            singers.append(
                Singer(
                    mid=getattr(s, "mid", "") or "",
                    name=getattr(s, "name", "") or "",
                )
            )

        mid = getattr(bi, "mid", album_mid) or album_mid
        name = getattr(bi, "name", "") or getattr(bi, "title", "") or ""
        publish_date = getattr(bi, "time_public", "") or ""
        description = getattr(bi, "desc", "") or ""
        song_count = getattr(bi, "total_num", 0) or 0

        # songs_resp.song_list 是 song dict list
        raw_songs = getattr(songs_resp, "song_list", None) or []

        album = Album(
            mid=mid,
            name=name,
            singers=singers,
            cover_url=_cover_url(mid, 500),
            publish_date=publish_date,
            description=description,
            song_count=song_count or len(raw_songs),
            songs=[self._to_song(s) for s in raw_songs],
        )
        if self.cache is not None and album.songs:
            self.cache.put_album(album)
        return album

    async def get_playlist_detail(
        self, pid: str | int, *, song_limit: int = 300
    ) -> Playlist:
        pid_str = str(pid)
        if self.cache is not None:
            cached = self.cache.get_playlist(pid_str)
            if cached is not None and cached.songs:
                return cached

        try:
            sid = int(pid)
        except (TypeError, ValueError):
            sid = 0
        resp = await self.client.songlist.get_detail(
            songlist_id=sid, num=song_limit
        )
        # 0.6.1 GetSonglistDetailResponse: info (SonglistInfo) + songs (list) + total
        info = getattr(resp, "info", None)
        creator_obj = getattr(info, "creator", None)
        # creator 可能是 SonglistCreator (pydantic) 含 nick/name 字段
        creator_name = (
            getattr(creator_obj, "nick", "")
            or getattr(creator_obj, "name", "")
        ) if creator_obj else ""
        playlist = Playlist(
            pid=str(getattr(info, "id", "") or pid or ""),
            name=getattr(info, "title", "") or "",
            cover_url=getattr(info, "picurl", "") or "",
            description=getattr(info, "desc", "") or "",
            creator=creator_name,
            song_count=int(getattr(resp, "total", 0) or 0)
                or int(getattr(info, "songnum", 0) or 0),
            play_count=int(getattr(info, "listennum", 0) or 0),
            songs=[
                self._to_song(s) for s in (getattr(resp, "songs", None) or [])
            ],
        )
        if self.cache is not None and playlist.songs:
            self.cache.put_playlist(playlist)
        return playlist

    async def get_artist_detail(
        self, singer_mid: str, *, hot_song_limit: int = 50
    ) -> ArtistDetail:
        if self.cache is not None:
            cached = self.cache.get_artist(singer_mid)
            if cached is not None and cached.hot_songs:
                return cached

        info_resp = await self.client.singer.get_info(singer_mid)
        tab_resp = await self.client.singer.get_tab_detail(
            singer_mid, TabType.SONG, 1, hot_song_limit
        )
        # 0.6 HomepageHeaderResponse 含 singer (HomepageSinger), base_info
        singer_obj = getattr(info_resp, "singer", None) or getattr(
            info_resp, "base_info", None
        )
        name = getattr(singer_obj, "name", "") if singer_obj else ""
        avatar = (
            getattr(singer_obj, "singer_pic", "")
            or getattr(singer_obj, "avatar", "")
            if singer_obj else ""
        )
        s = Singer(mid=singer_mid, name=name or "", avatar_url=avatar or "")

        # tab_resp 是 HomepageTabDetailResponse; SONG tab 内的歌曲在 song_tab.list
        raw_songs = self._extract_artist_hot_songs(tab_resp)
        artist = ArtistDetail(
            singer=s,
            description="",
            hot_songs=[self._to_song(sr) for sr in raw_songs],
        )
        if self.cache is not None and artist.hot_songs:
            self.cache.put_artist(artist)
        return artist

    @staticmethod
    def _extract_artist_hot_songs(tab_resp: Any) -> list[Any]:
        """0.6 HomepageTabDetailResponse 里 hot songs 可能在 song_tab.list / tab_list[0].list."""
        for attr in ("song_tab", "song_list", "list"):
            v = getattr(tab_resp, attr, None)
            if v is not None:
                if hasattr(v, "list"):
                    inner = getattr(v, "list", None) or []
                    if inner:
                        return inner
                if isinstance(v, list) and v:
                    return v
        # fallback: 看 tab_list (list of dict)
        tl = getattr(tab_resp, "tab_list", None) or []
        for item in tl:
            inner = getattr(item, "list", None) or []
            if inner:
                return inner
        return []

    async def get_lyric(
        self, mid: str, *, with_translation: bool = True
    ) -> Lyric:
        """拉歌词. 走 bypass: 0.6 lib 硬编码 crypt=1 服务端返加密歌词,
        我们直接 POST crypt=0 拿 base64 明文."""
        import base64

        block = await self._bypass_post(
            "music.musichallSong.PlayLyricInfo",
            "GetPlayLyricInfo",
            {
                "crypt": 0,
                "lrc_t": 0,
                "qrc": 0, "qrc_t": 0,
                "roma": 0, "roma_t": 0,
                "trans": 1 if with_translation else 0,
                "trans_t": 0,
                "type": 1,
                "songMid": mid,
            },
            require_login=True,
        )
        if not block:
            return Lyric(mid=mid, lines=[], has_translation=False)

        lrc_b64 = block.get("lyric", "") or ""
        trans_b64 = block.get("trans", "") or ""

        def _decode(b64: str) -> str:
            if not b64:
                return ""
            try:
                return base64.b64decode(b64).decode("utf-8", errors="replace")
            except Exception:
                return ""

        lrc_text = _decode(lrc_b64)
        trans_text = _decode(trans_b64)

        lines = parse_lrc(lrc_text)
        if trans_text:
            trans_lines = parse_lrc(trans_text)
            trans_by_ts = {ln.timestamp_ms: ln.text for ln in trans_lines}
            lines = [
                LyricLine(
                    timestamp_ms=ln.timestamp_ms,
                    text=ln.text,
                    translation=trans_by_ts.get(ln.timestamp_ms, ""),
                )
                for ln in lines
            ]
        return Lyric(
            mid=mid, lines=lines, has_translation=bool(trans_text)
        )

    # ------------------------------------------------------------------
    # 歌曲播放 URL (绕过库的 get_song_urls; 走自拼 vkey)
    # ------------------------------------------------------------------

    async def get_song_url(
        self,
        song_obj: Song,
        *,
        quality_preference: str = "balanced",
    ) -> SongUrl | None:
        """按音质降级, 走 bypass vkey 路径拿可播完整 URL."""
        order = self._QUALITY_PROFILES.get(
            quality_preference, self._QUALITY_PROFILES[self._DEFAULT_QUALITY]
        )
        for quality_label in order:
            url = await self._try_bypass_url(song_obj.mid, quality_label)
            if url:
                logger.info("命中 %s: %s", quality_label, song_obj.name)
                return SongUrl(
                    mid=song_obj.mid, url=url, quality=quality_label
                )
        logger.warning("所有音质均不可下发: %s", song_obj.name)
        return None

    async def _bypass_post(
        self,
        module: str,
        method: str,
        param: dict[str, Any],
        *,
        require_login: bool = False,
    ) -> dict[str, Any] | None:
        """通用 musicu.fcg POST: 用 self._ct_value 跳过库默认 ct=11 的降级响应.

        返回 req_0.data 字典 (失败/无登录时 None).
        """
        cred = self._effective_credential()
        if require_login and (cred is None or not cred.musickey):
            return None

        comm: dict[str, Any] = {"ct": self._ct_value, "cv": 0}
        if cred is not None and cred.musickey:
            comm["qq"] = str(cred.musicid)
            comm["authst"] = cred.musickey

        body = {
            "comm": comm,
            "req_0": {"module": module, "method": method, "param": param},
        }

        def _do() -> dict[str, Any]:
            import niquests
            with niquests.Session() as s:
                r = s.post(
                    "https://u.y.qq.com/cgi-bin/musicu.fcg",
                    json=body,
                    timeout=10,
                )
                return r.json()

        try:
            data = await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("bypass %s.%s 请求异常: %s", module, method, exc)
            return None

        return data.get("req_0", {}).get("data", {}) or {}

    async def _try_bypass_url(
        self, mid: str, quality_label: str
    ) -> str | None:
        """vkey bypass. ct 实例生命周期内固定 (启动时从 _SAFE_CT_VALUES 随机)."""
        prefix_ext = self._QUALITY_FILE.get(quality_label)
        if not prefix_ext:
            return None
        prefix, ext = prefix_ext
        filename = f"{prefix}{mid}{mid}.{ext}"

        data = await self._bypass_post(
            "music.vkey.GetVkey",
            "UrlGetVkey",
            {
                "filename": [filename],
                "guid": uuid.uuid4().hex,
                "songmid": [mid],
                "songtype": [0],
            },
            require_login=True,
        )
        if not data:
            return None

        midurlinfo = data.get("midurlinfo") or []
        if not midurlinfo:
            return None
        purl = midurlinfo[0].get("purl", "") or ""
        if not purl:
            return None
        return f"https://isure.stream.qqmusic.qq.com/{purl}"

    # ------------------------------------------------------------------
    # 用户库 (我喜欢 + 我创建的歌单)
    # ------------------------------------------------------------------

    # 0.6 QQ "我喜欢" 歌单的固定 dirid (所有账号都是 201)
    FAV_DIRID = 201

    async def get_liked_songs(
        self, *, limit: int = 500
    ) -> list[Song]:
        """拉远端"我喜欢"歌单的歌. 需要登录态."""
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return []
        resp = await self.client.user.get_fav_song(
            cred.encrypt_uin, num=limit, page=1, credential=cred
        )
        songs = getattr(resp, "songs", None) or []
        return [self._to_song(s) for s in songs]

    async def like_song(self, song: Song) -> bool:
        """把歌加到"我喜欢"歌单. song.id 需是 QQ 数字 ID."""
        cred = self._effective_credential()
        if cred is None or not cred.musickey:
            return False
        if song.id == 0:
            logger.warning("like_song: %s 缺数字 id, 跳过", song.name)
            return False
        try:
            ok = await self.client.songlist.add_songs(
                self.FAV_DIRID, [(song.id, 1)], credential=cred
            )
            return bool(ok)
        except Exception as exc:
            logger.warning("like_song API 失败: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 发现 / 推荐 (P2.1 — HomeView)
    # ------------------------------------------------------------------

    def _memo_get(self, key: str) -> Any | None:
        hit = self._memo.get(key)
        if hit is None:
            return None
        ts, val = hit
        if time.time() - ts > self._MEMO_TTL_SEC:
            return None
        return val

    def _memo_put(self, key: str, value: Any) -> None:
        self._memo[key] = (time.time(), value)

    async def get_recommend_playlists(
        self, *, limit: int = 8
    ) -> list[Playlist]:
        """推荐歌单 (首页 Featured Playlists). 10 分钟内存 cache."""
        cached = self._memo_get("recommend_playlists")
        if cached is not None:
            return cached[:limit]

        try:
            resp = await self.client.recommend.get_recommend_songlist(num=limit)
        except Exception as exc:
            logger.warning("get_recommend_songlist 失败: %s", exc)
            return []
        out: list[Playlist] = []
        for p in (getattr(resp, "songlists", None) or [])[:limit]:
            pid = str(getattr(p, "id", "") or "")
            out.append(
                Playlist(
                    pid=pid,
                    name=getattr(p, "title", "") or "",
                    cover_url=getattr(p, "picurl", "") or "",
                    description=getattr(p, "desc", "") or "",
                    creator=getattr(p, "creator_nick", "") or "",
                    song_count=int(getattr(p, "songnum", 0) or 0),
                    play_count=int(getattr(p, "listennum", 0) or 0),
                )
            )
        self._memo_put("recommend_playlists", out)
        return out

    async def get_top_categories(
        self, *, limit_per_group: int | None = None
    ) -> list[TopList]:
        """所有排行榜入口扁平化 (各 group 拼起来). 10 分钟内存 cache.

        用库默认 ct=11 (PC web 客户端 profile): 实测此 profile 返回 43 个榜
        (含巅峰潮流榜 等编辑榜); safe ct (移动端) 仅 30 个, 反而缺榜.
        intro 在列表里为空是 QQ 设计 — 详情页 GetDetail 才有.
        """
        cached = self._memo_get("top_categories")
        if cached is not None:
            return cached

        try:
            resp = await self.client.top.get_category()
        except Exception as exc:
            logger.warning("get_top_categories 失败: %s", exc)
            return []
        out: list[TopList] = []
        for g in (getattr(resp, "group", None) or []):
            tlist = getattr(g, "toplist", None) or []
            if limit_per_group is not None:
                tlist = tlist[:limit_per_group]
            for tl in tlist:
                out.append(
                    TopList(
                        top_id=int(getattr(tl, "id", 0) or 0),
                        name=getattr(tl, "name", "") or "",
                        cover_url=(
                            getattr(tl, "front_pic_url", "")
                            or getattr(tl, "head_pic_url", "")
                            or ""
                        ),
                        intro=_clean_text(getattr(tl, "intro", ""), max_len=80),
                        total_num=int(getattr(tl, "total_num", 0) or 0),
                    )
                )
        self._memo_put("top_categories", out)
        return out

    async def get_top_detail(
        self, top_id: int, *, limit: int = 100
    ) -> Playlist:
        """单个排行榜详情, 复用 Playlist 模型. 库默认 ct=11 即可拿完整 intro.

        注: 某些榜本身服务端无 intro (如 tid=135 巅峰潮流榜, 编辑榜没规则文本),
        这不是 ct 风控. 调用方需对 description 容空.
        """
        try:
            resp = await self.client.top.get_detail(top_id, num=limit, page=1)
        except Exception as exc:
            logger.warning("get_top_detail 失败 (top_id=%s): %s", top_id, exc)
            return Playlist(pid=str(top_id), name="榜单不可用")

        info = getattr(resp, "info", None)
        songs_raw = getattr(resp, "songs", None) or []
        return Playlist(
            pid=str(top_id),
            name=getattr(info, "name", "") or "",
            cover_url=(
                getattr(info, "front_pic_url", "")
                or getattr(info, "head_pic_url", "")
                or ""
            ),
            description=_clean_text(getattr(info, "intro", ""), max_len=400),
            creator="",
            song_count=int(getattr(info, "total_num", 0) or 0),
            play_count=int(getattr(info, "listen_num", 0) or 0),
            songs=[self._to_song(s) for s in songs_raw],
        )

    async def get_recommend_new_songs(
        self, *, limit: int = 12
    ) -> list[Song]:
        """新歌速递 (首页 New Releases). 10 分钟内存 cache."""
        cached = self._memo_get("recommend_new_songs")
        if cached is not None:
            return cached[:limit]

        try:
            resp = await self.client.recommend.get_recommend_newsong()
        except Exception as exc:
            logger.warning("get_recommend_newsong 失败: %s", exc)
            return []
        songs_raw = getattr(resp, "songs", None) or []
        out = [self._to_song(s) for s in songs_raw[:limit]]
        self._memo_put("recommend_new_songs", out)
        return out

    async def get_hot_search(self, *, limit: int = 12) -> list[str]:
        """热搜词 (vec_hotkey 抽 query). 10 分钟内存 cache, 去重."""
        cached = self._memo_get("hot_search")
        if cached is not None:
            return cached[:limit]

        try:
            resp = await self.client.search.get_hotkey()
        except Exception as exc:
            logger.warning("get_hotkey 失败: %s", exc)
            return []

        items = (resp or {}).get("vec_hotkey", []) or []
        out: list[str] = []
        seen: set[str] = set()
        for it in items:
            q = (it.get("query") or "").strip()
            if not q or q in seen:
                continue
            seen.add(q)
            out.append(q)
        self._memo_put("hot_search", out)
        return out[:limit]

    async def get_search_suggest(
        self, keyword: str, *, limit: int = 10
    ) -> list[str]:
        """搜索补全 (smartbox items 抽 hint). 空 keyword 不发请求."""
        kw = (keyword or "").strip()
        if not kw:
            return []
        try:
            resp = await self.client.search.complete(kw)
        except Exception as exc:
            logger.warning("search.complete 失败 (%s): %s", kw, exc)
            return []

        items = (resp or {}).get("items", []) or []
        out: list[str] = []
        seen: set[str] = set()
        for it in items:
            hint = (it.get("hint") or "").strip()
            if not hint or hint in seen:
                continue
            seen.add(hint)
            out.append(hint)
            if len(out) >= limit:
                break
        return out

    async def get_my_playlists(self) -> list[Playlist]:
        """我创建的歌单 (排除 dirid=201 那个"我喜欢", 后者走 library)."""
        cred = self._effective_credential()
        if cred is None or not cred.musicid:
            return []
        try:
            resp = await self.client.user.get_created_songlist(
                int(cred.musicid), credential=cred
            )
        except Exception as exc:
            logger.warning("get_created_songlist 失败: %s", exc)
            return []
        out: list[Playlist] = []
        for p in (resp.playlists or []):
            if getattr(p, "dirid", 0) == self.FAV_DIRID:
                continue  # 我喜欢单独成 Tab
            out.append(
                Playlist(
                    pid=str(getattr(p, "id", "") or ""),
                    name=getattr(p, "title", "") or "",
                    cover_url=getattr(p, "picurl", "") or "",
                    description=getattr(p, "desc", "") or "",
                    creator="",  # 自己
                    song_count=int(getattr(p, "songnum", 0) or 0),
                    play_count=int(getattr(p, "listennum", 0) or 0),
                    is_mine=True,
                )
            )
        return out

    async def get_fav_albums(self) -> list[Album]:
        """收藏的专辑. 0.6.1 lib 在用户只有 0/1 个专辑时 pydantic 校验报错, try/except 容错."""
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return []
        try:
            resp = await self.client.user.get_fav_album(
                cred.encrypt_uin, page=1, num=200, credential=cred
            )
        except Exception as exc:
            logger.warning("get_fav_album 失败 (lib 校验问题或无数据): %s", exc)
            return []
        out: list[Album] = []
        for a in (getattr(resp, "albums", None) or []):
            mid = getattr(a, "mid", "") or ""
            singer_obj = getattr(a, "singer", None)
            singers: list[Singer] = []
            if singer_obj is not None:
                # 可能是单个或列表
                items = (
                    singer_obj if isinstance(singer_obj, list) else [singer_obj]
                )
                for s in items:
                    singers.append(
                        Singer(
                            mid=getattr(s, "mid", "") or "",
                            name=getattr(s, "name", "") or "",
                        )
                    )
            out.append(
                Album(
                    mid=mid,
                    name=getattr(a, "name", "") or "",
                    singers=singers,
                    cover_url=getattr(a, "pic_url", None)
                        or getattr(a, "pic", None)
                        or _cover_url(mid, 300),
                    publish_date=getattr(a, "time_public", "") or "",
                    song_count=int(getattr(a, "song_num", 0) or 0),
                )
            )
        return out

    async def get_followed_singers(self) -> list[Singer]:
        """关注的歌手."""
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return []
        try:
            resp = await self.client.user.get_follow_singers(
                cred.encrypt_uin, page=1, num=200, credential=cred
            )
        except Exception as exc:
            logger.warning("get_follow_singers 失败: %s", exc)
            return []
        out: list[Singer] = []
        for s in (getattr(resp, "users", None) or []):
            out.append(
                Singer(
                    mid=getattr(s, "mid", "") or "",
                    name=getattr(s, "name", "") or "",
                    avatar_url=getattr(s, "avatar_url", "") or "",
                )
            )
        return out

    async def unlike_song(self, song: Song) -> bool:
        cred = self._effective_credential()
        if cred is None or not cred.musickey or song.id == 0:
            return False
        try:
            ok = await self.client.songlist.del_songs(
                self.FAV_DIRID, [(song.id, 1)], credential=cred
            )
            return bool(ok)
        except Exception as exc:
            logger.warning("unlike_song API 失败: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 凭据持久化
    # ------------------------------------------------------------------

    async def _get_cached_credential(self) -> Credential | None:
        path = self._credential_cache_path
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return _credential_from_dict(json.load(f))
        except Exception as exc:
            logger.warning("读取缓存凭据失败: %s", exc)
            return None

    async def save_credential(self, path: str | None = None) -> None:
        cred = self._effective_credential()
        if not cred or not cred.musickey:
            return
        save_path = path or self._credential_cache_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(_credential_to_dict(cred), f, ensure_ascii=False)
        logger.info("凭据已保存到 %s", save_path)

    @property
    def _credential_cache_path(self) -> str:
        from ..config import CONFIG_DIR
        return str(CONFIG_DIR / "credential.json")

    # ------------------------------------------------------------------
    # 模型转换 (0.6 pydantic 对象 → 我们的 dataclass)
    # ------------------------------------------------------------------

    @staticmethod
    def _to_song(raw: Any) -> Song:
        """支持 pydantic SongSearch / 普通 dict / SimpleNamespace."""
        singers: list[Singer] = []
        singer_list = QuaverService._g(raw, "singer", None)
        if singer_list:
            for s in singer_list:
                singers.append(
                    Singer(
                        mid=QuaverService._g(s, "mid", "") or "",
                        name=QuaverService._g(s, "name", "") or "",
                    )
                )

        album_obj = QuaverService._g(raw, "album", None)
        album_mid = QuaverService._g(album_obj, "mid", "") or ""
        album_name = QuaverService._g(album_obj, "name", "") or ""
        cover_url = ""
        if album_obj is not None:
            cover_fn = QuaverService._g(album_obj, "cover_url", None)
            if callable(cover_fn):
                try:
                    cover_url = cover_fn(300) or ""
                except Exception:
                    cover_url = ""
        if not cover_url and album_mid:
            cover_url = _cover_url(album_mid, 300)

        file_obj = QuaverService._g(raw, "file", None)
        media_mid = QuaverService._g(file_obj, "media_mid", "") or ""

        pay_obj = QuaverService._g(raw, "pay", None)
        pay_play = int(QuaverService._g(pay_obj, "pay_play", 0) or 0)

        return Song(
            mid=QuaverService._g(raw, "mid", "") or "",
            name=QuaverService._g(raw, "name", "") or "",
            singers=singers,
            album_mid=album_mid,
            album_name=album_name,
            cover_url=cover_url,
            duration=int(QuaverService._g(raw, "interval", 0) or 0),
            pay_play=pay_play,
            media_mid=media_mid,
            id=int(QuaverService._g(raw, "id", 0) or 0),
        )

    @staticmethod
    def _to_singer(raw: Any) -> Singer:
        """0.6 SingerSearch: mid/name/pic; 0.4 raw dict: singerMID/singerName/singerPic."""
        return Singer(
            mid=QuaverService._g(raw, "mid", None)
                or QuaverService._g(raw, "singerMID", "") or "",
            name=QuaverService._g(raw, "name", None)
                or QuaverService._g(raw, "singerName", "") or "",
            avatar_url=QuaverService._g(raw, "pic", None)
                or QuaverService._g(raw, "singerPic", "") or "",
        )

    @staticmethod
    def _to_album_brief(raw: Any) -> Album:
        """0.6 AlbumSearch: mid/name/pic/time_public/singer_list."""
        singers: list[Singer] = []
        sl = QuaverService._g(raw, "singer_list", None) or []
        for s in sl:
            singers.append(
                Singer(
                    mid=QuaverService._g(s, "mid", "") or "",
                    name=QuaverService._g(s, "name", "") or "",
                )
            )
        # 0.6 是 'mid' / 'albummid' 都试一下
        album_mid = (
            QuaverService._g(raw, "mid", None)
            or QuaverService._g(raw, "albummid", "")
            or ""
        )
        cover = (
            QuaverService._g(raw, "pic", None)
            or _cover_url(album_mid, 300)
        )
        publish_date = (
            QuaverService._g(raw, "time_public", None)
            or QuaverService._g(raw, "publish_date", "")
            or ""
        )
        return Album(
            mid=album_mid,
            name=QuaverService._g(raw, "name", "") or "",
            singers=singers,
            cover_url=cover or "",
            publish_date=publish_date,
            description="",
            song_count=int(
                QuaverService._g(raw, "song_num", None)
                or QuaverService._g(raw, "total_num", 0)
                or 0
            ),
        )

    @staticmethod
    def _to_playlist_brief(raw: Any) -> Playlist:
        """0.6 SongListSearch: id/dirid/title/picurl/desc/songnum/listennum/nickname.

        注意: 传给 get_detail(songlist_id=...) 的是 `id` 字段, 不是 `dirid`.
        SongListSearch.dirid 经常是 0 (无意义), id 才是真的 songlist 全局 ID.
        """
        pid = str(
            QuaverService._g(raw, "id", None)
            or QuaverService._g(raw, "dissid", "")
            or ""
        )
        name = (
            QuaverService._g(raw, "title", None)
            or QuaverService._g(raw, "dissname", "")
            or ""
        )
        return Playlist(
            pid=pid,
            name=name,
            cover_url=QuaverService._g(raw, "picurl", None)
                or QuaverService._g(raw, "logo", "") or "",
            description=QuaverService._g(raw, "desc", "") or "",
            creator=QuaverService._g(raw, "nickname", "") or "",
            song_count=int(QuaverService._g(raw, "songnum", 0) or 0),
            play_count=int(QuaverService._g(raw, "listennum", 0) or 0),
        )

    @staticmethod
    def _g(obj: Any, name: str, default: Any) -> Any:
        """通用读字段: dict / pydantic / SimpleNamespace 都走 getattr/get."""
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    @staticmethod
    def to_song_simple(raw: Any) -> Song:
        return QuaverService._to_song(raw)
