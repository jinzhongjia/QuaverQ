"""Windows 单实例守卫测试 (文件锁实现).

策略: 每个测试用独立 ``tmp_path / .lock`` 文件, 避免并行 / 串行测试间互相污染.
真正的跨进程互斥靠 OS 文件锁, 同进程内两个 ``WindowsSingleInstance(lock_path=同一文件)``
也能复现 "已被占" 场景 (msvcrt.locking 在同进程内 fd 已锁的字节再 LK_NBLCK 也会失败).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


async def test_acquire_returns_true_on_first_instance(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    guard = WindowsSingleInstance(lock_path=str(tmp_path / ".app.lock"))
    try:
        assert await guard.acquire() is True
    finally:
        guard.release()


async def test_acquire_returns_false_when_already_held(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    lock_path = str(tmp_path / ".app.lock")
    first = WindowsSingleInstance(lock_path=lock_path)
    second = WindowsSingleInstance(lock_path=lock_path)
    try:
        assert await first.acquire() is True
        assert await second.acquire() is False
    finally:
        first.release()
        second.release()


async def test_release_allows_reacquire(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    lock_path = str(tmp_path / ".app.lock")
    guard = WindowsSingleInstance(lock_path=lock_path)
    assert await guard.acquire() is True
    guard.release()

    guard2 = WindowsSingleInstance(lock_path=lock_path)
    try:
        assert await guard2.acquire() is True
    finally:
        guard2.release()


async def test_release_is_idempotent(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    guard = WindowsSingleInstance(lock_path=str(tmp_path / ".app.lock"))
    await guard.acquire()
    guard.release()
    guard.release()
    guard.release()


async def test_notify_existing_raise_does_not_crash_without_window(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    guard = WindowsSingleInstance(
        lock_path=str(tmp_path / ".app.lock"),
        window_title=f"NonExistent-{uuid.uuid4().hex}",
    )
    await guard.notify_existing_raise()


def test_satisfies_single_instance_protocol(tmp_path: Path):
    from quaverq.platform._windows_single_instance import WindowsSingleInstance
    from quaverq.platform.base import SingleInstance

    inst = WindowsSingleInstance(lock_path=str(tmp_path / ".app.lock"))
    assert isinstance(inst, SingleInstance)


def test_windows_platform_returns_real_single_instance():
    """WindowsPlatform.single_instance() 返回 WindowsSingleInstance 实例 (用默认 CONFIG_DIR 锁)."""
    from quaverq.platform import get_platform
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    pal = get_platform()
    inst = pal.single_instance()
    assert isinstance(inst, WindowsSingleInstance)
    inst.release()
