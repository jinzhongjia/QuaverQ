"""QQ 音乐服务层 (qqmusic-api-python 0.6.1).

关键设计:
- 用 0.6.x Client 类 + pydantic 返回模型
- get_song_url 走 **bypass 路径**: 自拼 musicu.fcg JSON, 不经过库的 get_song_urls,
  避免 0.6 默认 ct=11 触发地区版权风控.
- ct 在 service 启动时从合法白名单 random.choice 选一个, 实例生命周期固定,
  既避免高风险值 (1/3/4/11/18/23/27/46), 也防止固定值被未来收紧.

ct 风控背景见 findings.md 第三节.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from qqmusic_api import Client, Credential
from qqmusic_api.core.exceptions import (
    CredentialExpiredError as QQCredentialExpiredError,
    CredentialInvalidError as QQCredentialInvalidError,
    LoginError as QQLoginError,
)
from qqmusic_api.models.login import QRCodeLoginEvents, QRLoginType
from qqmusic_api.modules.search import SearchType
from qqmusic_api.modules.singer import TabType

from .lyric import parse_lrc, parse_qrc
from .models import (
    Album,
    ArtistDetail,
    Lyric,
    LyricLine,
    Playlist,
    ProducerGroup,
    Singer,
    Song,
    SongInfo,
    SongUrl,
    TopList,
    UserProfile,
)

if TYPE_CHECKING:
    from collections.abc import Callable as _Cb  # noqa: F401

logger = logging.getLogger(__name__)


class CredentialExpiredError(RuntimeError):
    """QQ Music credential is missing, expired, or rejected by a user API."""


_CREDENTIAL_EXPIRED_TEXT_TOKENS = (
    "credential expired",
    "login expired",
    "not login",
    "need login",
    "invalid credential",
    "有效登录凭证",
    "登录凭证已过期",
    "登录鉴权参数无效或已过期",
    "登录失效",
    "登录过期",
    "未登录",
    "请登录",
    "重新登录",
)
_CREDENTIAL_EXPIRED_CODES = (1000, 104400, 104401)


def is_credential_expired_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            CredentialExpiredError,
            QQCredentialExpiredError,
            QQCredentialInvalidError,
        ),
    ):
        return True
    if isinstance(exc, QQLoginError) and exc.code in _CREDENTIAL_EXPIRED_CODES:
        return True
    for item in _walk_exception_graph(exc):
        code = getattr(item, "code", None)
        if code in _CREDENTIAL_EXPIRED_CODES:
            return True
    text = " ".join(str(item) for item in _walk_exception_graph(exc)).lower()
    return any(token in text for token in _CREDENTIAL_EXPIRED_TEXT_TOKENS)


def _walk_exception_graph(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    out: list[BaseException] = []

    def walk(item: BaseException) -> None:
        if id(item) in seen:
            return
        seen.add(id(item))
        out.append(item)
        for nested in (item.__cause__, item.__context__):
            if nested is not None:
                walk(nested)
        for arg in item.args:
            if isinstance(arg, BaseException):
                walk(arg)

    walk(exc)
    return out


# ---------------------------------------------------------------- helpers


def _cover_url(album_mid: str, size: int = 300) -> str:
    if not album_mid:
        return ""
    return f"https://y.qq.com/music/photo_new/T002R{size}x{size}M000{album_mid}.jpg"


def cover_url_for(album_mid: str, size: int = 300) -> str:
    """公开别名: 供 bridge 层 (下载封面落盘) 按 album_mid 构造封面 URL."""
    return _cover_url(album_mid, size)


def _singer_avatar_url(singer_mid: str, size: int = 300) -> str:
    """歌手头像 CDN 模板 (T001); 接口偶尔不回 SingerPic, 用 mid 兜底."""
    if not singer_mid:
        return ""
    return f"https://y.qq.com/music/photo_new/T001R{size}x{size}M000{singer_mid}.jpg"


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(s: str | None, *, max_len: int = 120) -> str:
    """去 HTML 标签 + 折空白 + 截断 (UI 显示用的文本规整)."""
    if not s:
        return ""
    txt = _HTML_TAG_RE.sub(" ", s)  # <br>/<em> 等 → 空格
    txt = _WS_RE.sub(" ", txt).strip()  # 多空白 → 单空格
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


# ---------------------------------------------------------------- 凭据存储 (keyring)

# keyring 条目: (service_name, username); 同一 (service, user) 内一条 JSON blob 即可,
# 因为我们只有一个用户登录态需要持久化.
_KEYRING_SERVICE = "QuaverQ"
_KEYRING_USERNAME = "credential"


def _save_credential_blob(blob: str) -> None:
    """保存凭据 JSON blob 到 keyring.

    keyring 自动选平台后端: Linux Secret Service / Windows Credential Manager /
    macOS Keychain. 失败 (headless Linux 无 D-Bus 等) 只 log warning, 不 raise ——
    凭据保存失败不应当阻塞 app 运行, 用户重启后需要重新扫码即可.
    """
    try:
        import keyring
        import keyring.errors

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, blob)
    except keyring.errors.KeyringError as exc:
        logger.warning("keyring 写失败 (%s), 凭据本次未持久化", exc)
    except Exception as exc:  # 兜底: keyring import / backend init 异常
        logger.warning("keyring 调用失败 (%s), 凭据本次未持久化", exc)


def _load_credential_blob() -> str | None:
    """从 keyring 读凭据 JSON blob; 没有 / 失败均返 None."""
    try:
        import keyring
        import keyring.errors

        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except keyring.errors.KeyringError as exc:
        logger.debug("keyring 读失败: %s", exc)
        return None
    except Exception as exc:
        logger.debug("keyring 调用异常: %s", exc)
        return None


# ---------------------------------------------------------------- service


@dataclass
class QuaverService:
    """QQ 音乐 API 门面层 (0.6.1, 含 vkey bypass).

    用法:
        svc = QuaverService()
        await svc.connect()
        svc.set_credential_sync(cached_cred)
        url = await svc.get_song_url(song, quality_preference="high")
    """

    credential: Credential | None = None
    on_qrcode: Callable[[bytes, str, str], None] | None = None
    on_login_status: Callable[[str], None] | None = None

    _client: Client | None = field(default=None, init=False, repr=False)
    # bypass 路径用的 ct 值, 实例生命周期内固定 (见 _SAFE_CT_VALUES)
    _ct_value: int = field(default=0, init=False, repr=False)
    # 反风控 G1: 持久设备 guid (connect 时从 config 填充), 取链复用同一值
    _device_guid: str = field(default="", init=False, repr=False)
    # 实例级内存 cache: 短期 ad-hoc 数据 (recommend 等) 不适合 SQLite TTL 表
    # key → (timestamp, value); 重启失效
    _memo: dict[str, tuple[float, Any]] = field(default_factory=dict, init=False, repr=False)
    # 续命锁: 防并发刷新触发 refresh_token rotation (Gemini Code Review PR#1)
    _refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # 内存 cache 默认 TTL: 推荐数据每天/每小时换换, 10 分钟够
    _MEMO_TTL_SEC = 600

    # ------------------------------------------------------------------
    # bypass / 反风控
    # ------------------------------------------------------------------

    # 合法 ct 候选池 (排除 findings.md 列出的风控值 1/3/4/11/18/19/23/27/46)
    # 反风控原则: 1) 不固定一个值 2) 避开"客户端热门"值
    # ct=19: 2026-06-07 实测被加入风控黑名单, CDN 直接返 403 (Lego Server)
    _SAFE_CT_VALUES = (
        2,
        5,
        6,
        7,
        8,
        9,
        10,
        12,
        13,
        14,
        15,
        16,
        17,
        20,
        21,
        22,
        24,
        25,
        26,
        28,
        29,
        30,
    )

    # vkey 接口 filename 前缀 + 扩展名 (mid 双拼)
    # 见 findings 第五节: filename=`{prefix}{mid}{mid}.{ext}`
    # MASTER (臻品母带 24Bit/192kHz) / ATMOS_2 (臻品全景声) 仅下载档位使用,
    # 播放 profile 不含它们 (161MB 级文件拉流浪费带宽; 见 findings 第 4.2 节)
    _QUALITY_FILE: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "MASTER": ("AI00", "flac"),
            "ATMOS_2": ("Q000", "flac"),
            "FLAC": ("F000", "flac"),
            "MP3_320": ("M800", "mp3"),
            "OGG_192": ("O600", "ogg"),
            "MP3_128": ("M500", "mp3"),
        },
        init=False,
        repr=False,
    )

    # 各档音质偏好的降级顺序 (字符串 label, 不依赖 qqmusic SongFileType)
    # "master" 档仅供下载侧选择 (SettingsController._DOWNLOAD_QUALITIES)
    _QUALITY_PROFILES = {
        "master": ("MASTER", "ATMOS_2", "FLAC", "MP3_320", "OGG_192", "MP3_128"),
        "high": ("FLAC", "MP3_320", "OGG_192", "MP3_128"),
        "balanced": ("MP3_320", "OGG_192", "MP3_128"),
        "standard": ("MP3_128", "OGG_192"),
    }
    _DEFAULT_QUALITY = "balanced"
    _VKEY_REQUEST_TIMEOUT_SEC = 4
    # 反风控 U1/G2: curl_cffi 用官方浏览器 TLS 指纹 (JA3) + UA 发 musicu.fcg
    _IMPERSONATE = "chrome"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def __aenter__(self) -> QuaverService:
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """初始化 Client + 随机选定本次会话用的 ct 值."""
        self._client = Client(credential=self.credential)
        # 反风控: 每次启动从合法池中随机, 但实例生命周期内固定一个
        self._ct_value = random.choice(self._SAFE_CT_VALUES)
        if not self._device_guid:
            from ..config import device_guid

            self._device_guid = device_guid()
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

    async def login_by_qrcode(self, login_type: QRLoginType = QRLoginType.QQ) -> bool:
        if self._client is None:
            raise RuntimeError("服务未连接")
        qr = await self._client.login.get_qrcode(login_type)
        if self.on_qrcode:
            self.on_qrcode(qr.data, qr.qr_type.value, qr.mimetype)
        if self.on_login_status:
            self.on_login_status("qrcode")
        logger.info("二维码已获取 (类型: %s)", qr.qr_type.name)

        import anyio

        while True:
            result = await self._client.login.check_qrcode(qr)
            event = result.event
            if event == QRCodeLoginEvents.DONE:
                assert result.credential is not None
                self.credential = result.credential
                self._assign_credential(result.credential)
                if self.on_login_status:
                    self.on_login_status("done")
                logger.info("登录成功")
                return True
            if event == QRCodeLoginEvents.TIMEOUT:
                if self.on_login_status:
                    self.on_login_status("timeout")
                logger.warning("二维码已过期")
                return False
            if event == QRCodeLoginEvents.REFUSE:
                if self.on_login_status:
                    self.on_login_status("refuse")
                logger.warning("用户拒绝授权")
                return False
            if event == QRCodeLoginEvents.SCAN:
                if self.on_login_status:
                    self.on_login_status("waiting")
                logger.info("等待扫码...")
            elif event == QRCodeLoginEvents.CONF:
                if self.on_login_status:
                    self.on_login_status("scanned")
                logger.info("已扫码, 等待确认...")
            await anyio.sleep(0.8 if event == QRCodeLoginEvents.CONF else 1.5)

    async def check_login_expired(self) -> bool:
        expired = await self.probe_login_expired()
        return expired is not False

    async def probe_login_expired(self) -> bool | None:
        if self._client is None:
            return True
        try:
            expired = await self._client.login.check_expired()
        except Exception as exc:
            if is_credential_expired_error(exc):
                logger.warning("check_expired 返回登录失效: %s", exc)
                return await self._try_refresh_credential()
            logger.warning("check_expired 失败: %s", exc)
            return None
        if not expired:
            return False
        return await self._try_refresh_credential()

    async def _try_refresh_credential(self) -> bool:
        """登录凭据过期时尝试静默续命; 成功返回 False (未过期), 失败返回 True.

        并发安全: refresh_token 通常一次性 (rotation), 多协程同时刷新会让第二次拿到
        失效 token, 整条续命链断裂. 用 `_refresh_lock` + 双重检查避免重复刷新.
        """
        if self._client is None:
            return True
        before = self._effective_credential()
        before_key = getattr(before, "musickey", None) if before else None

        async with self._refresh_lock:
            current = self._effective_credential()
            current_key = getattr(current, "musickey", None) if current else None
            if current_key and current_key != before_key:
                # 等锁期间已被其他协程刷新成功, 直接复用结果
                return False

            try:
                new_cred = await self._client.login.refresh_credential()
            except Exception as exc:
                logger.warning("refresh_credential 失败: %s", exc)
                return True
            if new_cred is None or not getattr(new_cred, "musickey", None):
                logger.warning("refresh_credential 返回空凭据, 视作失败")
                return True
            self._assign_credential(new_cred)
            try:
                await self.save_credential()
            except Exception as exc:
                logger.warning("刷新凭据后落盘失败: %s", exc)
            logger.info("凭据已通过 refresh_credential 续命")
            return False

    # ------------------------------------------------------------------
    # 搜索 (0.6 SearchByTypeResponse 含 song/singer/album/songlist 等 list)
    # ------------------------------------------------------------------

    async def search_songs(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Song]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.SONG, num=limit, page=page, highlight=False
        )
        return [self._to_song(item) for item in (resp.song or [])]

    async def search_singers(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Singer]:
        resp = await self.client.search.search_by_type(
            keyword, SearchType.SINGER, num=limit, page=page, highlight=False
        )
        return [self._to_singer(item) for item in (resp.singer or [])]

    async def search_albums(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Album]:
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

    async def search(self, keyword: str, *, page: int = 1, limit: int = 30) -> list[Song]:
        return await self.search_songs(keyword, page=page, limit=limit)

    # ------------------------------------------------------------------
    # 详情拉取
    # ------------------------------------------------------------------

    async def get_album_detail(self, album_mid: str, *, song_limit: int = 100) -> Album:
        # 0.6.1 client method 返回 awaitable 但 unhashable 的 Request 对象; 直接塞
        # gather 会在内部去重 dict 时报 TypeError。包成本地 coroutine 后可安全并发。
        async def _fetch_detail() -> Any:
            return await self.client.album.get_detail(album_mid)

        async def _fetch_songs() -> Any:
            return await self.client.album.get_song(album_mid, num=song_limit, page=1)

        detail_resp, songs_resp = await asyncio.gather(_fetch_detail(), _fetch_songs())

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
        return album

    async def get_playlist_detail(self, pid: str | int, *, song_limit: int = 300) -> Playlist:
        try:
            sid = int(pid)
        except (TypeError, ValueError):
            sid = 0
        resp = await self.client.songlist.get_detail(songlist_id=sid, num=song_limit)
        # 0.6.1 GetSonglistDetailResponse: info (SonglistInfo) + songs (list) + total
        info = getattr(resp, "info", None)
        creator_obj = getattr(info, "creator", None)
        # creator 可能是 SonglistCreator (pydantic) 含 nick/name 字段
        creator_name = (
            (getattr(creator_obj, "nick", "") or getattr(creator_obj, "name", ""))
            if creator_obj
            else ""
        )
        playlist = Playlist(
            pid=str(getattr(info, "id", "") or pid or ""),
            name=getattr(info, "title", "") or "",
            cover_url=getattr(info, "picurl", "") or "",
            description=getattr(info, "desc", "") or "",
            creator=creator_name,
            song_count=int(getattr(resp, "total", 0) or 0) or int(getattr(info, "songnum", 0) or 0),
            play_count=int(getattr(info, "listennum", 0) or 0),
            songs=[self._to_song(s) for s in (getattr(resp, "songs", None) or [])],
        )
        return playlist

    # ------------------------------------------------------------------
    # 歌手 tab 数据 (第二档 2.2)
    # ------------------------------------------------------------------

    async def get_similar_singers(self, singer_mid: str, *, limit: int = 10) -> list[Singer]:
        """相似歌手 (歌手详情页 tab). 公开接口, 凭据过期类异常透传."""
        if not singer_mid:
            return []
        try:
            resp = await self.client.singer.get_similar(singer_mid, number=limit)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_similar_singers 失败 (mid=%s): %s", singer_mid, exc)
            return []
        out: list[Singer] = []
        for s in getattr(resp, "singerlist", None) or []:
            mid = getattr(s, "mid", "") or ""
            if not mid:
                continue
            out.append(
                Singer(
                    mid=mid,
                    name=getattr(s, "name", "") or "",
                    avatar_url=(getattr(s, "singer_pic", "") or "") or _singer_avatar_url(mid),
                )
            )
        return out

    async def get_singer_songs(
        self, singer_mid: str, *, limit: int = 50, page: int = 1
    ) -> list[Song]:
        """歌手全部歌曲 (分页). 返回的是完整 Song pydantic, 走 _to_song."""
        if not singer_mid:
            return []
        try:
            resp = await self.client.singer.get_songs_list(singer_mid, num=limit, page=page)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_singer_songs 失败 (mid=%s): %s", singer_mid, exc)
            return []
        return [self._to_song(s) for s in (getattr(resp, "song_list", None) or [])]

    async def get_singer_albums(
        self, singer_mid: str, *, limit: int = 50, page: int = 1
    ) -> list[Album]:
        """歌手全部专辑 (分页). AlbumBrief 字段: time_public/total_num/singer_name (单字符串)."""
        if not singer_mid:
            return []
        try:
            resp = await self.client.singer.get_album_list(singer_mid, num=limit, page=page)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_singer_albums 失败 (mid=%s): %s", singer_mid, exc)
            return []
        out: list[Album] = []
        for a in getattr(resp, "album_list", None) or []:
            mid = getattr(a, "mid", "") or ""
            if not mid:
                continue
            singer_name = getattr(a, "singer_name", "") or ""
            singers = [Singer(mid="", name=singer_name)] if singer_name else []
            out.append(
                Album(
                    mid=mid,
                    name=getattr(a, "name", "") or "",
                    singers=singers,
                    cover_url=_cover_url(mid, 300),
                    publish_date=getattr(a, "time_public", "") or "",
                    song_count=int(getattr(a, "total_num", 0) or 0),
                )
            )
        return out

    async def get_artist_detail(self, singer_mid: str, *, hot_song_limit: int = 50) -> ArtistDetail:
        # 同 get_album_detail: 上游 Request-like 对象需包成本地 coroutine 再 gather。
        async def _fetch_info() -> Any:
            return await self.client.singer.get_info(singer_mid)

        async def _fetch_hot_songs() -> Any:
            return await self.client.singer.get_tab_detail(
                singer_mid, TabType.SONG, 1, hot_song_limit
            )

        info_resp, tab_resp = await asyncio.gather(_fetch_info(), _fetch_hot_songs())
        # 0.6 HomepageHeaderResponse 含 singer (HomepageSinger), base_info
        singer_obj = getattr(info_resp, "singer", None) or getattr(info_resp, "base_info", None)
        name = getattr(singer_obj, "name", "") if singer_obj else ""
        avatar = (
            getattr(singer_obj, "singer_pic", "") or getattr(singer_obj, "avatar", "")
            if singer_obj
            else ""
        )
        s = Singer(
            mid=singer_mid,
            name=name or "",
            avatar_url=(avatar or "") or _singer_avatar_url(singer_mid),
        )

        # tab_resp 是 HomepageTabDetailResponse; SONG tab 内的歌曲在 song_tab.list
        raw_songs = self._extract_artist_hot_songs(tab_resp)
        artist = ArtistDetail(
            singer=s,
            description="",
            hot_songs=[self._to_song(sr) for sr in raw_songs],
        )
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

    async def get_lyric(self, mid: str, *, with_translation: bool = True) -> Lyric:
        """拉歌词: 优先逐字 QRC, 拿不到 (无权限/纯音乐/解密失败) 回退逐行 LRC."""
        no_qrc_key = f"lyric:no_qrc:{mid}"
        if self._memo_get(no_qrc_key) is not True:
            lines = await self._try_get_qrc(mid, with_translation=with_translation)
            if lines:
                return Lyric(
                    mid=mid,
                    lines=lines,
                    has_translation=any(ln.translation for ln in lines),
                )
            if lines == []:
                self._memo_put(no_qrc_key, True)
        return await self._get_lyric_lrc(mid, with_translation=with_translation)

    async def _try_get_qrc(self, mid: str, *, with_translation: bool) -> list[LyricLine] | None:
        """请求逐字 QRC; 请求失败返 None, 成功但无 QRC 返 []."""
        from qqmusic_api.algorithms import qrc_decrypt

        block = await self._bypass_post(
            "music.musichallSong.PlayLyricInfo",
            "GetPlayLyricInfo",
            {
                "crypt": 1,
                "lrc_t": 0,
                "qrc": 1,
                "qrc_t": 0,
                "roma": 0,
                "roma_t": 0,
                "trans": 1 if with_translation else 0,
                "trans_t": 0,
                "type": 1,
                "songMid": mid,
            },
            require_login=True,
        )
        if block is None:
            return None
        if not block:
            return []

        def _dec(field: str) -> str:
            if not field:
                return ""
            try:
                return qrc_decrypt(field)
            except Exception:
                return ""

        # QRC 逐字优先; 该歌无逐字时解出的是普通 LRC, 退回逐行解析
        lyric_text = _dec(block.get("lyric", "") or "")
        lines = parse_qrc(lyric_text) or parse_lrc(lyric_text)
        if not lines:
            return []

        trans_text = _dec(block.get("trans", "") or "")
        if trans_text:
            trans_by_ts = {ln.timestamp_ms: ln.text for ln in parse_lrc(trans_text)}
            # QRC 毫秒精度 vs 翻译 LRC 厘秒精度: 2061 vs 2060, 差 1-2ms
            trans_by_cs = {ts // 10: t for ts, t in trans_by_ts.items()}
            lines = [
                LyricLine(
                    timestamp_ms=ln.timestamp_ms,
                    text=ln.text,
                    translation=(
                        trans_by_ts.get(ln.timestamp_ms)
                        or trans_by_cs.get(ln.timestamp_ms // 10, "")
                    ),
                    words=ln.words,
                )
                for ln in lines
            ]
        return lines

    async def _get_lyric_lrc(self, mid: str, *, with_translation: bool) -> Lyric:
        """逐行 LRC: bypass crypt=0 拿 base64 明文 (QRC 不可用时的回退)."""
        import base64

        block = await self._bypass_post(
            "music.musichallSong.PlayLyricInfo",
            "GetPlayLyricInfo",
            {
                "crypt": 0,
                "lrc_t": 0,
                "qrc": 0,
                "qrc_t": 0,
                "roma": 0,
                "roma_t": 0,
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
        return Lyric(mid=mid, lines=lines, has_translation=bool(trans_text))

    # ------------------------------------------------------------------
    # 歌曲播放 URL (绕过库的 get_song_urls; 走自拼 vkey)
    # ------------------------------------------------------------------

    async def get_song_url(
        self,
        song_obj: Song,
        *,
        quality_preference: str = "balanced",
    ) -> SongUrl | None:
        """按音质偏好, 走 bypass vkey 路径拿可播完整 URL.

        全部降级档批量塞进单个 UrlGetVkey 请求 (1 次往返), 本地按偏好顺序挑
        第一个可播档 —— 旧实现按档串行降级最多 3 次往返, 是切歌延迟大头之一
        (issue #11). 实测响应保序回显 filename, 见 scripts/debug_vkey_batch.py.
        """
        order = self._QUALITY_PROFILES.get(
            quality_preference, self._QUALITY_PROFILES[self._DEFAULT_QUALITY]
        )
        fetched = await self._try_bypass_urls(
            song_obj.mid,
            order,
            media_mid=song_obj.media_mid,
        )
        failure_codes: dict[str, int] = {}
        for quality_label in order:
            url, vkey_result = fetched.get(quality_label, (None, None))
            if url:
                artists = " / ".join(s.name for s in song_obj.singers) or "未知歌手"
                album = f" [{song_obj.album_name}]" if song_obj.album_name else ""
                logger.info(
                    "命中 %s: %s — %s%s (mid=%s)",
                    quality_label,
                    song_obj.name,
                    artists,
                    album,
                    song_obj.mid,
                )
                return SongUrl(mid=song_obj.mid, url=url, quality=quality_label)
            if vkey_result is not None:
                failure_codes[quality_label] = vkey_result
        # mid + media_mid 让我们能快速本地复现 (诊断脚本只需这两项即可还原 filename);
        # vkey_result 一眼定性: 104003=无版权/不可下发 (灰色歌曲, 官方客户端同样不可播)
        codes = set(failure_codes.values())
        code_text = str(codes.pop()) if len(codes) == 1 else (str(failure_codes) or "无")
        logger.warning(
            "所有音质均不可下发: %s (mid=%s, media_mid=%s, pref=%s, vkey_result=%s)",
            song_obj.name,
            song_obj.mid,
            song_obj.media_mid or "",
            quality_preference,
            code_text,
        )
        return None

    async def _bypass_post(
        self,
        module: str,
        method: str,
        param: dict[str, Any],
        *,
        require_login: bool = False,
        timeout: float = 10,
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
            # 反风控 U1: curl_cffi 用官方浏览器 TLS 指纹 (JA3) + UA 发请求
            from curl_cffi import requests as creq

            r = creq.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                json=body,
                impersonate=self._IMPERSONATE,
                timeout=timeout,
            )
            return r.json()

        try:
            data = await asyncio.to_thread(_do)
        except Exception as exc:
            logger.warning("bypass %s.%s 请求异常: %s", module, method, exc)
            return None

        if require_login and self._payload_indicates_credential_expired(data):
            raise CredentialExpiredError("登录已过期，请重新登录")
        return data.get("req_0", {}).get("data", {}) or {}

    @staticmethod
    def _payload_indicates_credential_expired(payload: dict[str, Any]) -> bool:
        candidates = [payload, payload.get("req_0", {}) or {}]
        for item in candidates:
            code = item.get("code")
            message = str(
                item.get("message", "") or item.get("msg", "") or item.get("tips", "") or ""
            ).lower()
            if code in _CREDENTIAL_EXPIRED_CODES:
                return True
            if any(token in message for token in _CREDENTIAL_EXPIRED_TEXT_TOKENS):
                return True
        return False

    async def _try_bypass_urls(
        self,
        mid: str,
        quality_labels: Sequence[str],
        *,
        media_mid: str = "",
    ) -> dict[str, tuple[str | None, int | None]]:
        """vkey bypass 批量: 全部档位 filename 塞同一请求, 按档返回 (url, vkey_result 码).

        ct 实例生命周期内固定 (启动时从 _SAFE_CT_VALUES 随机). 成功档 (url, None);
        拒发档 url=None, 码透给调用方进 warning 日志 (104003=无版权/不可下发,
        真机实测灰色歌曲返回该码). 未知档位不进结果. 形状漂移 (非 dict 条目 /
        条数不齐 / 缺回显) 一律降级为该档 (None, None), 不抛.
        """
        file_mid = media_mid or mid
        known = [
            (label, self._QUALITY_FILE[label])
            for label in quality_labels
            if label in self._QUALITY_FILE
        ]
        if not known:
            return {}
        filenames = [f"{prefix}{file_mid}{file_mid}.{ext}" for _, (prefix, ext) in known]
        results: dict[str, tuple[str | None, int | None]] = {
            label: (None, None) for label, _ in known
        }

        data = await self._bypass_post(
            "music.vkey.GetVkey",
            "UrlGetVkey",
            {
                "filename": filenames,
                "guid": self._device_guid or uuid.uuid4().hex,
                "songmid": [mid] * len(filenames),
                "songtype": [0] * len(filenames),
            },
            require_login=True,
            timeout=self._VKEY_REQUEST_TIMEOUT_SEC,
        )
        if not data:
            logger.debug("vkey 空响应: mid=%s labels=%s", mid, list(quality_labels))
            return results

        midurlinfo = data.get("midurlinfo") or []
        if not midurlinfo:
            # vkey 接口未返回 midurlinfo, 一般是请求路径异常 (而非曲目不可下发)
            logger.debug(
                "vkey 缺 midurlinfo: mid=%s labels=%s data_keys=%s",
                mid,
                list(quality_labels),
                sorted(data.keys()),
            )
            return results

        # 对位策略 (review 加固): 正常响应每条都回显请求的 filename, 按 filename 精确
        # 对位 (最可靠, 见 scripts/debug_vkey_batch.py). 若有条目缺 filename 回显, 退化
        # 为按下标对位 (假设保序), 但要求条数与请求档数**完全一致** —— 否则无法可靠
        # 对位, 该批保持全部不可用. 避免旧实现"混合回显时 setdefault 撞键 / 无回显时
        # 把 A 档 purl 错安给 B 档"导致的静默音质错标.
        dict_entries = [e for e in midurlinfo if isinstance(e, dict)]
        all_echoed = bool(dict_entries) and all(e.get("filename") for e in dict_entries)
        if all_echoed:
            by_filename: dict[str, dict[str, Any]] = {}
            for entry in dict_entries:
                by_filename.setdefault(str(entry["filename"]), entry)
            pairs: list[tuple[str, str, dict[str, Any] | None]] = [
                (label, filename, by_filename.get(filename))
                for (label, _), filename in zip(known, filenames, strict=True)
            ]
        elif len(dict_entries) == len(filenames):
            pairs = [
                (label, filename, entry)
                for (label, _), filename, entry in zip(known, filenames, dict_entries, strict=True)
            ]
        else:
            logger.debug(
                "vkey 响应无法对位 (缺 filename 回显且条数不符): mid=%s 请求=%d 响应=%d",
                mid,
                len(filenames),
                len(dict_entries),
            )
            return results

        for label, filename, entry in pairs:
            if entry is None:
                continue
            purl = entry.get("purl", "") or ""
            if not purl:
                # 区域/版权/会员限制时 purl 置空, result 码标明原因 (104003=无版权).
                # DEBUG (而非 WARNING): 某些档失败是常态 (例如非 VIP 试 FLAC), 不应刷屏;
                # 全档失败时 get_song_url 的 warning 会带上这里的码.
                logger.debug(
                    "vkey purl 空: mid=%s quality=%s filename=%s entry=%s",
                    mid,
                    label,
                    filename,
                    entry,
                )
                raw_result = entry.get("result")
                try:
                    code = int(raw_result) if raw_result not in (None, "") else None
                except (TypeError, ValueError):
                    code = None
                results[label] = (None, code)
                continue
            # 返回真实 CDN https url：由 bridge 的 StreamProxy 用 curl_cffi 官方 TLS
            # 指纹 (impersonate) 拉流，经本机回环 http 喂给 FFmpeg。FFmpeg 自身的 TLS
            # 指纹会被 CDN 风控 (https→401/403)，故不让它直连；明文只在本机回环。
            results[label] = (f"https://isure.stream.qqmusic.qq.com/{purl}", None)
        return results

    # ------------------------------------------------------------------
    # 用户库 (我喜欢 + 我创建的歌单)
    # ------------------------------------------------------------------

    # 0.6 QQ "我喜欢" 歌单的固定 dirid (所有账号都是 201)
    FAV_DIRID = 201

    async def get_liked_songs(self, *, limit: int = 500) -> list[Song]:
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
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
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

    async def get_recommend_playlists(self, *, limit: int = 8) -> list[Playlist]:
        """推荐歌单 (首页 Featured Playlists). 10 分钟内存 cache."""
        cached = self._memo_get("recommend_playlists")
        if cached is not None:
            return cached[:limit]

        try:
            data = await self._bypass_post(
                "music.playlist.PlaylistSquare",
                "GetRecommendFeed",
                {"From": 0, "Size": limit},
                timeout=5,
            )
        except Exception as exc:
            logger.warning("get_recommend_songlist 失败: %s", exc)
            return []
        if not data:
            return []
        out = [
            self._to_recommend_playlist(item)
            for item in (data.get("List", None) or data.get("songlists", None) or [])[:limit]
        ]
        self._memo_put("recommend_playlists", out)
        return out

    async def get_top_categories(self, *, limit_per_group: int | None = None) -> list[TopList]:
        """所有排行榜入口扁平化 (各 group 拼起来). 10 分钟内存 cache.

        直接走 musicu.fcg 线程请求, 避开 qqmusic-api async recommend/top
        接口在部分环境下的 CPU 空转问题.
        """
        cached = self._memo_get("top_categories")
        if cached is not None:
            return cached

        try:
            data = await self._bypass_post(
                "music.musicToplist.Toplist",
                "GetAll",
                {},
                timeout=5,
            )
        except Exception as exc:
            logger.warning("get_top_categories 失败: %s", exc)
            return []
        if not data:
            return []
        out: list[TopList] = []
        for g in data.get("group", None) or []:
            tlist = self._g(g, "toplist", None) or []
            if limit_per_group is not None:
                tlist = tlist[:limit_per_group]
            for tl in tlist:
                out.append(self._to_top_list(tl))
        self._memo_put("top_categories", out)
        return out

    async def get_top_detail(self, top_id: int, *, limit: int = 100) -> Playlist:
        """单个排行榜详情, 复用 Playlist 模型.

        注: 某些榜本身服务端无 intro (如 tid=135 巅峰潮流榜, 编辑榜没规则文本),
        这不是 ct 风控. 调用方需对 description 容空.
        """
        try:
            data = await self._bypass_post(
                "music.musicToplist.Toplist",
                "GetDetail",
                {
                    "topId": top_id,
                    "offset": 0,
                    "num": limit,
                    "withTags": True,
                },
                timeout=5,
            )
        except Exception as exc:
            logger.warning("get_top_detail 失败 (top_id=%s): %s", top_id, exc)
            return Playlist(pid=str(top_id), name="榜单不可用")
        if not data:
            return Playlist(pid=str(top_id), name="榜单不可用")

        info = data.get("data", {}) or data
        songs_raw = data.get("songInfoList", None) or info.get("songInfoList", None) or []
        if not songs_raw:
            songs_raw = info.get("song", None) or []
        return Playlist(
            pid=str(top_id),
            name=(self._g(info, "name", None) or self._g(info, "title", "") or ""),
            cover_url=(
                self._g(info, "front_pic_url", None)
                or self._g(info, "frontPicUrl", None)
                or self._g(info, "head_pic_url", None)
                or self._g(info, "headPicUrl", "")
                or ""
            ),
            description=_clean_text(self._g(info, "intro", ""), max_len=400),
            creator="",
            song_count=int(self._g(info, "total_num", None) or self._g(info, "totalNum", 0) or 0),
            play_count=int(self._g(info, "listen_num", None) or self._g(info, "listenNum", 0) or 0),
            songs=[self._to_song_from_top_raw(s) for s in songs_raw],
        )

    async def get_recommend_new_songs(self, *, limit: int = 12) -> list[Song]:
        """新歌速递 (首页 New Releases). 10 分钟内存 cache."""
        cached = self._memo_get("recommend_new_songs")
        if cached is not None:
            return cached[:limit]

        try:
            data = await self._bypass_post(
                "newsong.NewSongServer",
                "get_new_song_info",
                {"type": 5},
                timeout=5,
            )
        except Exception as exc:
            logger.warning("get_recommend_newsong 失败: %s", exc)
            return []
        if not data:
            return []
        songs_raw = data.get("songlist", None) or data.get("songs", None) or []
        out = [self._to_song(s) for s in songs_raw[:limit]]
        self._memo_put("recommend_new_songs", out)
        return out

    async def get_daily_recommend_songs(self, *, limit: int = 30) -> list[Song]:
        """每日推荐歌曲. 优先取雷达推荐并补足到 limit, 失败时回退猜你喜欢."""
        if limit <= 0:
            return []

        cache_key = f"daily_recommend_songs:{limit}"
        cached = self._memo_get(cache_key)
        if cached is not None:
            return cached[:limit]

        out: list[Song] = []
        seen: set[str] = set()

        try:
            page = 1
            while len(out) < limit and page <= 10:
                data = await self._bypass_post(
                    "music.recommend.TrackRelationServer",
                    "GetRadarSong",
                    {
                        "Page": page,
                        "ReqType": 0,
                        "FavSongs": [],
                        "EntranceSongs": [],
                    },
                    require_login=True,
                    timeout=5,
                )
                songs_raw = (
                    (data or {}).get("VecSongs", None) or (data or {}).get("songs", None) or []
                )
                for raw in songs_raw:
                    song = self._to_radar_song(raw)
                    if not song.mid or song.mid in seen:
                        continue
                    seen.add(song.mid)
                    out.append(song)
                    if len(out) >= limit:
                        break
                has_more = bool(
                    (data or {}).get("HasMore", None) or (data or {}).get("has_more", False)
                )
                if not songs_raw or not has_more:
                    break
                page += 1
        except Exception as exc:
            logger.warning("get_radar_recommend 失败: %s", exc)

        if not out:
            try:
                data = await self._bypass_post(
                    "music.radioProxy.MbTrackRadioSvr",
                    "get_radio_track",
                    {
                        "id": 99,
                        "num": limit,
                        "from": 0,
                        "scene": 0,
                        "song_ids": [],
                    },
                    require_login=True,
                    timeout=5,
                )
                songs_raw = (
                    (data or {}).get("tracks", None) or (data or {}).get("songs", None) or []
                )
                for raw in songs_raw:
                    song = self._to_song(raw)
                    if not song.mid or song.mid in seen:
                        continue
                    seen.add(song.mid)
                    out.append(song)
                    if len(out) >= limit:
                        break
            except Exception as exc:
                logger.warning("get_guess_recommend 失败: %s", exc)

        self._memo_put(cache_key, out)
        return out[:limit]

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

    async def get_search_suggest(self, keyword: str, *, limit: int = 10) -> list[str]:
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
            resp = await self.client.user.get_created_songlist(int(cred.musicid), credential=cred)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_created_songlist 失败: %s", exc)
            return []
        out: list[Playlist] = []
        for p in resp.playlists or []:
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
        """收藏的专辑.

        绕过 qqmusic-api 0.6.1 的 ``UserFavAlbumResponse``：该模型用 jsonpath
        ``$.v_list[*]`` 取列表，当用户只有 0/1 个专辑时 ``v_list`` 可能是单个
        dict 而非数组，pydantic 直接校验失败、整页拉不到。这里走 ``_bypass_post``
        取原始 data，手动容错解析（``v_list`` 为 dict / list / 缺失都能处理）。
        """
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return []
        data = await self._bypass_post(
            "music.musicasset.AlbumFavRead",
            "CgiGetAlbumFavInfo",
            {"euin": cred.encrypt_uin, "offset": 0, "size": 200},
            require_login=True,
        )
        return self._parse_fav_albums(data)

    @staticmethod
    def _parse_fav_albums(data: dict[str, Any] | None) -> list[Album]:
        raw = (data or {}).get("v_list")
        if isinstance(raw, dict):
            # 单个专辑时 API 直接返回 dict；或 index→album 的映射
            items = (
                [raw]
                if ("mid" in raw or "id" in raw)
                else [v for v in raw.values() if isinstance(v, dict)]
            )
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        out: list[Album] = []
        for a in items:
            if not isinstance(a, dict):
                continue
            mid = str(a.get("mid", "") or "")
            if not mid:
                continue
            singers: list[Singer] = []
            for s in a.get("v_singer") or a.get("singer") or []:
                if isinstance(s, dict):
                    singers.append(
                        Singer(
                            mid=str(s.get("mid", "") or ""),
                            name=str(s.get("name", "") or ""),
                        )
                    )
            out.append(
                Album(
                    mid=mid,
                    name=str(a.get("name", "") or ""),
                    singers=singers,
                    cover_url=_cover_url(mid, 300),
                    publish_date="",
                    song_count=int(a.get("songnum", 0) or 0),
                )
            )
        return out

    # 服务端 PlaylistFavRead 单页 cap = 50, 必须分页拉.
    _FAV_SONGLIST_PAGE_SIZE = 50

    async def get_fav_songlist(self) -> list[Playlist]:
        """收藏的外部歌单 (区别于 ``get_my_playlists`` 的自建歌单).

        走 0.6.1 库方法 ``client.user.get_fav_songlist`` 分页拉到 ``hasmore=0``.
        ``SongList`` 基类用 ``AliasChoices`` 识别服务端 ``tid``/``name``/``logo``
        等字段名变体, pydantic 解析正常. ``v_list`` 在 0/1 项时变 dict 触发
        ``ValidationError`` 时回退 ``_bypass_post``, 沿用 fav_albums 同款兜底.
        """
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return []
        try:
            return await self._fetch_fav_songlist_via_library(cred)
        except CredentialExpiredError:
            raise
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            # 仅 pydantic 校验失败时退 bypass (例如 0/1 项 v_list 为 dict).
            from pydantic import ValidationError

            if not isinstance(exc, ValidationError):
                logger.warning("get_fav_songlist 库方法失败: %s", exc)
                return []
            logger.warning("库 get_fav_songlist pydantic 校验失败, 退 bypass: %s", exc)
            return await self._fetch_fav_songlist_via_bypass(cred)

    async def _fetch_fav_songlist_via_library(self, cred: Credential) -> list[Playlist]:
        out: list[Playlist] = []
        page = 1
        while True:
            resp = await self.client.user.get_fav_songlist(
                cred.encrypt_uin,
                page=page,
                num=self._FAV_SONGLIST_PAGE_SIZE,
                credential=cred,
            )
            items = getattr(resp, "playlists", None) or []
            if not items:
                break
            for item in items:
                playlist = self._to_fav_playlist(item)
                if playlist is not None:
                    out.append(playlist)
            if not getattr(resp, "hasmore", 0):
                break
            page += 1
        return out

    async def _fetch_fav_songlist_via_bypass(self, cred: Credential) -> list[Playlist]:
        data = await self._bypass_post(
            "music.musicasset.PlaylistFavRead",
            "CgiGetPlaylistFavInfo",
            {"uin": cred.encrypt_uin, "offset": 0, "size": self._FAV_SONGLIST_PAGE_SIZE},
            require_login=True,
        )
        return self._parse_fav_songlists(data)

    @staticmethod
    def _to_fav_playlist(raw: Any) -> Playlist | None:
        """库 ``UserFavSonglistItem`` (pydantic) → 我们的 ``Playlist`` dataclass."""
        pid = str(QuaverService._g(raw, "id", 0) or 0)
        if not pid or pid == "0":
            return None
        return Playlist(
            pid=pid,
            name=QuaverService._g(raw, "title", "") or "",
            cover_url=QuaverService._g(raw, "picurl", "") or "",
            description=QuaverService._g(raw, "desc", "") or "",
            creator=QuaverService._g(raw, "nickname", "") or "",
            song_count=int(QuaverService._g(raw, "songnum", 0) or 0),
            play_count=int(QuaverService._g(raw, "listennum", 0) or 0),
        )

    @staticmethod
    def _parse_fav_songlists(data: dict[str, Any] | None) -> list[Playlist]:
        """bypass 兜底解析: 服务端实际返回 ``tid``/``name``/``logo`` 字段名 (非 id/title/picurl).

        探针实测: ``v_list`` 项是 ``{"tid", "name", "logo", "songnum", "nickname", ...}``.
        同时兼容老 ``id``/``title``/``picurl`` 键名以防服务端切换.
        """
        raw = (data or {}).get("v_list")
        if isinstance(raw, dict):
            items = (
                [raw]
                if any(k in raw for k in ("tid", "id", "dissid", "name", "title"))
                else [v for v in raw.values() if isinstance(v, dict)]
            )
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        out: list[Playlist] = []
        for p in items:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("tid", "") or p.get("id", "") or p.get("dissid", "") or "")
            if not pid or pid == "0":
                continue
            out.append(
                Playlist(
                    pid=pid,
                    name=str(
                        p.get("name", "") or p.get("title", "") or p.get("dissname", "") or ""
                    ),
                    cover_url=str(p.get("logo", "") or p.get("picurl", "") or ""),
                    description=str(p.get("desc", "") or ""),
                    creator=str(p.get("nickname", "") or ""),
                    song_count=int(p.get("songnum", 0) or 0),
                    play_count=int(p.get("listennum", 0) or 0),
                )
            )
        return out

    async def get_similar_songs(self, songid: int) -> list[Song]:
        """歌曲详情 popup 用: 'XX 听过的也在听' 的相似歌曲.

        song.get_similar_song 返回多 SimilarSongGroup, 每组有 title_template/title_content +
        song 列表 (完整 0.6 Song pydantic). 拍扁所有组 + 按 mid 去重 (跨组重复保留首次).
        公开接口不需 credential. 凭据过期类异常透传; 其它异常降级为 [].
        """
        if not songid:
            return []
        try:
            resp = await self.client.song.get_similar_song(songid)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_similar_song 失败 (songid=%s): %s", songid, exc)
            return []
        out: list[Song] = []
        seen: set[str] = set()
        for group in getattr(resp, "song", None) or []:
            for s in getattr(group, "song", None) or []:
                song = self._to_song(s)
                if not song.mid or song.mid in seen:
                    continue
                seen.add(song.mid)
                out.append(song)
        return out

    async def get_related_songlists(self, songid: int) -> list[Playlist]:
        """歌曲详情 popup 用: 包含此曲或相关主题的歌单.

        song.get_related_songlist 返回 RelatedPlaylist 列表, 字段
        id/title/picurl/desc/songnum/listennum/creator. 公开接口.
        """
        if not songid:
            return []
        try:
            resp = await self.client.song.get_related_songlist(songid)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_related_songlist 失败 (songid=%s): %s", songid, exc)
            return []
        out: list[Playlist] = []
        for p in getattr(resp, "songlist", None) or []:
            pid = str(getattr(p, "id", 0) or 0)
            if not pid or pid == "0":
                continue
            out.append(
                Playlist(
                    pid=pid,
                    name=getattr(p, "title", "") or "",
                    cover_url=getattr(p, "picurl", "") or "",
                    description=getattr(p, "desc", "") or "",
                    creator=getattr(p, "creator", "") or "",
                    song_count=int(getattr(p, "songnum", 0) or 0),
                    play_count=int(getattr(p, "listennum", 0) or 0),
                )
            )
        return out

    async def get_song_related(self, songid: int) -> tuple[list[Song], list[Playlist]]:
        """并发拉 similar + related, 二元组返回; 一边挂另一边照常.

        凭据过期类异常透传 (let controller 走清缓存路径); 其它错误降级为空列表.
        """
        if not songid:
            return [], []
        similar, related = await asyncio.gather(
            self.get_similar_songs(songid),
            self.get_related_songlists(songid),
            return_exceptions=True,
        )
        for exc in (similar, related):
            if isinstance(exc, BaseException) and is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
        similar_list = similar if isinstance(similar, list) else []
        related_list = related if isinstance(related, list) else []
        if isinstance(similar, BaseException):
            logger.warning("get_song_related similar 端失败 (songid=%s): %s", songid, similar)
        if isinstance(related, BaseException):
            logger.warning("get_song_related related 端失败 (songid=%s): %s", songid, related)
        return similar_list, related_list

    # ------------------------------------------------------------------
    # 歌曲附加信息 (语种 / 流派 / 制作人, 第二档 2.4)
    # ------------------------------------------------------------------

    # 标签接口噪声过滤: 这些 tag_type / species 是"实时统计 / 营销"类, 不适合做"歌曲信息"展示
    _LABEL_NOISE_TYPES = frozenset({20, 21, 22, 23, 24, 25, 26, 27, 29, 30, 31})
    _LABEL_NOISE_SPECIES = frozenset({3, 4, 5})

    async def get_song_info(self, song_mid: str, song_id: int = 0) -> SongInfo:
        """歌曲附加信息: 并发拉 detail / labels / producer, 合并为 SongInfo.

        任一接口失败降级为对应空字段, 不抛 (跟相似/相关行为一致).
        凭据过期类异常透传, 让 controller 走清缓存路径.
        """
        if not song_mid and not song_id:
            return SongInfo()

        # detail 接口 mid/id 都能用; labels/producer 必须 int songid (0 也能调, 接口返空)
        detail_arg: int | str = song_id if song_id else song_mid

        detail, labels, producer = await asyncio.gather(
            self._safe_call_song_detail(detail_arg),
            self._safe_call_song_labels(song_id),
            self._safe_call_song_producer(song_id if song_id else song_mid),
            return_exceptions=True,
        )
        for exc in (detail, labels, producer):
            if isinstance(exc, BaseException) and is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc

        info = SongInfo()
        if detail is not None and not isinstance(detail, BaseException):
            info.language = self._first_content_value(getattr(detail, "lan", None))
            info.genre = self._first_content_value(getattr(detail, "genre", None))
            info.company = self._first_content_value(getattr(detail, "company", None))
            info.publish_time = self._first_content_value(getattr(detail, "pub_time", None))
            info.intro = self._first_content_value(getattr(detail, "intro", None))
        if labels is not None and not isinstance(labels, BaseException):
            info.tags = self._filter_song_labels(getattr(labels, "labels", None) or [])
        if producer is not None and not isinstance(producer, BaseException):
            info.producers = self._collect_producer_groups(getattr(producer, "data", None) or [])
        return info

    async def _safe_call_song_detail(self, value: int | str) -> Any | None:
        try:
            return await self.client.song.get_detail(value)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise
            logger.warning("get_song_info detail 失败 (value=%s): %s", value, exc)
            return None

    async def _safe_call_song_labels(self, songid: int) -> Any | None:
        if not songid:
            return None
        try:
            return await self.client.song.get_labels(songid)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise
            logger.warning("get_song_info labels 失败 (songid=%s): %s", songid, exc)
            return None

    async def _safe_call_song_producer(self, value: int | str) -> Any | None:
        try:
            return await self.client.song.get_producer(value)
        except Exception as exc:
            if is_credential_expired_error(exc):
                raise
            logger.warning("get_song_info producer 失败 (value=%s): %s", value, exc)
            return None

    @staticmethod
    def _first_content_value(items: Any) -> str:
        if not items:
            return ""
        first = items[0]
        return getattr(first, "value", "") or ""

    # 单个 chip 文本上限 (服务端会把多个奖项用 | / \n 拼在一条; UI chip 撑不下)
    _LABEL_MAX_LEN = 28

    @classmethod
    def _filter_song_labels(cls, labels: list[Any]) -> list[str]:
        """过滤噪声标签 + 把 | / \\n 拼接的多奖项拆成独立 tag 避免单 chip 过长."""
        out: list[str] = []
        for label in labels:
            txt = (getattr(label, "tag_txt", "") or "").strip()
            if not txt:
                continue
            type_ = int(getattr(label, "tag_type", 0) or 0)
            species = int(getattr(label, "species", 0) or 0)
            if type_ in cls._LABEL_NOISE_TYPES or species in cls._LABEL_NOISE_SPECIES:
                continue
            # 服务端有时用 | 或换行把多奖项 / 多榜单拼一条; 拆成独立 chip
            parts = [p.strip() for p in re.split(r"[|\n]+", txt) if p.strip()]
            for part in parts:
                if part.isdigit():
                    continue
                if len(part) > cls._LABEL_MAX_LEN:
                    continue  # 单条仍过长 (奖项全名带年份) 直接丢, 不强塞 chip
                if part not in out:
                    out.append(part)
        return out

    @staticmethod
    def _collect_producer_groups(raw_groups: list[Any]) -> list[ProducerGroup]:
        out: list[ProducerGroup] = []
        for g in raw_groups:
            title = getattr(g, "title", "") or ""
            producers = getattr(g, "producers", None) or []
            names = [getattr(p, "name", "") or "" for p in producers]
            names = [n for n in names if n]
            if title and names:
                out.append(ProducerGroup(title=title, names=names))
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
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("get_follow_singers 失败: %s", exc)
            return []
        out: list[Singer] = []
        for s in getattr(resp, "users", None) or []:
            out.append(
                Singer(
                    mid=getattr(s, "mid", "") or "",
                    name=getattr(s, "name", "") or "",
                    avatar_url=getattr(s, "avatar_url", "") or "",
                )
            )
        return out

    async def get_user_profile(self) -> UserProfile | None:
        """登录账号画像 (昵称 / 头像 / VIP 种类), 供侧栏身份区.

        并发拉 ``get_homepage`` (昵称 / 头像) 与 ``get_vip_info`` (VIP 身份块,
        上游 #258 起建模); 任一失败不挡另一半, 双失败返 None, 凭据过期统一
        抛 :class:`CredentialExpiredError` 交 ServiceController 处理.
        """
        cred = self._effective_credential()
        if cred is None or not cred.encrypt_uin:
            return None

        # 库 API 是同步方法, 返回 awaitable 但 unhashable 的 Request 对象
        # (pydantic __eq__ 无 __hash__); 直接塞 gather 会在内部去重时炸
        # TypeError, 必须包成本地 coroutine (真机踩过, 见回归测试).
        async def _fetch_homepage() -> Any:
            return await self.client.user.get_homepage(cred.encrypt_uin, credential=cred)

        async def _fetch_vip_info() -> Any:
            return await self.client.user.get_vip_info(credential=cred)

        homepage, vip_info = await asyncio.gather(
            _fetch_homepage(),
            _fetch_vip_info(),
            return_exceptions=True,
        )
        for result in (homepage, vip_info):
            if isinstance(result, BaseException) and is_credential_expired_error(result):
                raise CredentialExpiredError("登录已过期，请重新登录") from result
        if isinstance(homepage, BaseException):
            logger.warning("get_homepage 失败: %s", homepage)
            homepage = None
        if isinstance(vip_info, BaseException):
            logger.warning("get_vip_info 失败: %s", vip_info)
            vip_info = None
        if homepage is None and vip_info is None:
            return None
        return self._parse_user_profile(homepage, vip_info)

    @staticmethod
    def _parse_user_profile(homepage: Any, vip_info: Any) -> UserProfile:
        """纯函数: 两个响应 (可各自为 None) 合成 UserProfile, 缺字段一律默认空.

        徽章优先级 SVIP > 豪华绿钻 > 绿钻 > 无; 非会员抑制服务端等级 icon
        (不显示负面标签). 年费标志随种类取 huge_year_flag / yearflag.
        """
        base = getattr(homepage, "base_info", None)
        nickname = _clean_text(getattr(base, "name", "") or "", max_len=40)
        avatar_url = str(getattr(base, "avatar", "") or "")

        identity = getattr(vip_info, "identity", None)
        svip = int(getattr(vip_info, "svip", 0) or 0)
        huge_vip = int(getattr(identity, "huge_vip", 0) or 0)
        vip = int(getattr(identity, "vip", 0) or 0)
        year_flag = int(getattr(identity, "year_flag", 0) or 0)
        huge_year_flag = int(getattr(identity, "huge_year_flag", 0) or 0)

        if svip:
            kind = "svip"
            is_year = bool(huge_year_flag or year_flag)
        elif huge_vip:
            kind = "hugevip"
            is_year = bool(huge_year_flag)
        elif vip:
            kind = "vip"
            is_year = bool(year_flag)
        else:
            kind = ""
            is_year = False
        icon = str(getattr(identity, "icon", "") or "") if kind else ""

        return UserProfile(
            nickname=nickname,
            avatar_url=avatar_url,
            vip_kind=kind,
            is_year_vip=is_year,
            vip_icon_url=icon,
        )

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
            if is_credential_expired_error(exc):
                raise CredentialExpiredError("登录已过期，请重新登录") from exc
            logger.warning("unlike_song API 失败: %s", exc)
            return False

    # ------------------------------------------------------------------
    # 凭据持久化
    # ------------------------------------------------------------------

    def load_cached_credential_sync(self) -> Credential | None:
        """同步从 keyring 加载缓存凭据 (供启动期首帧前置 authed; 不联网, 不需事件循环)."""
        blob = _load_credential_blob()
        if not blob:
            return None
        try:
            return _credential_from_dict(json.loads(blob))
        except Exception as exc:
            logger.warning("解析缓存凭据失败: %s", exc)
            return None

    async def _get_cached_credential(self) -> Credential | None:
        return self.load_cached_credential_sync()

    async def save_credential(self) -> None:
        cred = self._effective_credential()
        if not cred or not cred.musickey:
            return
        blob = json.dumps(_credential_to_dict(cred), ensure_ascii=False)
        _save_credential_blob(blob)
        logger.info("凭据已保存到 keyring")

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
            mid=QuaverService._g(raw, "mid", None) or QuaverService._g(raw, "singerMID", "") or "",
            name=QuaverService._g(raw, "name", None)
            or QuaverService._g(raw, "singerName", "")
            or "",
            avatar_url=QuaverService._g(raw, "pic", None)
            or QuaverService._g(raw, "singerPic", "")
            or "",
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
            QuaverService._g(raw, "mid", None) or QuaverService._g(raw, "albummid", "") or ""
        )
        cover = QuaverService._g(raw, "pic", None) or _cover_url(album_mid, 300)
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
        pid = str(QuaverService._g(raw, "id", None) or QuaverService._g(raw, "dissid", "") or "")
        name = QuaverService._g(raw, "title", None) or QuaverService._g(raw, "dissname", "") or ""
        return Playlist(
            pid=pid,
            name=name,
            cover_url=QuaverService._g(raw, "picurl", None)
            or QuaverService._g(raw, "logo", "")
            or "",
            description=QuaverService._g(raw, "desc", "") or "",
            creator=QuaverService._g(raw, "nickname", "") or "",
            song_count=int(QuaverService._g(raw, "songnum", 0) or 0),
            play_count=int(QuaverService._g(raw, "listennum", 0) or 0),
        )

    @staticmethod
    def _to_recommend_playlist(raw: Any) -> Playlist:
        """首页推荐歌单 raw dict -> Playlist."""
        playlist = QuaverService._g(raw, "Playlist", None) or raw
        basic = QuaverService._g(playlist, "basic", None) or playlist
        cover = QuaverService._g(basic, "cover", None) or {}
        creator = QuaverService._g(basic, "creator", None) or {}
        return Playlist(
            pid=str(
                QuaverService._g(basic, "tid", None) or QuaverService._g(basic, "id", "") or ""
            ),
            name=QuaverService._g(basic, "title", "") or "",
            cover_url=(
                QuaverService._g(cover, "default_url", None)
                or QuaverService._g(cover, "small_url", None)
                or QuaverService._g(basic, "picurl", "")
                or ""
            ),
            description=QuaverService._g(basic, "desc", "") or "",
            creator=(
                QuaverService._g(creator, "nick", None)
                or QuaverService._g(basic, "creator_nick", "")
                or ""
            ),
            song_count=int(
                QuaverService._g(basic, "song_cnt", None)
                or QuaverService._g(basic, "songnum", 0)
                or 0
            ),
            play_count=int(
                QuaverService._g(basic, "play_cnt", None)
                or QuaverService._g(basic, "listennum", 0)
                or 0
            ),
        )

    @staticmethod
    def _to_top_list(raw: Any) -> TopList:
        """排行榜入口 raw dict / pydantic -> TopList."""
        return TopList(
            top_id=int(QuaverService._g(raw, "topId", None) or QuaverService._g(raw, "id", 0) or 0),
            name=(QuaverService._g(raw, "title", None) or QuaverService._g(raw, "name", "") or ""),
            cover_url=(
                QuaverService._g(raw, "frontPicUrl", None)
                or QuaverService._g(raw, "front_pic_url", None)
                or QuaverService._g(raw, "headPicUrl", None)
                or QuaverService._g(raw, "head_pic_url", "")
                or ""
            ),
            intro=_clean_text(QuaverService._g(raw, "intro", ""), max_len=80),
            total_num=int(
                QuaverService._g(raw, "totalNum", None)
                or QuaverService._g(raw, "total_num", 0)
                or 0
            ),
        )

    @staticmethod
    def _to_radar_song(raw: Any) -> Song:
        """雷达推荐返回 VecSongs[*].Track, 兼容直接 song dict."""
        track = QuaverService._g(raw, "Track", None) or raw
        return QuaverService._to_song(track)

    @staticmethod
    def _to_song_from_top_raw(raw: Any) -> Song:
        """排行榜详情优先使用 songInfoList; 简表 song 字段做降级."""
        if QuaverService._g(raw, "mid", ""):
            return QuaverService._to_song(raw)
        singer_mid = QuaverService._g(raw, "singerMid", "") or ""
        singer_name = QuaverService._g(raw, "singerName", "") or ""
        album_mid = QuaverService._g(raw, "albumMid", "") or ""
        cover_url = QuaverService._g(raw, "cover", "") or ""
        return Song(
            mid=QuaverService._g(raw, "songMid", "") or "",
            id=int(QuaverService._g(raw, "songId", None) or QuaverService._g(raw, "id", 0) or 0),
            name=(QuaverService._g(raw, "title", None) or QuaverService._g(raw, "name", "") or ""),
            singers=[Singer(mid=singer_mid, name=singer_name)] if singer_mid or singer_name else [],
            album_mid=album_mid,
            cover_url=cover_url or (_cover_url(album_mid, 300) if album_mid else ""),
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
