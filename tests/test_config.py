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


# ============================================================== orphan caches

def test_purge_orphan_caches_removes_known_artifacts(tmp_path):
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    config_dir.mkdir()
    cache_dir.mkdir()
    # 旧架构遗留的孤儿
    (config_dir / "cache.db").write_bytes(b"x")
    (config_dir / "cache.db-wal").write_bytes(b"x")
    (config_dir / "cache.db-shm").write_bytes(b"x")
    (cache_dir / "CacheStorage").mkdir()
    (cache_dir / "CacheStorage" / "f").write_bytes(b"x")
    (cache_dir / "WebKitCache").mkdir()
    # 必须保留的现役文件
    (config_dir / "credential.json").write_bytes(b"keep")
    (config_dir / "state.json").write_bytes(b"keep")
    (config_dir / "device_id").write_bytes(b"keep")
    (cache_dir / "covers").mkdir()
    (cache_dir / "covers" / "a.jpg").write_bytes(b"keep")

    removed = config.purge_orphan_caches(config_dir, cache_dir)

    assert {p.name for p in removed} == {
        "cache.db", "cache.db-wal", "cache.db-shm", "CacheStorage", "WebKitCache",
    }
    assert not (config_dir / "cache.db").exists()
    assert not (cache_dir / "CacheStorage").exists()
    assert not (cache_dir / "WebKitCache").exists()
    # 现役文件不受影响
    assert (config_dir / "credential.json").exists()
    assert (config_dir / "state.json").exists()
    assert (config_dir / "device_id").exists()
    assert (cache_dir / "covers" / "a.jpg").exists()


def test_purge_orphan_caches_idempotent(tmp_path):
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    config_dir.mkdir()
    cache_dir.mkdir()
    (config_dir / "cache.db").write_bytes(b"x")

    first = config.purge_orphan_caches(config_dir, cache_dir)
    second = config.purge_orphan_caches(config_dir, cache_dir)

    assert [p.name for p in first] == ["cache.db"]
    assert second == []


def test_purge_orphan_caches_handles_missing_dirs(tmp_path):
    removed = config.purge_orphan_caches(
        tmp_path / "nope-config", tmp_path / "nope-cache"
    )
    assert removed == []
