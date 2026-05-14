"""Tests for version ranking, lock verify, asset audit, pack sheet, crash heuristics."""

from __future__ import annotations

import json
from pathlib import Path

from forager_ai.diagnostics.asset_audit import build_mods_asset_audit
from forager_ai.diagnostics.crash_parser import analyze_crash_log
from forager_ai.launcher.mod_downloader import ModInfo
from forager_ai.launcher.version_hints import rank_modrinth_versions
from forager_ai.ops.mod_lock_verify import verify_forager_mods_lock
from forager_ai.ops.mods_folder_lockfile import write_game_root_mods_lock
from forager_ai.ops.reminders import append_reminder, load_reminders, mark_reminder_done_at_index, overdue_items, save_reminders
from forager_ai.ops.repair_hints import repair_hints_from_verify
from forager_ai.ops.lock_diff import diff_lock_payloads
from forager_ai.ops.server_parity import (
    compare_server_parity,
    parse_server_manifest_json,
    parse_server_modlist_blob,
)
from forager_ai.pack.compat_hints import compat_rules_touching_mod_ids
from forager_ai.pack.compat_registry import add_compat_rule
from forager_ai.pack.pack_sheet import build_pack_sheet_markdown
from forager_ai.pack.pack_text_ops import assert_editable_rel, list_pack_text_files
from forager_ai.tools.issue_harvest import harvest_project_url


def test_crash_mixin_signature() -> None:
    r = analyze_crash_log("Mixin apply failed org.spongepowered.asm.mixin.transformer.MixinTransformer")
    assert any("mixin" in f.lower() for f in r["findings"])


def test_rank_prefers_matching_mc() -> None:
    a = ModInfo(
        id="1",
        name="x",
        description="",
        author="",
        source="modrinth",
        project_id="p",
        minecraft_versions=["1.19.2"],
        loaders=["forge"],
        file_name="a.jar",
        file_size=100,
    )
    b = ModInfo(
        id="2",
        name="x",
        description="",
        author="",
        source="modrinth",
        project_id="p",
        minecraft_versions=["1.20.1"],
        loaders=["forge"],
        file_name="b.jar",
        file_size=50,
    )
    out = rank_modrinth_versions([a, b], want_mc="1.20.1", want_loader="forge")
    assert out[0].file_name == "b.jar"


def test_verify_lock(tmp_path: Path) -> None:
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "z.jar").write_bytes(b"x" * 20)
    write_game_root_mods_lock(str(root))
    rep = verify_forager_mods_lock(str(root))
    assert rep.get("ok") is True
    assert rep.get("hash_ok_count", 0) >= 1
    (root / "mods" / "z.jar").write_bytes(b"y" * 20)
    rep2 = verify_forager_mods_lock(str(root))
    assert len(rep2.get("hash_mismatch") or []) >= 1


def test_asset_audit_dup(tmp_path: Path) -> None:
    root = tmp_path / "g"
    m = root / "mods"
    m.mkdir(parents=True)
    (m / "a.jar").write_bytes(b"1")
    (m / "sub").mkdir()
    (m / "sub" / "a.jar.disabled").write_bytes(b"2")
    rep = build_mods_asset_audit(str(root))
    assert rep["jar_count"] == 2
    assert len(rep["duplicate_logical_names"]) >= 1


def test_pack_sheet_md(tmp_path: Path) -> None:
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "z.jar").write_bytes(b"1")
    lock = json.loads(Path(write_game_root_mods_lock(str(root))).read_text(encoding="utf-8"))
    md = build_pack_sheet_markdown(str(root), title="T", lock_payload=lock)
    assert "T" in md
    assert "|" in md


def test_server_parity_parse() -> None:
    s = parse_server_modlist_blob("jei, create\n#x\nmods/a.jar")
    assert "jei" in s and "create" in s and "a" in s
    ids, note = parse_server_manifest_json('{"mod_ids":["Create","oxidized"]}')
    assert "create" in ids and "oxidized" in ids
    assert "mod_ids" in note


def test_server_parity_compare(tmp_path: Path) -> None:
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "z.jar").write_bytes(b"x" * 20)
    write_game_root_mods_lock(str(root))
    rep = compare_server_parity(str(root), server_text="missing_mod_only", server_json="")
    assert "missing_mod_only" in (rep.get("only_on_server") or [])


