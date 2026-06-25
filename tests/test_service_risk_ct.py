"""service 风控指纹 (ct) 持久化 + 可重置.

ct 不再每次 connect 随机抽 (旧设计抽到失效 ct 会整段播不了, 重启才好);
改为落盘复用 (像固定设备), 设置页可手动重置, 内存值立即生效。
"""

from __future__ import annotations

import pytest

from quaverq import config
from quaverq.core.service import QuaverService


@pytest.fixture
def _ct_file(tmp_path, monkeypatch):
    path = tmp_path / "risk_ct"
    monkeypatch.setattr(config, "_risk_ct_file", lambda: path)
    return path


def test_load_risk_ct_persists_across_calls(_ct_file):
    svc = QuaverService()
    c1 = svc._load_risk_ct()
    assert c1 in svc._SAFE_CT_VALUES
    assert _ct_file.read_text(encoding="utf-8").strip() == str(c1)
    # 第二个实例 (= 模拟重启) 读到同一值, 不重抽
    assert QuaverService()._load_risk_ct() == c1


def test_reset_risk_fingerprint_changes_value_immediately(_ct_file):
    svc = QuaverService()
    svc._ct_value = svc._load_risk_ct()
    before = svc._ct_value
    # 重抽直到拿到不同值 (池够大, 有限次必中), 验证落盘 + 内存同步
    seen = {before}
    for _ in range(50):
        new = svc.reset_risk_fingerprint()
        seen.add(new)
        assert new in svc._SAFE_CT_VALUES
        assert svc._ct_value == new, "重置后内存 _ct_value 必须立即更新"
        assert int(_ct_file.read_text(encoding="utf-8").strip()) == new
        if new != before:
            break
    assert len(seen) > 1, "多次重置应至少出现过不同 ct"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
