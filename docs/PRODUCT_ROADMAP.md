# Forager AI — product roadmap

Phased delivery is tracked here. **Major roadmap slices are implemented** in `dashboard.py` (Browse Mods → **Exports & mods diff**) and supporting `src/forager_ai/` modules. Update this file when you add a new surface.

---

## Trust & reproducibility

- [x] **Mods folder lockfile** — `forager_mods.lock.json` / export (`forager_ai.ops.mods_folder_lockfile`, Browse Mods → Exports).
- [x] **Two-instance mods diff (MVP)** — same screen: only-in-A / only-in-B / same logical jar, different hash.
- [x] **Install provenance** — `cache/install_provenance.jsonl` + table (`forager_ai.launcher.install_provenance`, Browse Mods → Exports).
- [x] **Human in the loop** — Settings: **Block all AI plan applies** and **Require “Mark diffs reviewed” before Apply** (`launcher_core` `ai_apply_blocked` / `ai_writes_require_preview`, plan apply gates in `dashboard.py`).

## Instance & catalog awareness

- [x] **Instance diff** — `mods/` compare + surface folders + **deep `config/`** text diff capped (`compare_surface_folders`, `compare_config_deep_limited`, Browse Mods batch 2).
- [x] **Lock attestation sidecar** — `forager_mods.lock.meta.json` (`forager_ai.ops.lock_attestation`).
- [x] **Diff two lockfiles** — paste JSON A/B (`forager_ai.ops.lock_diff`).
- [x] **Catalog offline mode** — Settings toggle (`launcher_core` `catalog_offline_mode`).
- [x] **Mod pin / channel** — `catalog_pins` + optional **`channel`** tag; **on-demand** + **optional auto** Modrinth pin drift vs newest listing (`forager_ai.ops.pin_drift`, **Settings** `catalog_pin_drift_auto`, Browse Mods).

## Health & launch

- [x] **Pre-launch health (Browse Mods)** — install target preflight (`forager_ai.diagnostics.instance_preflight`).
- [x] **Version solver hints** — relaxed Modrinth list ranked; **CurseForge** strict miss falls back to ranked files + hint lines (`forager_ai.launcher.version_hints`, Browse Mods Install).

## AI & content

- [x] **Crash flow** — heuristics + **Issue / Discord markdown** from last analysis (`forager_ai.ops.crash_ticket`, `ai_crash` in `dashboard.py`).
- [x] **KubeJS / CraftTweaker / datapack copilot** — scoped editor + OpenRouter draft (review-only) (`forager_ai.pack.pack_text_ops`, Browse Mods batch 2).
- [x] **Config surgeon** — same editor + UTF-8 backups + **config playbooks** expander (`forager_ai.pack.playbooks`, `pack/data/config_playbooks.json`).
- [x] **Mod interaction cards** — compat rules vs installed jar ids (`forager_ai.pack.compat_hints`, Browse Mods batch 2).
- [x] **Mob scaffold (Forge)** — Power Center / Architect: zip download (`forager_ai.mods.mob_scaffold`, playbooks JSON).

## Team & server

- [x] **Server parity** — client vs server list / manifest paste (`forager_ai.ops.server_manifest`, Browse Mods batch 2).
- [x] **Shareable pack sheet** — `PACK_SHEET.md` (`forager_ai.pack.pack_sheet`).
- [x] **Pack profiles** — role tags + export + **paste JSON diff vs client** (`build_pack_profile_from_lock`, Browse Mods batch 2).

## Heavier ops

- [x] **Scheduled tasks** — list + **quick add**, **mark done by index**, overdue table + jump to Browse Mods (`forager_ai.ops.reminders`, Browse Mods batch 2).
- [x] **Git-aware** — `git status -sb -- packs` + unstaged **`--stat` / `--name-status` / patch** + **`git diff --cached --stat`** (staged) + **`git log -8 --oneline -- packs`** + **`git stash list`** (first 8) + **branch @ short SHA** (`dashboard.py` Browse Mods → Exports).
- [x] **Issue harvester** — Modrinth/Curse URLs (`forager_ai.tools.issue_harvest`).
- [x] **Asset audit** — largest jars, totals, duplicate logical names (`forager_ai.diagnostics.asset_audit`, Browse Mods → Exports).
- [x] **Support bundle zip** — `forager_ai.ops.support_bundle`.
- [x] **JVM hints** — read-only from default RAM (`forager_ai.diagnostics.jvm_hints`).
- [x] **Environment fingerprint** — OS / Python / Java + **`git --version`** + **Streamlit version** (`forager_ai.diagnostics.env_fingerprint`).
- [x] **latest.log tail** — (`forager_ai.diagnostics.log_tail`).
- [x] **Session install queue** — dedupe on add, **move row up / down**, scratch ids + **`queue.txt`** + **`queue_resolve.json`** + **Resolve queue** + **Modrinth link list** from last resolve (`forager_ai.ops.queue_resolution`, Browse Mods).

