"""Tests for support bundle and log tail helpers."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from forager_ai.diagnostics.log_tail import find_latest_log_paths, tail_latest_log
from forager_ai.ops.support_bundle import build_support_bundle_zip_bytes


def test_support_bundle_contains_readme(tmp_path: Path) -> None:
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "forager_mods.lock.json").write_text("{}", encoding="utf-8")
    logs = root / "logs"
    logs.mkdir(parents=True)
    (logs / "latest.log").write_text("tail line here\n", encoding="utf-8")
    cache = tmp_path / "c"
    cache.mkdir()
    (cache / "install_provenance.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    z = build_support_bundle_zip_bytes(str(root), str(cache))
    zf = zipfile.ZipFile(io.BytesIO(z))
    names = zf.namelist()
    assert "README.txt" in names
    assert "forager_mods.lock.json" in names
    assert "latest_log_tail.txt" in names
    assert "env_fingerprint.json" in names
    inner = zf.read("latest_log_tail.txt").decode("utf-8", errors="replace")
    assert "tail line" in inner


def test_tail_latest_log(tmp_path: Path) -> None:
    root = tmp_path / "g"
    logs = root / "logs"
    logs.mkdir(parents=True)
    (logs / "latest.log").write_text("hello\nworld\n", encoding="utf-8")
    assert find_latest_log_paths(str(root))
    t = tail_latest_log(str(root), max_chars=1000)
    assert "world" in t
