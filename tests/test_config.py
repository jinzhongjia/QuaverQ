"""配置层测试：持久设备 guid（反风控 G1）。"""

from __future__ import annotations

from quaverq import config


def test_device_guid_generates_and_persists(tmp_path):
    path = tmp_path / "device_id"
    g1 = config.device_guid(path)
    assert len(g1) == 32  # uuid4 hex
    assert path.read_text(encoding="utf-8").strip() == g1
    # 第二次调用复用同一 guid，不重新生成（模拟固定设备）
    g2 = config.device_guid(path)
    assert g2 == g1


def test_device_guid_regenerates_on_blank_file(tmp_path):
    path = tmp_path / "device_id"
    path.write_text("   \n", encoding="utf-8")
    g = config.device_guid(path)
    assert len(g) == 32
    assert path.read_text(encoding="utf-8").strip() == g


def test_load_without_file_returns_independent_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "missing.toml")

    loaded = config.load()
    loaded["player"]["volume"] = 0.1

    assert config.DEFAULTS["player"]["volume"] == 0.8


def test_load_deep_merges_user_config(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[player]\nvolume = 0.5\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_FILE", config_file)

    loaded = config.load()

    assert loaded["player"] == {
        "volume": 0.5,
        "quality": "balanced",
    }
    assert loaded["api"] == {"cookie_file": ""}
    assert config.DEFAULTS["player"]["volume"] == 0.8
