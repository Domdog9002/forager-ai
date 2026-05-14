# Forager AI — Approvals-first UI (mock reference)

Streamlit-shaped wireframes aligned with [`DESIGN.md`](../DESIGN.md) tokens and the live shell in [`dashboard.py`](../dashboard.py). Implementation touchpoints: **Settings → Safety & approvals**, hidden route **Approvals Inbox** (`?forager_nav=approvals_inbox`), and the shared apply gate in `_forager_feature_plan_apply_allowed`.

---

## A. Settings — Safety & approvals (always visible strip)

ASCII layout (main column, below saved keys / model rows as in product):

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Safety & approvals                                                       │
│ Global switches affect every AI write path that applies feature plans.   │
│                                                                          │
│  [ ] Block all AI plan applies (Plans page, crash hotfix apply,          │
│       instance plan Apply)                                               │
│                                                                          │
│  [ ] Require “Mark diffs reviewed” before each Apply (after preview      │
│       succeeds)                                                          │
│                                                                          │
│  [ Open Approvals Inbox ]     (→ ?forager_nav=approvals_inbox)           │
│                                                                          │
│  Caption: Pending items are listed in the Inbox; approving diffs there   │
│  unlocks Apply for the same plan fingerprint everywhere.                │
└─────────────────────────────────────────────────────────────────────────┘
```

Streamlit mapping: `st.markdown` kicker + `st.checkbox` ×2 + `st.button` / link-style button; optional `st.container(border=True)`.

---

## B. Approvals Inbox — list (`_page == "approvals_inbox"`)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Pending approvals                                    [ All | Plans | … ] │
│                                                                          │
│  Item                          Pack              Risk        Waiting   │
│  ─────────────────────────────────────────────────────────────────────  │
│  config_assistant_draft          packs/MyPack      file_writes  2m ago   │
│                                   [ Review ] [ Reject ]                  │
│                                                                          │
│  Crash hotfix — mixin conflict   packs/Diag        file_writes  12m ago  │
│                                   [ Review ] [ Reject ]                  │
│                                                                          │
│  (empty state)                                                           │
│  Nothing waiting — generate a plan under AI · Plans, AI · Architect,     │
│  or AI · Crashes; new previews appear here for review.                   │
└─────────────────────────────────────────────────────────────────────────┘
```

Streamlit mapping: filter `st.radio` or horizontal pills; each row `st.columns` + `st.button("Review")` sets session detail id; **Reject** calls persisted status update.

---

## C. Item detail — card stack + shared review footer

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ← Back to list                                                           │
│                                                                          │
│  Summary                                                                 │
│  Title: config_assistant_draft                                           │
│  Pack root: …/packs/MyPack                                               │
│  Source: AI · Architect          [ Open in AI · Architect ]              │
│                                                                          │
│  Generated plan   (forager-kicker)                                       │
│  [ quality gate / JSON expanders same as live review ]                   │
│                                                                          │
│  Diffs (preview_feature_plan)                                            │
│  path/to/file …                                                         │
│  @@ diff text …                                                          │
│                                                                          │
│  [ Mark diffs reviewed (enables Apply for this plan) ]   ← canonical   │
│                                                                          │
│  [ Send to AI Council ]  [ Save plan ]  [ Apply plan ]                  │
│                                                                          │
│  [ Reject and remove from queue ]                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

Streamlit mapping: reuse `_render_feature_plan_review` for the middle block so **preview_feature_plan**, **Apply**, and **Council** match other routes. **Reject** only updates inbox store + clears detail.

---

## D. Source screens (banner — future optional)

When a plan is also in the inbox queue, a compact `st.info` banner can deep-link: “This plan is pending approval — **Open Approvals Inbox**.” (Optional polish; not required for MVP queue accuracy.)

---

## Copy alignment (canonical strings)

Use these **verbatim** in UI and tests so the inbox and legacy routes stay mentally one product:

| Intent | Canonical control label |
|--------|---------------------------|
| Acknowledge diffs before Apply | `Mark diffs reviewed (enables Apply for this plan)` |
| Human-in-the-loop hint when preview is OK but not yet marked | `**Human in the loop:** confirm you reviewed the diffs, then unlock **Apply**.` |
| Gate blocked caption | `Click **Mark diffs reviewed** for this plan, or disable **Require diff review before Apply** in Settings.` |
| Apply writes | `Apply plan` |
| Save artifact | `Save plan` |
| Council handoff | `Send to AI Council` |
| Settings — block writes | `Block all AI plan applies (Plans page, crash hotfix apply, instance plan Apply)` |
| Settings — review gate | `Require “Mark diffs reviewed” before each Apply (after preview succeeds)` |

**Crash hotfix row** (AI · Crashes) uses the same **Mark diffs reviewed** string as Architect/Plans; the Apply button label there remains **`Apply crash hotfix plan`** (domain-specific) but the unlock semantics are identical (fingerprint-scoped session unlock).

**Navigation labels** for cross-links: use `FORGER_NAV_LABEL_BY_KEY` strings, e.g. **AI · Plans**, **AI · Architect**, **AI · Crashes**, **Settings**.

---

## `/go` shortcut

- `/go approvals` and `/go inbox` → hidden route `approvals_inbox` (see `assistant_commands.py`).