## AI behavior (local profile)

- [x] **Skeptical assistant mode** — Settings → **Skeptical assistant** toggles `user_profile.json` **`skeptical_mode`**; injects pushback guidance into adaptation context and interactive assistant system prompts (`user_adaptation.py`, `assistant_voice.py`).
- [x] **Batch 1 — AI context + trust** — `build_pack_ai_context` adds **confirmed facts**, **health narrative**, **budgeted context cards** (lock excerpt, change trace, provenance, optional git name-status); **crash ticket** embeds log tail / lock digest / jar count / provenance when a pack is selected; **support bundle** includes `latest_log_tail.txt`; Settings: **context card toggles** + **bulk fact import** (`pack_context.py`, `context_snippets.py`, `crash_ticket.py`, `support_bundle.py`, `dashboard.py`).
- [x] **Batch 2 — Surfaces + Council parity** — optional **environment fingerprint** + **install-target preflight** context cards (`format_env_fingerprint_text`, `format_preflight_narrative`, `build_pack_ai_context`); **AI · Council** optional pack overlay + auto quality Council; **Pack Health** conflicts page **Pack AI context preview**; support bundle **`env_fingerprint.json`** (`council.py`, `pack_context.py`, `support_bundle.py`, `dashboard.py`).
- [x] **Batch 3 — Diagnostics in context + exports** — optional **JVM hints** + **mods asset audit** context cards; **`build_pack_ai_context_export_text`** + hub / Pack Health download; **crash ticket** adds JVM + asset sections; support bundle **`mods_asset_audit.json`** + **`jvm_hints.txt`** (`context_snippets.py`, `asset_audit.py`, `context_export.py`, `pack_context.py`, `crash_ticket.py`, `support_bundle.py`, `dashboard.py`).
- [x] **Batch 4 — Known issues + structured export + bundle parity** — optional **known-issue DB** context card (`build_known_issues_probe_text`, `pack_context` **`known_issue_hints`**); **AI context JSON export** (`build_pack_ai_context_export_json`); **crash ticket** known-issue section; support bundle **`interaction_memory_tail.txt`** + slim **`preflight_snapshot.json`** when launcher + resolver passed (`known_issues.py`, `context_export.py`, `crash_ticket.py`, `support_bundle.py`, `pack_context.py`, `dashboard.py`).

---

## Future polish (not blocking)

- [x] **Three-way merge preview + full-repo git** — Exports: **Git — full repository** (`git status` / `diff` / `log` at repo root) + read-only **`git merge-tree`** preview from two refs (`dashboard.py` next to packs-scoped git).
- [x] **Chained Modrinth installs from the session queue** — Browse Mods → **Session install queue** → **Install queue (runs each row)** with optional relaxed file pick + preflight-warn bypass (`forager_ai.ops.queue_resolution.run_modrinth_install_queue`).

_Update this file when a slice lands: check the box and add a one-line pointer to module or UI location._

---

## Modpack-developer UX (incremental batches)

High-trust ergonomics **for authors/maintainers** (not casual players). Ships in phases.

### Batch 1 — Hub readability & grounding

- [x] **Stream chat answers** — Forager hub **Ask Forager AI**: OpenRouter SSE stream + `st.write_stream` fallback to one-shot completion (`chat_completion_text_stream` · `dashboard.py`).
- [x] **Retrieval citations surface** — After a hub reply (non-feature-plan paths), expandable **notebook sources**: path-level cites + retrieval meta from `retrieve_for_assistant` (`dashboard.py`).

### Batch 2 — Dev session memory (lightweight)

- [x] **Per-pack turn tape** — Last **N** Q/A pairs in session (or keyed by `pack_root` slug) under the hub, with explicit clear (`dashboard.py` · `_forager_hub_tape_*` · expander below Message).
- [x] **Re-open last composer** optional restore from tape on pack switch guardrails (`_FORAGER_HUB_RESTORE_OFFER_KEY` · empty composer only · Load / Dismiss).

