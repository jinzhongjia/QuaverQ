"""Windows AppUserModelID 设置.

调用 ``SetCurrentProcessExplicitAppUserModelID`` 给本进程贴上一个稳定的 AUMID,
让任务栏图标 / SMTC / Jump List / Toast 都按这个 ID 关联本应用, 而不是按
python.exe 默认 ID (多个 Python 应用会合并到同一组).

必须在主窗口 / SMTC 创建前调用; 失败时不抛 (功能降级而非崩).
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger(__name__)


def set_app_user_model_id(app_id: str) -> bool:
    """设置本进程的 AUMID. 成功返 True; 失败 (非 Windows / API 缺失 / HRESULT 错) 返 False.

    `app_id` 应该是逆域名风格, 例如 ``"io.github.jinzhongjia.quaverq"``.
    """
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    except (OSError, AttributeError):
        return False  # 非 Windows
    try:
        func = shell32.SetCurrentProcessExplicitAppUserModelID
    except AttributeError:
        return False  # 很老的 Windows (< Win7)
    func.argtypes = [wintypes.LPCWSTR]
    func.restype = ctypes.c_long  # HRESULT
    hr = func(app_id)
    if hr < 0:
        logger.warning(
            "SetCurrentProcessExplicitAppUserModelID 失败: HRESULT=%#010x", hr & 0xFFFFFFFF
        )
        return False
    logger.info("Windows AUMID 已设: %s", app_id)
    return True
