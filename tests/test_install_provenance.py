"""Tests for catalog install provenance JSONL."""

from __future__ import annotations

import json
from pathlib import Path

from forager_ai.launcher.install_provenance import (
    append_install_provenance,
    build_provenance_record,
    read_install_provenance_tail,
)
from forager_ai.launcher.mod_downloader import ModInfo


def test_build_and_append_roundtrip(tmp_path: Path) -> None:
    jar = tmp_path / "x.jar"
    jar.write_bytes(b"abc")
    mi = ModInfo(
        id="vid",
        name="Test Mod",
        description="",
        author="a",
        source="modrinth",
        project_id="prj",
        version_id="vid",
        download_url="http://example.invalid",
        file_name="x.jar",
        sha1_hash="",
    )
    rec = build_provenance_record(mi, str(jar))
    assert rec["source"] == "modrinth"
    assert rec["project_id"] == "prj"
    assert len(rec["sha256"]) == 64
    append_install_provenance(tmp_path, rec)
    tail = read_install_provenance_tail(tmp_path, max_lines=10)
    assert len(tail) == 1
    assert tail[0]["file_name"] == "x.jar"


def test_read_tail_truncates(tmp_path: Path) -> None:
    log = tmp_path / "install_provenance.jsonl"
    with open(log, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"i": i}, separators=(",", ":")) + "\n")
    tail = read_install_provenance_tail(tmp_path, max_lines=3)
    assert [r["i"] for r in tail] == [2, 3, 4]
