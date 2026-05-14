---
version: alpha
name: Forager AI Launcher
description: Streamlit shell — Forge Pro / Launcher v3 (zinc neutrals + single sky accent). Aligns with dashboard.py :root tokens and forager-ui-mockups.
colors:
  primary: "#0ea5e9"
  on-primary: "#fafafa"
  surface-base: "#09090b"
  surface-raised: "#18181b"
  surface-sidebar: "#0c0c0e"
  text-primary: "#fafafa"
  text-secondary: "#e4e4e7"
  text-muted: "#a1a1aa"
  border-subtle: "#27272a"
  border-strong: "#3f3f46"
  accent-sky: "#0ea5e9"
  accent-sky-strong: "#0284c7"
  accent-sky-soft: "rgba(14, 165, 233, 0.12)"
  success: "#22c55e"
  warning: "#eab308"
  danger: "#f43f5e"
typography:
  brand-title:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 1.125rem
    fontWeight: "700"
    lineHeight: "1.25"
  brand-subline:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 0.8125rem
    fontWeight: "500"
    lineHeight: "1.35"
  chrome-title:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 1rem
    fontWeight: "600"
    lineHeight: "1.3"
  body:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 0.9375rem
    fontWeight: "400"
    lineHeight: "1.5"
  label:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 0.8125rem
    fontWeight: "500"
    lineHeight: "1.4"
  chip:
    fontFamily: ui-sans-serif, system-ui, sans-serif
    fontSize: 0.75rem
    fontWeight: "500"
    lineHeight: "1.2"
rounded:
  sm: 6px
  md: 10px
  lg: 12px
spacing:
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.accent-sky}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.accent-sky-strong}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
  card-elevated:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "{spacing.md}"
  sidebar-surface:
    backgroundColor: "{colors.surface-sidebar}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
  top-chrome:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.chrome-title}"
    padding: "{spacing.sm}"
  env-chip:
    backgroundColor: "{colors.surface-base}"
    textColor: "{colors.text-muted}"
    typography: "{typography.chip}"
    rounded: "{rounded.sm}"
    padding: 6px
  brand-line:
    textColor: "{colors.text-primary}"
    typography: "{typography.brand-title}"
  brand-sub:
    textColor: "{colors.accent-sky}"
    typography: "{typography.brand-subline}"
---

## Overview

Forager AI is a **launcher-first** desktop experience built in **Streamlit** (`dashboard.py`). The shipped visual system is **Forge Pro / Launcher v3**: **zinc** neutrals (`#09090b` canvas, `#18181b` raised surfaces, `#0c0c0e` sidebar) with a **single sky accent** (`#0ea5e9` / `#0284c7`). Surfaces are **flat solids** and thin borders (`#27272a`); avoid multi-stop cyan–purple gradients and “generic AI” glow unless a feature explicitly needs a semantic state color.

Primary implementation: **injected CSS** (`:root` / `--fp-*` tokens in `dashboard.py`), **`st.sidebar`** for navigation (vertical radio list), and **sticky top chrome** in the main column. Main content max width is about **1680px** (`--forager-content-max`).

## Colors

- **`{colors.surface-base}`** — App background.
- **`{colors.surface-raised}`** — Cards, panels, top chrome, command decks.
- **`{colors.surface-sidebar}`** — Sidebar rail.
- **`{colors.text-primary}`** / **`{colors.text-secondary}`** / **`{colors.text-muted}`** — Hierarchy for titles, body, and metadata.
- **`{colors.accent-sky}`** / **`{colors.accent-sky-strong}`** — Primary actions, active env pill, nav selection bar, links that should read as “do the thing”.
- **`{colors.border-subtle}`** / **`{colors.border-strong}`** — Dividers and widget outlines.
- **`{colors.success}`** / **`{colors.warning}`** / **`{colors.danger}`** — Status only; do not replace sky as the main accent.

CSS aliases in code often mirror these as `--fp-bg`, `--fp-bg-raised`, `--fp-accent`, `--fp-border`, etc.

## Typography