def test_repair_hints() -> None:
    lines = repair_hints_from_verify(
        {
            "ok": True,
            "missing_on_disk": ["mods/x.jar"],
            "extra_on_disk": [],
            "hash_mismatch": [{"rel": "mods/y.jar", "sha256_lock": "a", "sha256_disk": "b"}],
        }
    )
    assert any("missing" in ln.lower() for ln in lines)
    assert any("mismatch" in ln.lower() for ln in lines)


def test_reminders_overdue(tmp_path: Path) -> None:
    save_reminders(tmp_path, {"items": [{"title": "t", "cadence_days": 1, "last_done_iso": ""}]})
    d = load_reminders(tmp_path)
    assert len(overdue_items(d)) >= 1


def test_reminders_mark_done(tmp_path: Path) -> None:
    save_reminders(tmp_path, {"items": [{"title": "a", "cadence_days": 7, "last_done_iso": ""}]})
    assert mark_reminder_done_at_index(tmp_path, 0) is True
    d = load_reminders(tmp_path)
    assert str((d["items"][0] or {}).get("last_done_iso") or "").startswith("20")


def test_reminders_append(tmp_path: Path) -> None:
    append_reminder(tmp_path, "job", cadence_days=3)
    d = load_reminders(tmp_path)
    assert len(d["items"]) == 1
    assert d["items"][0]["title"] == "job"
    assert int(d["items"][0]["cadence_days"]) == 3


def test_env_fingerprint_extra_keys() -> None:
    from forager_ai.diagnostics.env_fingerprint import collect_env_fingerprint

    fp = collect_env_fingerprint(timeout_s=4.0)
    assert "python" in fp
    assert ("git_version_line" in fp) or ("git_version_error" in fp)
    assert ("streamlit_version" in fp) or ("streamlit_version_error" in fp)


def test_pack_text_ops_list(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "config").mkdir(parents=True)
    (root / "config" / "x.toml").write_text("a=1", encoding="utf-8")
    rels = list_pack_text_files(str(root))
    assert any(r.endswith("config/x.toml") for r in rels)
    assert_editable_rel("config/x.toml")
    try:
        assert_editable_rel("secrets/foo.txt")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_compat_hints_touch(tmp_path: Path) -> None:
    root = tmp_path / "p"
    (root / "mods").mkdir(parents=True)
    add_compat_rule(
        str(root),
        rule_name="R1",
        affected_mods=["create", "jei"],
        description="d",
        source="test",
    )
    hits = compat_rules_touching_mod_ids(str(root), {"create", "other"})
    assert hits and "create" in (hits[0].get("_matched_installed") or [])


def test_issue_harvest_empty() -> None:
    r = harvest_project_url("")
    assert r.get("ok") is False


def test_pack_profile_roles() -> None:
    from forager_ai.pack.pack_text_ops import build_pack_profile_from_lock

    lock = {"jars": [{"mod_id": "create"}]}
    p = build_pack_profile_from_lock(lock, name="t", roles=["server", "client-min"])
    assert p.get("roles") == ["server", "client-min"]


def test_lock_diff_basic() -> None:
    a = {"jars": [{"rel": "mods/a.jar", "sha256": "x" * 64, "mod_id": "a"}]}
    b = {"jars": [{"rel": "mods/a.jar", "sha256": "y" * 64, "mod_id": "a"}, {"rel": "mods/b.jar", "sha256": "z" * 64, "mod_id": "b"}]}
    d = diff_lock_payloads(a, b)
    assert "mods/b.jar" in str(d.get("only_rels_in_b"))
    assert d.get("shared_rel_hash_mismatch")


def test_lock_attestation_roundtrip(tmp_path: Path) -> None:
    from forager_ai.ops.lock_attestation import lock_file_sha256_hex, write_lock_attestation_sidecar

    lp = tmp_path / "forager_mods.lock.json"
    lp.write_text('{"jars":[]}', encoding="utf-8")
    write_lock_attestation_sidecar(lp)
    meta = lp.with_name("forager_mods.lock.meta.json")
    assert meta.is_file()
    import json

    o = json.loads(meta.read_text(encoding="utf-8"))
    assert o.get("sha256") == lock_file_sha256_hex(lp)


