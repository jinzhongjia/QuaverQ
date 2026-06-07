"""Windows 单实例守卫 (Mutex) 测试.

策略: ctypes 直调 Win32 API, 没有真"另一个进程"测试位; 通过两个 ``WindowsSingleInstance``
实例 + 同一 mutex 名复现"已被占" 场景 (Windows mutex 是命名全局对象, 同进程内多次
``CreateMutexW`` 也能复现 ``ERROR_ALREADY_EXISTS``).

mutex 名按测试用例 uuid 随机化, 避免并行 / 串行测试间互相污染.
"""

from __future__ import annotations

import sys
import uuid

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def _random_mutex_name() -> str:
    return f"QuaverQ-Test-{uuid.uuid4().hex[:16]}"


async def test_acquire_returns_true_on_first_instance():
    """第一次 acquire 必须成功 (没有其他实例)."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    guard = WindowsSingleInstance(mutex_name=_random_mutex_name())
    try:
        assert await guard.acquire() is True
    finally:
        guard.release()


async def test_acquire_returns_false_when_already_held():
    """同一 mutex 名第二次 acquire 必须失败 (复现"已被占")."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    name = _random_mutex_name()
    first = WindowsSingleInstance(mutex_name=name)
    second = WindowsSingleInstance(mutex_name=name)
    try:
        assert await first.acquire() is True
        assert await second.acquire() is False
    finally:
        first.release()
        second.release()


async def test_release_allows_reacquire():
    """release 后必须能 reacquire (锁释放干净, 无残留 handle)."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    name = _random_mutex_name()
    guard = WindowsSingleInstance(mutex_name=name)
    assert await guard.acquire() is True
    guard.release()

    # 同一 name 再开一个新 guard 也应能拿到
    guard2 = WindowsSingleInstance(mutex_name=name)
    try:
        assert await guard2.acquire() is True
    finally:
        guard2.release()


async def test_release_is_idempotent():
    """release 多次调用不应 raise (与 SingleInstance Protocol 契约一致)."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    guard = WindowsSingleInstance(mutex_name=_random_mutex_name())
    await guard.acquire()
    guard.release()
    guard.release()  # 第二次不抛
    guard.release()


async def test_notify_existing_raise_does_not_crash_without_window():
    """没找到目标窗口时 notify_existing_raise 应静默返回, 不抛."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    # 用一个绝不存在的 window title, EnumWindows 找不到目标
    guard = WindowsSingleInstance(
        mutex_name=_random_mutex_name(),
        window_title=f"NonExistent-{uuid.uuid4().hex}",
    )
    # 不需要 acquire; notify 本身是给"第二实例"调的, 它没占住锁
    await guard.notify_existing_raise()  # 不 raise 即通过


def test_satisfies_single_instance_protocol():
    """WindowsSingleInstance 应当满足 PlatformAdapter 的 SingleInstance Protocol 鸭子."""
    from quaverq.platform._windows_single_instance import WindowsSingleInstance
    from quaverq.platform.base import SingleInstance

    inst = WindowsSingleInstance(mutex_name=_random_mutex_name())
    assert isinstance(inst, SingleInstance)


def test_windows_platform_returns_real_single_instance():
    """WindowsPlatform.single_instance() 不再返回 None, 应是 WindowsSingleInstance 实例."""
    from quaverq.platform import get_platform
    from quaverq.platform._windows_single_instance import WindowsSingleInstance

    pal = get_platform()
    inst = pal.single_instance()
    assert isinstance(inst, WindowsSingleInstance)
    inst.release()  # cleanup; 测试不持有
