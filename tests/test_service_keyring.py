"""凭据存储: 纯 keyring (无文件 fallback) 契约.

软件未发布无历史用户; ``service.py`` 凭据存取**只**走 keyring (Linux Secret Service /
Windows Credential Manager / macOS Keychain). 失败时静默 log warning, app 继续跑,
用户重启需要重新扫码.
"""

from __future__ import annotations

import keyring
import keyring.errors
from qqmusic_api import Credential

from quaverq.core.service import (
    QuaverService,
    _load_credential_blob,
    _save_credential_blob,
)

# ============================================================== _save_credential_blob


def test_save_writes_to_keyring(fake_keyring):
    blob = '{"musicid":1,"musickey":"k"}'
    _save_credential_blob(blob)
    assert fake_keyring.get_password("QuaverQ", "credential") == blob


def test_save_swallows_keyring_error(fake_keyring, monkeypatch, caplog):
    """keyring 不可用 (headless / 无 D-Bus) 时 _save 不应 raise, 只 warning."""
    import logging

    def _raise(*_args, **_kwargs):
        raise keyring.errors.NoKeyringError("simulated headless env")

    monkeypatch.setattr(fake_keyring, "set_password", _raise)
    with caplog.at_level(logging.WARNING, logger="quaverq.core.service"):
        _save_credential_blob('{"musicid":1}')  # 不应 raise
    assert any("keyring 写失败" in record.message for record in caplog.records)


def test_save_supports_unicode_blob(fake_keyring):
    """keyring API 是 Python str (内部 UTF-16/UTF-8), 不会有 GBK 编码问题."""
    blob = '{"musickey":"key—Ø","nickname":"七元"}'
    _save_credential_blob(blob)
    assert fake_keyring.get_password("QuaverQ", "credential") == blob


# ============================================================== _load_credential_blob


def test_load_returns_keyring_blob_when_present(fake_keyring):
    fake_keyring.set_password("QuaverQ", "credential", '{"musicid":3}')
    assert _load_credential_blob() == '{"musicid":3}'


def test_load_returns_none_when_empty(fake_keyring):
    assert _load_credential_blob() is None


def test_load_returns_none_when_keyring_errors(fake_keyring, monkeypatch):
    """keyring 抛错也应当返 None (而非 raise), app 启动期不能因为 keyring 失败崩."""

    def _raise(*_args, **_kwargs):
        raise keyring.errors.KeyringError("backend broken")

    monkeypatch.setattr(fake_keyring, "get_password", _raise)
    assert _load_credential_blob() is None


# ============================================================== QuaverService 端到端


async def test_service_save_then_load_roundtrip():
    """svc.save_credential() -> 新 svc.load_cached_credential_sync() 应复原."""
    svc = QuaverService()
    await svc.set_credential(Credential(musicid=42, musickey="ks—42", str_musicid="42"))
    await svc.save_credential()

    svc2 = QuaverService()
    loaded = svc2.load_cached_credential_sync()
    assert loaded is not None
    assert loaded.musicid == 42
    assert loaded.musickey == "ks—42"


async def test_service_skips_save_when_no_musickey():
    """没 musickey -> 不写 keyring (避免落一条空记录污染存储)."""
    svc = QuaverService()
    # 不 set_credential, 直接 save: musickey 为空, 应当无 op
    await svc.save_credential()
    assert _load_credential_blob() is None
