"""QQ 音乐服务层 (基于 qqmusic-api-python 0.4.1).

0.4.1 是模块级函数 API (而非 v0.6 的 Client 类); 经实测它能用同一份 cookie
拿到完整 MP3_128 / MP3_320 / OGG_192 / FLAC URL (新版 0.5/0.6 服务端拒下发).

设计要点:
- 没有 Client 对象, service 只持有 Credential
- get_song_urls 返回 {mid: full_url} (URL 自带 host + vkey), 不需要 CDN 探测
- 凭据 Credential 是普通 dataclass, 持久化用 asdict (兼容 v0.6 残留字段)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from qqmusic_api import Credential, login, search, song
from qqmusic_api.login import QRCodeLoginEvents, QRLoginType
from qqmusic_api.search import SearchType
from qqmusic_api.song import SongFileType

from .models import Album, Lyric, Playlist, Singer, Song, SongUrl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- helpers


def _cover_url(album_mid: str, size: int = 300) -> str:
    """拼 QQ 音乐封面 URL (0.4.1 raw response 没现成 cover_url 方法)."""
    if not album_mid:
        return ""
    return f"https://y.qq.com/music/photo_new/T002R{size}x{size}M000{album_mid}.jpg"


def _credential_from_dict(d: dict[str, Any]) -> Credential:
    """从 dict 构造 Credential; 未知字段进 extra_fields (兼容 v0.6 残留)."""
    known = set(Credential.__dataclass_fields__.keys()) - {"extra_fields"}
    base = {k: v for k, v in d.items() if k in known}
    extra = {k: v for k, v in d.items() if k not in known}
    return Credential(**base, extra_fields=extra)


def _credential_to_dict(c: Credential) -> dict[str, Any]:
    """Credential → dict, extra_fields 展开回顶层."""
    d = asdict(c)
    extra = d.pop("extra_fields", None) or {}
    d.update(extra)
    return d


# ---------------------------------------------------------------------- service


@dataclass
class QuaverService:
    """QQ 音乐 API 门面 / 服务层 (qqmusic-api 0.4.1).

    所有 API 通过 module-level 函数 (login.*, search.*, song.*), 把 credential
    作为参数传下去. service 只是个聚合点 + 凭据持有者.
    """

    credential: Credential | None = None

    # 登录回调: 通知 UI 展示二维码图片
    on_qrcode: Callable[[bytes, str], None] | None = None

    # 完整音质降级顺序: VIP 优先拿无损/高码, 免费档兜底
    _QUALITY_ORDER = (
        SongFileType.FLAC,       # 无损 (VIP)
        SongFileType.MP3_320,    # 高品 320k (VIP)
        SongFileType.OGG_192,    # HQ (OGG 192k)
        SongFileType.MP3_128,    # 标准 128k (免费)
    )

    # ------------------------------------------------------------------
    # 生命周期 (0.4.1 没 client 对象, connect/disconnect 是 no-op,
    # 保留方法让 controller 调用兼容)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "QuaverService":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        logger.info("QQMusic 服务初始化 (qqmusic-api 0.4.1)")

    async def disconnect(self) -> None:
        logger.info("QQMusic 服务断开")

    @property
    def is_authenticated(self) -> bool:
        """有 credential 且带 musickey 才算登录."""
        return self.credential is not None and bool(self.credential.musickey)

    async def get_credential(self) -> Credential | None:
        return self.credential

    async def set_credential(self, cred: Credential | None) -> None:
        self.credential = cred

    def set_credential_sync(self, cred: Credential | None) -> None:
        self.credential = cred

    # ------------------------------------------------------------------
    # 登录 — 二维码流程
    # ------------------------------------------------------------------

    async def login_by_qrcode(
        self, login_type: QRLoginType = QRLoginType.QQ
    ) -> bool:
        """二维码登录; 完成后凭据存到 self.credential."""
        qr = await login.get_qrcode(login_type)
        if self.on_qrcode:
            self.on_qrcode(qr.data, qr.qr_type.name.lower())
        logger.info("二维码已获取 (类型: %s)", qr.qr_type.name)

        import anyio

        while True:
            event, cred = await login.check_qrcode(qr)
            if event == QRCodeLoginEvents.DONE:
                assert cred is not None
                self.credential = cred
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
        """检查凭据是否过期; 无凭据视为过期."""
        if not self.credential:
            return True
        try:
            return await login.check_expired(self.credential)
        except Exception as exc:
            logger.warning("check_expired 失败: %s", exc)
            return True

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    async def search_songs(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Song]:
        """搜索歌曲."""
        raw_list = await search.search_by_type(
            keyword=keyword,
            search_type=SearchType.SONG,
            num=limit,
            page=page,
            highlight=False,
        )
        return [self._to_song(item) for item in raw_list]

    async def search_singers(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Singer]:
        """搜索歌手."""
        raw_list = await search.search_by_type(
            keyword=keyword,
            search_type=SearchType.SINGER,
            num=limit,
            page=page,
            highlight=False,
        )
        return [self._to_singer(item) for item in raw_list]

    async def search_albums(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Album]:
        """搜索专辑."""
        raw_list = await search.search_by_type(
            keyword=keyword,
            search_type=SearchType.ALBUM,
            num=limit,
            page=page,
            highlight=False,
        )
        return [self._to_album_brief(item) for item in raw_list]

    async def search_playlists(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Playlist]:
        """搜索歌单."""
        raw_list = await search.search_by_type(
            keyword=keyword,
            search_type=SearchType.SONGLIST,
            num=limit,
            page=page,
            highlight=False,
        )
        return [self._to_playlist_brief(item) for item in raw_list]

    async def search(
        self, keyword: str, *, page: int = 1, limit: int = 30
    ) -> list[Song]:
        """兼容别名 = search_songs."""
        return await self.search_songs(keyword, page=page, limit=limit)

    # ------------------------------------------------------------------
    # 歌曲播放
    # ------------------------------------------------------------------

    async def get_song_url(self, song_obj: Song) -> SongUrl | None:
        """按音质降级顺序拿可播 URL; 全失败返 None.

        0.4.1 的 song.get_song_urls 直接返回 {mid: full_url}, URL 自带
        host + vkey, 直接给 GStreamer 即可.
        """
        for ft in self._QUALITY_ORDER:
            try:
                result = await song.get_song_urls(
                    mid=[song_obj.mid],
                    file_type=ft,
                    credential=self.credential,
                )
            except Exception as exc:
                logger.debug("%s 获取失败: %s", ft.name, exc)
                continue

            url = result.get(song_obj.mid, "") if isinstance(result, dict) else ""
            if url:
                logger.info("命中 %s: %s", ft.name, song_obj.name)
                return SongUrl(mid=song_obj.mid, url=url, quality=ft.name)

        logger.warning("所有音质均不可下发: %s", song_obj.name)
        return None

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
        if not self.credential:
            return
        save_path = path or self._credential_cache_path
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(
                _credential_to_dict(self.credential), f, ensure_ascii=False
            )
        logger.info("凭据已保存到 %s", save_path)

    @property
    def _credential_cache_path(self) -> str:
        from ..config import CONFIG_DIR

        return str(CONFIG_DIR / "credential.json")

    # ------------------------------------------------------------------
    # 模型转换
    # ------------------------------------------------------------------

    @staticmethod
    def _to_song(raw: dict[str, Any]) -> Song:
        """0.4.1 search_by_type 返回 raw dict (而非 pydantic), 这里映射到 dataclass."""
        singers: list[Singer] = []
        for s in raw.get("singer") or []:
            singers.append(
                Singer(mid=s.get("mid", "") or "", name=s.get("name", "") or "")
            )

        album = raw.get("album") or {}
        album_mid = album.get("mid", "") or ""
        album_name = album.get("name", "") or ""

        file_info = raw.get("file") or {}
        media_mid = file_info.get("media_mid", "") or ""

        pay = raw.get("pay") or {}
        pay_play = pay.get("pay_play", 0) or 0

        return Song(
            mid=raw.get("mid", "") or "",
            name=raw.get("name", "") or "",
            singers=singers,
            album_mid=album_mid,
            album_name=album_name,
            cover_url=_cover_url(album_mid, 300),
            duration=raw.get("interval", 0) or 0,
            pay_play=pay_play,
            media_mid=media_mid,
        )

    @staticmethod
    def _to_singer(raw: dict[str, Any]) -> Singer:
        """0.4.1 SearchType.SINGER 返回的 raw → Singer."""
        return Singer(
            mid=raw.get("singerMID", "") or "",
            name=raw.get("singerName", "") or "",
            avatar_url=raw.get("singerPic", "") or "",
        )

    @staticmethod
    def _to_album_brief(raw: dict[str, Any]) -> Album:
        """SearchType.ALBUM 返回的 raw → Album (无 songs, 详情进 P0.3 拉)."""
        singers: list[Singer] = []
        for s in raw.get("singer_list") or []:
            singers.append(
                Singer(
                    mid=s.get("mid", "") or "",
                    name=s.get("name", "") or "",
                )
            )
        album_mid = raw.get("albummid", "") or ""
        cover = raw.get("pic", "") or _cover_url(album_mid, 300)
        return Album(
            mid=album_mid,
            name=raw.get("name", "") or "",
            singers=singers,
            cover_url=cover,
            publish_date=raw.get("publish_date", "") or "",
            description="",  # 搜索返回的 description 含 HTML, 走 get_detail 拿
            song_count=raw.get("song_num", 0) or 0,
        )

    @staticmethod
    def _to_playlist_brief(raw: dict[str, Any]) -> Playlist:
        """SearchType.SONGLIST 返回的 raw → Playlist (无 songs)."""
        return Playlist(
            pid=str(raw.get("dissid", "") or ""),
            name=raw.get("dissname", "") or "",
            cover_url=raw.get("logo", "") or "",
            description=raw.get("description", "") or "",
            creator=raw.get("nickname", "") or "",
            song_count=raw.get("songnum", 0) or 0,
            play_count=raw.get("listennum", 0) or 0,
        )

    @staticmethod
    def to_song_simple(raw: Any) -> Song:
        """将任何符合 raw dict / pydantic 形态的对象转为 Song (兼容)."""
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        elif not isinstance(raw, dict):
            raw = {
                "mid": getattr(raw, "mid", "") or "",
                "name": getattr(raw, "name", "") or "",
            }
        return QuaverService._to_song(raw)
