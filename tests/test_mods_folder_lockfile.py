"""Tests for reproducible mods/ lockfile and two-root compare."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from forager_ai.ops.mods_folder_lockfile import (
    build_game_root_mods_lock,
    compare_mods_roots,
    compare_surface_folders,
    write_game_root_mods_lock,
)


def _write_fabric_jar(path: Path, mod_id: str, version: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "fabric.mod.json",
            json.dumps({"schemaVersion": 1, "id": mod_id, "version": version}),
        )
    path.write_bytes(buf.getvalue())


def test_build_game_root_mods_lock_empty_mods(tmp_path: Path) -> None:
    root = tmp_path / "inst"
    (root / "mods").mkdir(parents=True)
    lock = build_game_root_mods_lock(str(root))
    assert lock["mods_dir_present"] is True
    assert lock["jars"] == []


def test_build_game_root_mods_lock_one_jar(tmp_path: Path) -> None:
    root = tmp_path / "inst"
    mods = root / "mods"
    mods.mkdir(parents=True)
    jar = mods / "demo-fabric-1.0.0.jar"
    _write_fabric_jar(jar, "demo", "1.0.0")
    lock = build_game_root_mods_lock(str(root))
    assert len(lock["jars"]) == 1
    row = lock["jars"][0]
    assert row["rel"].replace("\\", "/") == "mods/demo-fabric-1.0.0.jar"
    assert row["mod_id"] == "demo"
    assert row["jar_version"] == "1.0.0"
    assert len(row["sha256"]) == 64
    assert row["enabled"] is True


def test_write_game_root_mods_lock(tmp_path: Path) -> None:
    root = tmp_path / "inst"
    (root / "mods").mkdir(parents=True)
    _write_fabric_jar(root / "mods" / "a.jar", "a", "1")
    out = write_game_root_mods_lock(str(root))
    assert Path(out).name == "forager_mods.lock.json"
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["kind"] == "forager_mods_lock"
    assert len(data["jars"]) == 1


def test_compare_mods_roots_only_in_b(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "mods").mkdir(parents=True)
    (b / "mods").mkdir(parents=True)
    _write_fabric_jar(a / "mods" / "onlya.jar", "onlya", "1")
    _write_fabric_jar(b / "mods" / "onlyb.jar", "onlyb", "1")
    rep = compare_mods_roots(str(a), str(b))
    assert len(rep["only_in_a"]) == 1
    assert len(rep["only_in_b"]) == 1
    assert rep["only_in_a"][0]["logical_key"] == "onlya.jar"
    assert rep["only_in_b"][0]["logical_key"] == "onlyb.jar"


def test_compare_same_logical_different_hash(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "mods").mkdir(parents=True)
    (b / "mods").mkdir(parents=True)
    _write_fabric_jar(a / "mods" / "shared.jar", "shared", "1.0.0")
    _write_fabric_jar(b / "mods" / "shared.jar", "shared", "2.0.0")
    rep = compare_mods_roots(str(a), str(b))
    assert len(rep["same_logical_jar_different_hash"]) == 1


def test_compare_surface_folders(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "resourcepacks").mkdir(parents=True)
    (b / "resourcepacks").mkdir(parents=True)
    (a / "resourcepacks" / "x.zip").write_text("1", encoding="utf-8")
    (b / "resourcepacks" / "y.zip").write_text("2", encoding="utf-8")
    rep = compare_surface_folders(str(a), str(b))
    sec = rep["sections"]["resourcepacks"]
    assert "x.zip" in sec["only_in_a"]
    assert "y.zip" in sec["only_in_b"]
