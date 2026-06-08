"""测试全局夹具.

主要做一件事: 把 ``keyring`` 全局换成进程内的 dict, 防止测试污染用户真实凭据存储
(Windows Credential Manager / macOS Keychain / Linux Secret Service).
"""

from __future__ import annotations

import keyring
import keyring.errors
import pytest


class _FakeKeyring(keyring.backend.KeyringBackend):
    """进程内 dict-based keyring 后端, 优先级最高 (50)."""

    priority = 50  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._store:
            raise keyring.errors.PasswordDeleteError
        del self._store[(service, username)]


@pytest.fixture(autouse=True)
def fake_keyring():
    """每个测试用独立 FakeKeyring; 跑完恢复原后端 (防污染用户真实凭据存储).

    用 ``keyring.set_keyring`` 切, 跑完用 ``keyring.core.set_keyring(None)`` + 重置内部变量
    让 ``get_keyring()`` 下次重新 init.
    """
    backend = _FakeKeyring()
    keyring.set_keyring(backend)
    yield backend
    # 清掉; 下次 get_keyring() 会重新 init_backend (走真实平台后端)
    keyring.core._keyring_backend = None  # type: ignore[attr-defined]