def test_server_manifest_forge(tmp_path: Path) -> None:
    from forager_ai.ops.server_manifest import extract_from_manifest_json

    raw = '{"files":[{"projectID":123,"fileID":1}]}'
    ids, cf, note = extract_from_manifest_json(raw)
    assert "123" in cf


def test_compare_config_deep(tmp_path: Path) -> None:
    from forager_ai.ops.mods_folder_lockfile import compare_config_deep_limited

    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "config").mkdir(parents=True)
    (b / "config").mkdir(parents=True)
    (a / "config" / "x.toml").write_text("k=1", encoding="utf-8")
    (b / "config" / "x.toml").write_text("k=2", encoding="utf-8")
    rep = compare_config_deep_limited(str(a), str(b), max_files_per_side=50)
    assert rep.get("same_rel_different_hash")


def test_modrinth_pin_drift_status() -> None:
    from forager_ai.ops.pin_drift import modrinth_pin_drift_status

    assert modrinth_pin_drift_status(pinned_version_id="a", newest_first_version_ids=["a"]) == "pinned_is_latest"
    assert modrinth_pin_drift_status(pinned_version_id="a", newest_first_version_ids=["b", "a"]) == "newer_available"
    assert modrinth_pin_drift_status(pinned_version_id="", newest_first_version_ids=["x"]) == "no_pin"


def test_summarize_modrinth_pin_drift_reuses_http() -> None:
    from forager_ai.ops.pin_drift import summarize_modrinth_pin_drift

    class _FakeDL:
        def __init__(self) -> None:
            self.calls = 0

        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            self.calls += 1
            return [
                ModInfo(
                    id="n",
                    name="n",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="nv",
                    minecraft_versions=["1.20.1"],
                    loaders=["forge"],
                    file_name="new.jar",
                    file_size=10,
                ),
                ModInfo(
                    id="o",
                    name="o",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="pv",
                    minecraft_versions=["1.20.1"],
                    loaders=["forge"],
                    file_name="old.jar",
                    file_size=9,
                ),
            ]

    dl = _FakeDL()
    pins = [
        {"source": "modrinth", "project_id": "p1", "version_id": "pv", "target_key": "t1"},
        {"source": "modrinth", "project_id": "p1", "version_id": "pv", "target_key": "t2"},
    ]
    rows = summarize_modrinth_pin_drift(dl, pins, max_pins=10)
    assert dl.calls == 1
    assert len(rows) == 2
    assert rows[0]["status"] == "newer_available"
    assert rows[0]["newest_version_id"] == "nv"


def test_summarize_modrinth_install_queue() -> None:
    from forager_ai.ops.queue_resolution import summarize_modrinth_install_queue

    class _QDL:
        def __init__(self) -> None:
            self.detail_calls = 0
            self.version_calls = 0

        def get_modrinth_project_detail(self, project_id: str):
            self.detail_calls += 1
            return {"title": f"T-{project_id}", "project_url": "https://modrinth.com/mod/x"}

        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            self.version_calls += 1
            if filter_loader and minecraft_version:
                return [
                    ModInfo(
                        id="1",
                        name="x",
                        description="",
                        author="",
                        source="modrinth",
                        project_id=pid,
                        version_id="v1",
                        minecraft_versions=["1.20.1"],
                        loaders=["forge"],
                        file_name="hit.jar",
                        file_size=3,
                    )
                ]
            return [
                ModInfo(
                    id="2",
                    name="x",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="v2",
                    minecraft_versions=["1.19.2"],
                    loaders=["forge"],
                    file_name="loose.jar",
                    file_size=2,
                )
            ]

    dl = _QDL()
    q = [{"source": "modrinth", "project_id": "abc"}]
    rows = summarize_modrinth_install_queue(dl, q, minecraft_version="1.20.1", loader="forge", max_items=5)
    assert len(rows) == 1
    assert rows[0]["strict_matches"] == 1
    assert rows[0]["used_relaxed_preview"] is False
    assert "hit.jar" in rows[0]["preview_files"]
    assert "modrinth.com" in rows[0].get("project_url", "")

    class _QDL2:
        def get_modrinth_project_detail(self, project_id: str):
            return {"title": "X"}

        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            if filter_loader and minecraft_version:
                return []
            return [
                ModInfo(
                    id="2",
                    name="x",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="v2",
                    minecraft_versions=["1.19.2"],
                    loaders=["forge"],
                    file_name="loose.jar",
                    file_size=2,
                )
            ]

    r2 = summarize_modrinth_install_queue(_QDL2(), q, minecraft_version="1.20.1", loader="forge")
    assert r2[0]["strict_matches"] == 0
    assert r2[0]["used_relaxed_preview"] is True


