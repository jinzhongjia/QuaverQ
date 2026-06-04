"""Q11.3 smoke 判定 + release workflow 结构测试。"""

from __future__ import annotations

from quaverq import packaging, resources

_STARTED = "QuaverQ started with QML: /x/qml/Main.qml"


def test_smoke_output_ok_detects_started():
    assert packaging.smoke_output_ok(f"启动自检 ...\n{_STARTED}\n")


def test_smoke_output_ok_requires_started_marker():
    # 自检跑了但没到窗口创建（如 QML 之前崩溃）应判失败
    assert not packaging.smoke_output_ok("启动自检 [multimedia]: ok\nStreamProxy 启动")


def test_smoke_output_ok_rejects_qml_failure():
    assert not packaging.smoke_output_ok(f"{_STARTED}\nQML load failed: Main.qml")


def test_smoke_output_ok_rejects_traceback():
    assert not packaging.smoke_output_ok(
        f"{_STARTED}\nTraceback (most recent call last):"
    )


def test_smoke_output_ok_rejects_module_not_installed():
    assert not packaging.smoke_output_ok(
        f'{_STARTED}\nmodule "QtQuick.Controls.Basic" is not installed'
    )


def test_release_workflow_exists_and_triggers_on_tag():
    wf = resources.project_root() / ".github" / "workflows" / "release.yml"
    assert wf.is_file()
    text = wf.read_text(encoding="utf-8")
    assert "tags:" in text  # tag 触发
    assert "workflow_dispatch" in text  # 也允许手动触发


def test_release_workflow_has_build_appimage_smoke_upload():
    wf = resources.project_root() / ".github" / "workflows" / "release.yml"
    text = wf.read_text(encoding="utf-8")
    assert "build.py" in text or "nuitka" in text  # 编译
    assert "linuxdeploy" in text or "AppImage" in text  # AppImage 封装
    assert "--smoke" in text or "smoke" in text.lower()  # smoke 自检
    assert "upload-artifact" in text or "action-gh-release" in text  # 产物上传
    assert "patchelf" in text  # standalone 必需系统依赖
