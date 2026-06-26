"""GUI 假死看门狗 (diagnostics_hang.HangWatchdog) 的契约 / 回归测试。

死锁不抛异常, sys.excepthook 抓不到; 看门狗靠心跳停顿检测 GUI 线程假死, 并用
faulthandler dump 全线程栈。这里用可注入的 clock + dump_fn 直接驱动 poll 逻辑,
不起真线程 / QTimer / 真 faulthandler, 保证测试快且确定。
"""

from __future__ import annotations

from quaverq.diagnostics_hang import HangWatchdog


def _make(clock_box, dumps, *, threshold=5.0):
    return HangWatchdog(
        hang_threshold_s=threshold,
        check_interval_s=1.0,
        log_path="unused-in-test",
        clock=lambda: clock_box[0],
        dump_fn=lambda path: dumps.append((clock_box[0], path)),
    )


def test_no_dump_while_heartbeat_advances() -> None:
    """心跳每秒前进 -> 永不判定假死。"""
    clk = [0.0]
    dumps: list = []
    wd = _make(clk, dumps)
    for t in range(1, 30):
        clk[0] = float(t)
        wd.heartbeat()
        assert wd.poll() is False
    assert dumps == []


def test_no_dump_before_threshold() -> None:
    """心跳停顿但未到阈值 -> 不 dump。"""
    clk = [0.0]
    dumps: list = []
    wd = _make(clk, dumps, threshold=5.0)
    wd.heartbeat()
    clk[0] = 1.0
    assert wd.poll() is False  # 看到一次进展
    clk[0] = 5.0  # 距上次进展 4s < 5s
    assert wd.poll() is False
    assert dumps == []


def test_dump_after_stall_exceeds_threshold() -> None:
    """心跳停顿超过阈值 -> dump 一次。"""
    clk = [0.0]
    dumps: list = []
    wd = _make(clk, dumps, threshold=5.0)
    wd.heartbeat()
    clk[0] = 1.0
    wd.poll()  # 记录进展时间 = 1.0
    clk[0] = 6.0  # 停顿 5s == 阈值
    assert wd.poll() is True
    assert len(dumps) == 1


def test_only_one_dump_per_hang_episode() -> None:
    """同一次假死持续 -> 只 dump 一次, 不刷屏。"""
    clk = [0.0]
    dumps: list = []
    wd = _make(clk, dumps, threshold=5.0)
    wd.heartbeat()
    clk[0] = 1.0
    wd.poll()
    clk[0] = 6.0
    assert wd.poll() is True
    for t in (7.0, 10.0, 30.0, 100.0):
        clk[0] = t
        assert wd.poll() is False
    assert len(dumps) == 1


def test_dump_again_after_recovery() -> None:
    """假死 -> dump -> 心跳恢复 -> 再次假死 -> 再 dump。"""
    clk = [0.0]
    dumps: list = []
    wd = _make(clk, dumps, threshold=5.0)
    wd.heartbeat()
    clk[0] = 1.0
    wd.poll()
    clk[0] = 6.0
    assert wd.poll() is True  # 第一次

    # 恢复: 心跳重新前进
    wd.heartbeat()
    clk[0] = 7.0
    assert wd.poll() is False  # 看到进展, 重新 arm

    # 再次假死
    clk[0] = 13.0  # 距 7.0 停顿 6s >= 5s
    assert wd.poll() is True  # 第二次
    assert len(dumps) == 2


def test_default_dump_writes_thread_stacks(tmp_path) -> None:
    """默认 dump_fn 用 faulthandler 把全线程栈写到 log 文件 (真 faulthandler, 真落盘)。"""
    log_path = tmp_path / "hang.log"
    wd = HangWatchdog(hang_threshold_s=5.0, log_path=log_path)
    wd._dump_all_threads(log_path)  # noqa: SLF001 - 直接验证默认 dump 实现
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    # faulthandler 稳定输出: "most recent call first" + 当前帧 (本测试函数名)
    assert "most recent call first" in content
    assert "test_default_dump_writes_thread_stacks" in content


def test_stop_is_idempotent_and_safe() -> None:
    """stop() 不起线程时也安全, 重复调用幂等。"""
    wd = HangWatchdog(hang_threshold_s=5.0, log_path="x")
    wd.stop()
    wd.stop()  # 不应抛