def test_pick_modrinth_install_candidate_strict_and_relaxed() -> None:
    from forager_ai.ops.queue_resolution import pick_modrinth_install_candidate

    class _DL:
        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            if filter_loader and minecraft_version:
                return [
                    ModInfo(
                        id="1",
                        name="x",
                        description="",
                        author="",
                        source="modrinth",
                        project_id=pid,
                        version_id="v1",
                        minecraft_versions=["1.20.1"],
                        loaders=["forge"],
                        file_name="hit.jar",
                        file_size=3,
                    )
                ]
            return [
                ModInfo(
                    id="2",
                    name="x",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="v2",
                    minecraft_versions=["1.18.2"],
                    loaders=["forge"],
                    file_name="loose.jar",
                    file_size=2,
                )
            ]

    dl = _DL()
    mi, err, relaxed = pick_modrinth_install_candidate(
        dl, "proj", minecraft_version="1.20.1", loader="forge", allow_relaxed_fallback=True
    )
    assert err == ""
    assert not relaxed and mi is not None and mi.file_name == "hit.jar"

    class _StrictMiss:
        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            if filter_loader and minecraft_version:
                return []
            return [
                ModInfo(
                    id="2",
                    name="x",
                    description="",
                    author="",
                    source="modrinth",
                    project_id=pid,
                    version_id="v2",
                    minecraft_versions=["1.18.2"],
                    loaders=["forge"],
                    file_name="loose.jar",
                    file_size=2,
                )
            ]

    mi3, err3, rel3 = pick_modrinth_install_candidate(
        _StrictMiss(), "proj", minecraft_version="1.20.1", loader="forge", allow_relaxed_fallback=True
    )
    assert err3 == ""
    assert rel3 and mi3 is not None and mi3.file_name == "loose.jar"

    mi4, err4, _ = pick_modrinth_install_candidate(
        _StrictMiss(), "proj", minecraft_version="1.20.1", loader="forge", allow_relaxed_fallback=False
    )
    assert mi4 is None and err4 == "no_modrinth_file"


def test_run_modrinth_install_queue_instance_happy_path() -> None:
    from forager_ai.ops.queue_resolution import run_modrinth_install_queue

    hit = ModInfo(
        id="1",
        name="x",
        description="",
        author="",
        source="modrinth",
        project_id="abc",
        version_id="v1",
        minecraft_versions=["1.20.1"],
        loaders=["forge"],
        file_name="hit.jar",
        file_size=3,
    )

    class _Md:
        def get_modrinth_project_detail(self, project_id: str):
            return {"title": "T"}

        def get_modrinth_versions(self, pid, minecraft_version=None, loader=None, filter_loader=True, catalog_kind="mods"):
            if pid == "abc":
                return [hit]
            return []

    class _Lf:
        def __init__(self) -> None:
            self.mod_downloader = _Md()
            self.config = {"catalog_pins": []}
            self.installed = []

        def preflight_instance_install(self, name, mod_info):
            return {"decision": "allow"}

        def install_catalog_item(self, name, mod_info, catalog_kind="mods", install_dependencies=True):
            assert name == "i1"
            self.installed.append((mod_info.file_name, catalog_kind, install_dependencies))
            return True

        def install_catalog_into_pack(self, *a, **k):
            raise AssertionError("not used")

    lf = _Lf()
    rows = [{"source": "modrinth", "project_id": "abc"}]
    out = run_modrinth_install_queue(
        lf,
        rows,
        packs_dir="/tmp/packs",
        minecraft_version="1.20.1",
        loader="forge",
        catalog_kind="mods",
        target_key="inst:i1",
        install_target_is_instance=True,
        instance_name="i1",
        pack_name=None,
        external_game_root=None,
        install_dependencies=True,
        allow_preflight_warn=False,
        allow_relaxed_fallback=True,
        max_items=5,
    )
    assert len(out) == 1 and out[0]["status"] == "installed"
    assert lf.installed == [("hit.jar", "mods", True)]
