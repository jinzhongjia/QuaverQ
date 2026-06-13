"""LyricCache tests."""

from __future__ import annotations

import json

from quaverq.core.lyric_cache import LyricCache
from quaverq.core.models import Lyric, LyricLine, LyricWord


def _lyric(mid: str = "m1") -> Lyric:
    return Lyric(
        mid=mid,
        has_translation=True,
        lines=[
            LyricLine(
                timestamp_ms=1000,
                text="你好",
                translation="hello",
                words=[
                    LyricWord(text="你", start_ms=1000, duration_ms=200),
                    LyricWord(text="好", start_ms=1200, duration_ms=300),
                ],
            )
        ],
    )


def test_save_then_load_round_trips_words_and_translation(tmp_path):
    cache = LyricCache(tmp_path / "lyrics")
    lyric = _lyric()

    cache.save(lyric, with_translation=True)
    loaded = cache.load("m1", with_translation=True)

    assert loaded == lyric


def test_load_missing_or_corrupt_cache_returns_none(tmp_path):
    cache = LyricCache(tmp_path / "lyrics")

    assert cache.load("missing", with_translation=True) is None

    path = cache._path_for("m1", True)  # noqa: SLF001
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")

    assert cache.load("m1", with_translation=True) is None


def test_load_ignores_version_and_key_mismatch(tmp_path):
    cache = LyricCache(tmp_path / "lyrics")
    cache.save(_lyric("m1"), with_translation=True)

    assert cache.load("m1", with_translation=False) is None

    path = cache._path_for("m2", True)  # noqa: SLF001
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 999,
                "mid": "m2",
                "with_translation": True,
                "lyric": {},
            }
        ),
        encoding="utf-8",
    )

    assert cache.load("m2", with_translation=True) is None
