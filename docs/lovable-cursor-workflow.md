# Lovable (Lovable.dev) + Cursor workflow

This repo documents how to **pair Lovable with Cursor** using GitHub. There is no native “Lovable inside Cursor” plugin; the integration is a **Git-backed loop** you operate in the browser (Lovable), on GitHub, and locally (Cursor).

Official product context: [Lovable workflow / capabilities FAQ](https://lovable.dev/faq/capabilities/workflow) and search their site for “Cursor” or “GitHub” pairing guides.

---

## 1. GitHub bridge (Lovable → GitHub)

Do this in **Lovable.dev** for each project you want in Cursor.

1. Open your project in Lovable.
2. Find **Git / GitHub / Connect repository** (wording varies by Lovable UI revision) in project settings or the publish/export area.
3. Connect **your** GitHub account if prompted (OAuth).
4. Create a new repo or link an existing empty repo Lovable is allowed to push to.
5. Complete Lovable’s **initial sync** so `main` (or their default branch) contains generated code.

### Verification checklist (you run this after connecting)

- [ ] GitHub shows commits from Lovable (not only an empty README).
- [ ] Default branch name matches what you expect (`main` vs `master`).
- [ ] You have **clone + push** rights on that repo (personal or org permissions).
- [ ] Optional: enable branch protection on `main` and use feature branches from Cursor (reduces overwrite surprises).

---

## 2. Clone in Cursor (local loop)

On your machine:

```powershell
cd C:\Apps
git clone https://github.com/YOUR_ORG/YOUR_LOVABLE_REPO.git
```

In **Cursor**: **File → Open Folder** → select the cloned directory.

### Day-to-day discipline

| When | Action |
|------|--------|
| Start work in Cursor | `git pull` (or Cursor’s Source Control pull) so you have Lovable’s latest |
| After editing in Cursor | Commit + `git push` so GitHub (and Lovable sync, if enabled) see your changes |
| After prompting in Lovable | `git pull` again before large refactors in Cursor |

### Useful Git commands

```powershell
git status
git pull --rebase origin main
git add -A
git commit -m "Describe change"
git push origin HEAD
```

Replace `main` with your default branch if different.

### If Lovable and Cursor both changed the same files

1. `git pull` and resolve merge conflicts in Cursor.
2. Prefer **short-lived branches** for Cursor work (`feature/cursor-tweak`), open a PR on GitHub, merge, then sync Lovable from `main`.

---

## 3. Optional: Cursor rules in the Lovable repo (not this repo)

Copy the template from [templates/lovable-react-stack.mdc](templates/lovable-react-stack.mdc) into **your Lovable project**:

`YOUR_LOVABLE_REPO/.cursor/rules/lovable-react-stack.mdc`

Adjust the rule body if your stack is Next.js vs Vite, different UI library, etc.

---

## Relation to Forager AI

**Forager** (this workspace) is **Streamlit + PyInstaller**. Lovable targets **web/React** stacks. Use Lovable + Cursor for **separate** web apps; do not expect Lovable to generate `dashboard.py` unless you intentionally port designs by hand.
