import streamlit as st
import os
import sys
import json

# Ensure local src package imports work when running from repo root or bundle.
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from forager_ai.ai.openrouter_client import generate_feature_payload
from forager_ai.analysis.mod_graph import build_graph, to_graphviz_dot
from forager_ai.diagnostics.crash_parser import analyze_crash_log
from forager_ai.diagnostics.performance import profile_pack
from forager_ai.engine.apply import (
    apply_feature_plan,
    list_checkpoints,
    preview_feature_plan,
    rollback_checkpoint,
    save_feature_plan,
)
from forager_ai.pack.manifest import init_pack_manifest, load_pack_manifest
from forager_ai.pack.compat_registry import list_compat_rules
from forager_ai.sync.drift import compare_pack_roots

# Config
THEME_DIR = r"C:\Apps\Forager ai\theme_rules"
MODS_DIR = r"C:\Users\DCarl\AppData\Roaming\.minecraft\mods" # Update to your active path
PACKS_DIR = os.path.join(os.path.dirname(__file__), "packs")

st.set_page_config(page_title="Forager AI Suite", layout="wide")

# --- CUSTOM THEMEING ---
st.markdown("""
    <style>
    .stApp { background-color: #2b2b2b; color: #e0e0e0; }
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: #3d3d3d; border-radius: 5px; padding: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🛡️ Forager AI: Developer Suite")

# --- NAVIGATION TABS ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [
        "🎮 Modpack Manager",
        "🤖 AI Feature Builder",
        "🧩 Dependency Graph",
        "⚡ Performance Profiler",
        "🔄 Server/Client Drift",
        "🧪 Recipe & Quality Lab",
        "🚨 Diagnostics",
    ]
)

with tab1:
    st.header("Modpack Control")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Active Themes")
        all_themes = [f.replace(".txt", "") for f in os.listdir(THEME_DIR) if f.endswith(".txt")]
        selected = st.multiselect("Toggle Logic Modules:", all_themes, default=["industrial"])
    with col2:
        st.subheader("Asset Monitor")
        st.write(f"Scanning: `{os.path.basename(MODS_DIR)}`")
        if st.button("Check for Forbidden Mods"):
            st.error("Found remnant of 'Alex's Caves' - Click to Purge.")

with tab2:
    st.header("AI Feature Builder")

    os.makedirs(PACKS_DIR, exist_ok=True)
    packs = sorted([d for d in os.listdir(PACKS_DIR) if os.path.isdir(os.path.join(PACKS_DIR, d))])

    if not packs:
        st.info("No packs found in `packs/`. Create one by adding a folder under packs.")
    else:
        selected_pack = st.selectbox("Select pack", packs)
        pack_root = os.path.join(PACKS_DIR, selected_pack)
        init_pack_manifest(pack_root)
        manifest = load_pack_manifest(pack_root)

        with st.expander("Pack context", expanded=False):
            st.json(manifest)

        api_key = st.text_input("OpenRouter API Key", type="password")
        model = st.text_input("Model", value="openrouter/auto")
        user_request = st.text_area(
            "Describe the feature you want",
            placeholder="Example: Add a balanced brass machine progression with Create + Ars Nouveau compat and matching config updates.",
            height=120,
        )

        if st.button("Generate feature plan"):
            try:
                payload = generate_feature_payload(
                    api_key=api_key,
                    model=model,
                    user_request=user_request,
                    pack_context=manifest,
                )
                st.session_state["forager_last_payload"] = payload
                st.success("Feature plan generated.")
            except Exception as exc:
                st.error(f"Failed to generate plan: {exc}")

        payload = st.session_state.get("forager_last_payload")
        if payload:
            explanation = payload.get("explanation", "")
            feature_plan = payload.get("feature_plan", {})
            st.subheader("AI explanation")
            st.write(explanation)
            st.subheader("Proposed FeaturePlan")
            st.code(json.dumps(feature_plan, indent=2), language="json")

            if st.button("Save generated plan JSON"):
                try:
                    saved_path = save_feature_plan(pack_root, payload, prefix="ai_feature_plan")
                    st.success(f"Saved plan to `{saved_path}`")
                except Exception as exc:
                    st.error(f"Failed to save plan: {exc}")

            preview = preview_feature_plan(pack_root, feature_plan)
            if not preview.get("ok"):
                st.error("Plan validation failed.")
                st.json(preview)
            else:
                st.success("Plan validation passed.")
                st.write(f"Actions: `{preview['actions_executed']}`")
                st.write("Files to write:")
                for rel in preview["files_to_write"]:
                    st.write(f"- `{rel}`")
                if preview.get("compat_actions"):
                    st.write("Compat rules to register:")
                    for rule in preview["compat_actions"]:
                        st.write(f"- `{rule['rule_name']}` -> `{', '.join(rule['affected_mods'])}`")

                st.subheader("Diff preview")
                for item in preview.get("diffs", []):
                    st.caption(f"`{item['path']}`")
                    st.code(item["diff"] or "(no textual diff)", language="diff")

                confirm = st.checkbox("I confirm applying this plan to the selected pack")
                apply_clicked = st.button("Apply plan")
                if apply_clicked and confirm:
                    try:
                        res = apply_feature_plan(pack_root, feature_plan, update_manifest=True)
                        st.success(f"Applied `{res.feature_name}` successfully.")
                        st.write(f"Files written: {len(res.files_written)}")
                        st.write(f"Checkpoint created: `{res.checkpoint_id}`")
                    except Exception as exc:
                        st.error(f"Failed to apply plan: {exc}")
                elif apply_clicked and not confirm:
                    st.warning("Please confirm before applying.")

        st.divider()
        st.subheader("Compat registry")
        compat_rules = list_compat_rules(pack_root)
        if compat_rules:
            st.write(f"Registered compat rules: `{len(compat_rules)}`")
            for rule in compat_rules:
                st.write(f"- `{rule.get('rule_name', 'unknown')}` :: {', '.join(rule.get('affected_mods', []))}")
        else:
            st.info("No compat rules registered yet.")

        st.subheader("Checkpoints and rollback")
        checkpoints = list_checkpoints(pack_root)
        if not checkpoints:
            st.info("No checkpoints yet.")
        else:
            checkpoint_options = [cp["checkpoint_id"] for cp in checkpoints]
            selected_checkpoint = st.selectbox("Select checkpoint to rollback", checkpoint_options)
            if st.button("Rollback selected checkpoint"):
                try:
                    rb = rollback_checkpoint(pack_root, selected_checkpoint)
                    st.success(
                        f"Rollback complete. Restored {len(rb['restored'])} and deleted {len(rb['deleted'])} files."
                    )
                except Exception as exc:
                    st.error(f"Rollback failed: {exc}")

with tab3:
    st.header("Dependency / Conflict Graph")
    os.makedirs(PACKS_DIR, exist_ok=True)
    graph_packs = sorted([d for d in os.listdir(PACKS_DIR) if os.path.isdir(os.path.join(PACKS_DIR, d))])
    if not graph_packs:
        st.info("No packs found in `packs/`.")
    else:
        selected_graph_pack = st.selectbox("Select pack for graph analysis", graph_packs)
        graph_pack_root = os.path.join(PACKS_DIR, selected_graph_pack)
        init_pack_manifest(graph_pack_root)
        graph_manifest = load_pack_manifest(graph_pack_root)

        graph_data = build_graph(graph_manifest)
        st.write(f"Nodes: `{len(graph_data['nodes'])}` | Edges: `{len(graph_data['edges'])}`")
        st.graphviz_chart(to_graphviz_dot(graph_data))

        st.subheader("Conflict / risk findings")
        findings = graph_data.get("findings", [])
        if not findings:
            st.success("No known hard/soft conflicts detected from current heuristic rules.")
        else:
            for item in findings:
                if item["severity"] == "high":
                    st.error(f"[HIGH] {item['mods']} - {item['note']}")
                else:
                    st.warning(f"[MEDIUM] {item['mods']} - {item['note']}")

with tab4:
    st.header("Performance Profiler")
    os.makedirs(PACKS_DIR, exist_ok=True)
    perf_packs = sorted([d for d in os.listdir(PACKS_DIR) if os.path.isdir(os.path.join(PACKS_DIR, d))])
    if not perf_packs:
        st.info("No packs found in `packs/`.")
    else:
        selected_perf_pack = st.selectbox("Select pack for profiling", perf_packs)
        perf_root = os.path.join(PACKS_DIR, selected_perf_pack)
        init_pack_manifest(perf_root)
        report = profile_pack(perf_root)

        st.write(f"Total files: `{report['summary']['total_files']}`")
        st.write(f"Total size: `{report['summary']['total_size_mb']} MB`")

        st.subheader("Section stats")
        for section, stats in report["sections"].items():
            st.write(
                f"- `{section}`: exists={stats['exists']} files={stats['files_count']} size={stats['size_mb']} MB"
            )

        st.subheader("Largest mod JARs")
        if not report["largest_mod_jars"]:
            st.info("No mod jars found in pack `mods/`.")
        else:
            for row in report["largest_mod_jars"]:
                st.write(f"- `{row['file']}` ({row['size_mb']} MB)")

        st.subheader("Performance findings")
        if not report["findings"]:
            st.success("No major footprint flags detected by current heuristics.")
        else:
            for finding in report["findings"]:
                if finding["severity"] == "high":
                    st.error(f"[HIGH] {finding['message']}")
                else:
                    st.warning(f"[MEDIUM] {finding['message']}")

with tab5:
    st.header("Server/Client Drift Detector")
    os.makedirs(PACKS_DIR, exist_ok=True)
    drift_packs = sorted([d for d in os.listdir(PACKS_DIR) if os.path.isdir(os.path.join(PACKS_DIR, d))])
    if len(drift_packs) < 2:
        st.info("Create at least two packs under `packs/` to compare client vs server.")
    else:
        client_pack = st.selectbox("Client pack", drift_packs, key="drift_client_pack")
        server_candidates = [p for p in drift_packs if p != client_pack]
        server_pack = st.selectbox("Server pack", server_candidates, key="drift_server_pack")
        client_root = os.path.join(PACKS_DIR, client_pack)
        server_root = os.path.join(PACKS_DIR, server_pack)
        init_pack_manifest(client_root)
        init_pack_manifest(server_root)

        if st.button("Run drift detection"):
            drift = compare_pack_roots(client_root, server_root)
            summary = drift["summary"]
            if summary["in_sync"]:
                st.success("Client and server packs are in sync for tracked directories.")
            else:
                st.warning(
                    f"Drift detected: high sections={summary['high_sections']} medium sections={summary['medium_sections']}"
                )

            for section, data in drift["sections"].items():
                st.subheader(f"`{section}` ({data['severity']})")
                st.write(f"Client-only files: `{len(data['client_only'])}`")
                st.write(f"Server-only files: `{len(data['server_only'])}`")
                st.write(f"Content mismatches: `{len(data['hash_mismatch'])}`")
                with st.expander(f"Show details for {section}", expanded=False):
                    if data["client_only"]:
                        st.write("Client-only:")
                        for rel in data["client_only"][:100]:
                            st.write(f"- `{rel}`")
                    if data["server_only"]:
                        st.write("Server-only:")
                        for rel in data["server_only"][:100]:
                            st.write(f"- `{rel}`")
                    if data["hash_mismatch"]:
                        st.write("Hash mismatch:")
                        for rel in data["hash_mismatch"][:100]:
                            st.write(f"- `{rel}`")

with tab6:
    st.header("Recipe & Quality AI")
    item_input = st.text_input("Enter Item Name (e.g., Brass Goggles):")
    if st.button("Assign AI Quality"):
        # This would trigger a prompt to your Llama 3 model
        st.success(f"Recommended Quality: **Clockwork** (Tier: 7)")

with tab7:
    st.header("AI Crash Investigator")
    crash_log = st.text_area("Paste Crash Log Here:", height=200)
    os.makedirs(PACKS_DIR, exist_ok=True)
    packs_for_diag = sorted([d for d in os.listdir(PACKS_DIR) if os.path.isdir(os.path.join(PACKS_DIR, d))])
    selected_diag_pack = st.selectbox("Target pack for hotfix actions", packs_for_diag) if packs_for_diag else None

    if st.button("Analyze with Forager AI"):
        if not crash_log.strip():
            st.warning("Paste a crash log first.")
        else:
            result = analyze_crash_log(crash_log)
            st.subheader("Crash summary")
            st.write(result["summary"])
            st.subheader("Findings")
            for finding in result["findings"]:
                st.write(f"- {finding}")
            st.subheader("Suggested hotfix FeaturePlan")
            st.code(json.dumps(result["feature_plan"], indent=2), language="json")
            st.session_state["forager_crash_plan"] = result["feature_plan"]

    crash_plan = st.session_state.get("forager_crash_plan")
    if crash_plan and selected_diag_pack:
        diag_pack_root = os.path.join(PACKS_DIR, selected_diag_pack)
        init_pack_manifest(diag_pack_root)
        preview = preview_feature_plan(diag_pack_root, crash_plan)
        if preview.get("ok"):
            st.subheader("Hotfix diff preview")
            for item in preview.get("diffs", []):
                st.caption(f"`{item['path']}`")
                st.code(item["diff"] or "(no textual diff)", language="diff")
            if st.button("Apply crash hotfix plan"):
                try:
                    res = apply_feature_plan(diag_pack_root, crash_plan, update_manifest=True)
                    st.success(f"Applied crash hotfix plan. Checkpoint: `{res.checkpoint_id}`")
                except Exception as exc:
                    st.error(f"Hotfix apply failed: {exc}")
        else:
            st.error("Crash hotfix plan failed validation.")
            st.json(preview)