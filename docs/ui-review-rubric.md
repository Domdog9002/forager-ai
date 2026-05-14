# UI review rubric (Forager Streamlit shell)

Score each **primary** page 1–5 (1 poor, 5 excellent). Target average **≥ 4** before closing a redesign milestone.

| Criterion | What “good” looks like |
|-----------|-------------------------|
| **Hierarchy** | One clear focal point; secondary actions grouped; advanced items in expanders. |
| **Density** | No wall of simultaneous dense tables above the fold; breathing room between sections. |
| **Consistency** | Same radii, spacing, and alert patterns as other routes; sidebar labels match chrome title. |
| **Affordance** | Primary button obvious; destructive actions labeled; save flows explicit. |
| **Perceived performance** | No layout jump under sticky chrome; spinners and captions feel intentional. |

## Visual regression

Compare current screenshots to `docs/ui-redesign-audit.md` baseline folder (if present). Fail the gate if sidebar, chrome, or footer overlap widgets or clip focus rings.

## Iteration budget

Allow **two** full passes over low-scoring pages, then a final polish (contrast, motion, focus) before shipping a new `Forager_Dev_Suite*.exe`.

**Milestone log:** see scored primary-route table in [`docs/ui-redesign-audit.md`](ui-redesign-audit.md) (`FORAGER_UI_REVISION` **2026.05.11ui-redesign-v2**).
