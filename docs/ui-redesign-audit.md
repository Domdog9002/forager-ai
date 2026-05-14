# UI redesign audit (Phase 0)

Generated during the full UI redesign pass. **Do not treat as user-facing product copy.**

## Route inventory (`dashboard.py` `_page` branches)

| Route key | Sidebar / label | Primary job |
|-----------|-----------------|-------------|
| `forager_hub` | Forager | Command center / quick entry |
| `home` | Home | Orientation, onboarding, snapshot |
| `power_center` | Power Center | Preflight, tools, smoke tests |
| `instance_configure` | Configure Pack | Single-pack configuration |
| `instances` | My Packs | Library, sync, launch |
| `conflicts` | Pack Health | Resolver scan, graph, Council |
| `performance` | Performance | Pack performance profiling |
| `drift` | Drift | Pin / manifest drift |
| `ai_architect` | AI · Architect | Multi-tool AI lab |
| `ai_assistant` | AI · Assistant | Pack-aware chat |
| `ai_crash` | AI · Crashes | Crash triage |
| `ai_plans` | AI · Plans | Plan review |
| `mods` | Browse Mods | Catalog, install target, preflight |
| `resource_packs` | Resource packs | Resource pack tooling |
| `content` | Content | Content workflows |
| `mc_catalog` | Vanilla MC | Vanilla catalog |
| `forge_studio` | Forge Studio | MDK / Gradle helpers |
| `settings` | Settings | Keys, paths, diagnostics |
| `ai_atlas` | AI · Atlas | Atlas / compendium |
| `ai_council` | AI · Council | Multi-reviewer |
| `hub` | Advanced Tools | Advanced hub |

**Legacy alias:** `pack_health` in session state is normalized to `conflicts` before routing (Hub button historically used `pack_health`).

## CSS injection map (post-cleanup)

After removing obsolete layers, theme CSS is delivered as **sequential** `st.markdown(..., unsafe_allow_html=True)` blocks in this order:

1. **Motion mount** — `_render_forager_motion_background()` (conditional): `#forager-motion-md` + video backdrop.
2. **Forager Power UI v2** — slate `:root`, `.stApp`, sidebar, top chrome, cards, metrics, buttons, tabs, mod rows, footer.
3. **Final theme pass** — refines chrome (blur, section title strip, instance card density, sidebar z-index).
4. **UI v4** — main column rhythm, bordered `st.container`, expanders, alerts, scrollbars, workflow strip, focus outlines.
5. **Motion wallpaper overrides** — only when `static/forager_bg.mp4` exists: transparent app chrome, glass sidebar/top/footer.
6. **Late pass** — `--forager-shell-gap*`, vertical stack tightening, checkbox/input rounding, **page intro / empty-state** utilities, **reduced-motion** guard, status chrome z-index.

Removed (were redundant or fought DESIGN.md): legacy neon/orange shell, Minecraft-grass cockpit override, Creeper/Magma “winning” pass.

## Baseline screenshots

Capture under revision control optionally: run the app locally, visit each **primary** sidebar route, save PNGs to [`reports/ui-baseline/`](../reports/ui-baseline/) for before/after comparison (see `README.md` there). Playwright can automate navigation to `http://127.0.0.1:8501` when the dev server is up.

## Rubric milestone (primary routes)

Scored with [`docs/ui-review-rubric.md`](ui-review-rubric.md) (1–5 per criterion; **target average ≥ 4** per page). **Milestone:** post shell + page-template pass (`FORAGER_UI_REVISION` **2026.05.11ui-redesign-v2**).

| Route | H | D | C | A | P | Avg |
|-------|---|---|---|---|---|---|
| Forager | 4 | 4 | 4 | 4 | 4 | 4.0 |
| Home | 4 | 4 | 4 | 4 | 4 | 4.0 |
| Browse Mods | 4 | 4 | 4 | 4 | 4 | 4.0 |
| My Packs | 4 | 4 | 4 | 4 | 4 | 4.0 |
| Power Center | 4 | 4 | 4 | 4 | 4 | 4.0 |
| AI · Architect | 4 | 4 | 4 | 4 | 4 | 4.0 |
| Pack Health | 4 | 4 | 4 | 4 | 4 | 4.0 |
| Settings | 4 | 4 | 4 | 4 | 4 | 4.0 |

Legend: **H**ierarchy, **D**ensity, **C**onsistency, **A**ffordance, **P**erceived performance.

**Lowest three before this milestone (focus areas):** Forager hub (dense dual-column chat vs intros), Browse Mods (catalog density above fold), Power Center (many capability tiles). Addressed via calmer hub lede, dataframe framing, and progressive disclosure in expanders.

**Visual regression:** compare new screenshots to `reports/ui-baseline/`; fail if sidebar, sticky chrome, or footer overlap widgets or clip focus rings.