Use the **system UI sans** stack (`ui-sans-serif, system-ui, …`). **Brand title** is semibold; **subline** (“Modlauncher Ops”) uses the sky token. **Chrome title** sits in the sticky header with the current nav label. **Chips** match env tabs (Forge 1.20.1, Modpack Library; optional Approvals when the inbox has items). **Pack Health** appears in the suggested-flow strip under chrome, not duplicated in env tabs.

## Layout

- **Sidebar**: Brand, **Tips** (popover when Streamlit supports it, else expander), **+ New Instance**, vertical **radio** nav, instance inventory strip.
- **Main column**: Back control + **`forager-top-chrome`** (title, scope, env tabs, workflow strip, CurseForge API pill), then scrollable content.
- **Spacing**: Prefer `{spacing.sm}`–`{spacing.xl}` between sections; late-pass shell uses `--forager-shell-gap` for vertical rhythm.

## Elevation & Depth

Elevation is **one step** from base to raised panels, plus an **inset highlight** (`box-shadow: 0 1px 0 rgba(255,255,255,0.04)`) on cards—avoid heavy multi-layer glow. Optional motion background stays **under** UI (`z-index: -1`); when enabled, sidebar/top may use **translucent zinc + blur**, still aligned to sky—not green.

## Shapes

Corners use **`{rounded.md}`** (~10px) for most controls and **`{rounded.lg}`** (~12px) for cards and chrome. Pills stay fully rounded for chips and small status badges.

## Components

Map Streamlit and CSS class intent to these tokens:

| Concept | CSS / Streamlit hint | Token mapping |
|--------|----------------------|----------------|
| Primary CTA | `type="primary"` buttons, play/install links | `button-primary` |
| Elevated panel | `st.container(border=True)`, `.forager-card` | `card-elevated` |
| Sidebar chrome | `forager-stitch-*`, nav radio | `sidebar-surface`, `brand-line`, `brand-sub` |
| Sticky header row | `forager-top-chrome` | `top-chrome` |
| Env pills | `forager-env-tabs` | `env-chip` |
| Page lede | `forager_page_intro()` → `.forager-page-intro` | Raised panel + border |
| Empty / zero-data | `forager_empty_state()` → `.forager-empty-state` | Dashed border, muted body |
| Catalog / library chrome | `forager-library-toolbar`, `forager-mod-browser` | Same raised tier as cards |

Python helpers: [`src/forager_ai/ui/page_frame.py`](src/forager_ai/ui/page_frame.py) (`forager_page_intro` for page headlines + optional lede).

## Layout recipes (Streamlit)

[`src/forager_ai/ui/layout_recipes.py`](src/forager_ai/ui/layout_recipes.py):

| Recipe | Helper | Use when |
|--------|--------|----------|
| Elevated panel | `elevated_section()` | Onboarding, grouped explanations |
| Equal tool grid | `columns_equal(n)` | 2–4 parallel actions |
| List + detail | `columns_main_side()` | Filters + results |
| AI workspace + context | `columns_ai_lab()` | Chat with context rail |

**Navigation labels** (exact strings, sidebar order): Home, Browse Modpacks, My Packs, Power Center, AI · Architect, Pack Health, Settings. Hidden routes use labels like **Configure Pack**, **Approvals Inbox**, **AI · Council** in those flows only.

## Do's and Don'ts

**Do**

- Prefer **Streamlit-shaped** primitives: `st.sidebar`, `st.columns`, `st.container(border=True)`, `st.popover` where available.
- Reuse **`forager-stitch-brand`**, **`forager-top-chrome`**, **`forager-mod-browser`** when bridging design to `dashboard.py`.
- Preserve **launcher semantics**: packs/instances, Modrinth/CurseForge catalogs, jar enable/disable.

**Don't**

- Invent sidebar items or rename **My Packs** / **Pack Health**.
- Default to stock light Streamlit unless the user asks for a light theme.
- Reintroduce **purple gradient** as a default shell treatment; reserve purple for rare semantic emphasis if needed.

When tokens or layout are ambiguous, **`dashboard.py`** (`FORGER_NAV_ITEMS`, `forager-stitch-*`, `:root` / finale `html body` overrides) is the source of truth.