### Batch 3 — Reproducibility & exports

- [x] Append **Retrieval citations** appendix to **`build_pack_ai_context_export_*`** when `ctx` carries `retrieval_citations` / `retrieval_meta` (`context_export.py` · `format_retrieval_export_text_appendix`); hub merges **`forager_hub_last_retrieval_by_pack`** snapshot on **Build export** (same UI entry).
- [x] **Locks / provenance** one-liner under **`st.success`** after export build (`dashboard.py` · `lockfile_sha256_hex` + `read_install_provenance_tail`).

### Batch 4 — Ship quality & CI parity

- [x] Align **PyInstaller hidden imports** with `forager_ai.ai` hub chain: **`embedding_rag`**, **`light_rag`**, **`git_context`**, **`hub_citations`** (`Forager_Dev_Suite.spec` · plus existing `collect_submodules('forager_ai')`; no `forager_*` lines in typical `warn-*.txt`).
- [x] **Automated regression** — SSE deltas (`tests/test_openrouter_sse.py` · `content_parts`, first-choice, empty delta); hub citation bullets (`tests/test_hub_citations.py` · `format_hub_retrieval_citation_markdown` in `hub_citations.py`).

### Batch 5 — Authoring memory & grounded hub prompts *(first brainstorm batch)*

- [x] **Author-maintained authoring brief** — `.forager/authoring_brief.json` (goals, non-goals, audience, today’s focus); Hub expander · merged into **`build_pack_ai_context`** (`authoring_brief`, `authoring_brief_narrative`) · text + JSON export sections (`authoring_memory.py`, `pack_context.py`, `context_export.py`, `dashboard.py`).
- [x] **Decision log** — append-only `.forager/decision_log.jsonl`; Hub append UI; surfaced as **`decision_log_narrative`** (+ recent rows in JSON export) (`authoring_memory.py`, `dashboard.py`).
- [x] **Hub shortcut prompts** — ship-readiness audit · server parity · tester brief · regression check (`dashboard.py` · `_FORAGER_HUB_QUICK_PROMPTS`; example grid covers all entries).
- [x] **Hub system prompt tightening** — tagged claims, regression / git + trace awareness, destructive-plan caution; references new context keys (`dashboard.py` · `FORAGER_CENTER_BRAIN_NOTE`).
- [x] **Optional reply feedback log** — `.forager/hub_feedback.jsonl` from Hub (`authoring_memory.py`, `dashboard.py`).
- [x] **Tests** — `tests/test_authoring_memory.py`.

### Batch 6 — Diff-aware Hub + golden prompts + grounding checklist *(brainstorm Batch B · first slice)*

- [x] **Golden / regression prompts** — `.forager/golden_prompts.json`; Hub expander (edit, save, queue **#…** into chat); merged via **`build_pack_ai_context`** (`golden_prompts`, `golden_prompts_narrative`) + export appendix (`authoring_memory.py`, `pack_context.py`, `context_export.py`, `dashboard.py`).
- [x] **Compare vs reference profile** — workspace selectbox; **`compare_mods_roots`** + **`compare_surface_folders`** → `reference_pair_diff_narrative` merged into Hub **`unified_ctx`** and **Build export** when set (`hub_reference_diff.py`, `dashboard.py`).
- [x] **Author-facing grounding checklist** — Hub expander (self-review bullets) (`dashboard.py`).
- [x] **No-key Hub cue** — caption under missing OpenRouter key pointing at **`/help`** / local shortcuts (`dashboard.py`).
- [x] **Tests** — `tests/test_hub_reference_diff.py`; golden roundtrip in `tests/test_authoring_memory.py`.

---

## AI brainstorming — backlog *(after Batch 6)*

Remaining ideas; not started:

- [ ] Claim → evidence **automation** (post-parse or UI validation beyond the Batch 6 checklist).
- [ ] Bounded read-only **tools** for the assistant (`read_file` / manifest peek with audit log).
- [ ] Tiered models (triage vs synthesis) + visible routing reason.
- [ ] Cascade Council (cheap screening pass → full Council on flag).
- [ ] Stronger offline Hub (richer template fallbacks when keys missing / network down).
- [ ] Decision log pinning & tape **“remember this turn”** linkage.
- [ ] Issue-harvest / community digest merged into context cards.
- [ ] Dedicated **`serverProfile`** slice in AI context.
- [ ] Sandbox / duplicate-profile workflow before risky experiments.
- [ ] Playbook natural-language triggers (**`config_playbooks`**).
