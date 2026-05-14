# Forager AI (Minecraft Modpack Helper) - Claude Context

## Role
You are an AI assistant helping build and maintain **Forager AI**, a Minecraft modpack helper.

## Project Overview
Forager AI is a specialized, AI-driven development environment and launcher designed for the Minecraft Forge ecosystem. It is currently a standalone application that serves as a central dashboard for complex modpack management and technical troubleshooting.

### Product direction (launcher-first)
Forager AI should be primarily a Minecraft launcher (Modrinth/CurseForge-style) with an AI built in.

The AI should let users:
- Edit and generate configuration content (e.g., modpack/config files).
- Manage custom mods and modpack components.
- Define and maintain cross-mod compatibility (“compats”) and guidance.
- Request new features in plain language (e.g., “add a feature”), then receive more information about the feature and have the AI implement it.

“Implement it” includes updating/generating:
- configs
- mods (custom additions/changes where applicable)
- texture packs
- animations

### Intended Uses & Core Features
- Unified Launcher & IDE: The tool is designed to act as a complete launcher with a mod interface—similar to CurseForge—where users can install mods, modpacks, and textures directly.
- "Vast Intellect" System: It serves as an intelligent "Architect" that understands cross-mod compatibility, such as how Ars Nouveau magic interacts with Create technology.
- Automated Development: Users can utilize the AI to edit configurations, change mod features, and generate custom scripts for KubeJS and CraftTweaker.
- Performance Optimization: Built to be lightweight, it prioritizes manual system resource control to ensure high performance.

### Technical Specifications
- Strict Encoding: To prevent critical "null byte" errors, the tool strictly enforces UTF-8 (No BOM) encoding for all code and configuration files.
- Build Environment: Developed using Python, Streamlit, and PyInstaller to function as a stable standalone executable.

## Current runtime constraints
- Primary goal: provide accurate, practical guidance for modpack building workflows.
- Prefer small, safe iterations over large risky refactors.

## Budget / model notes
- OpenRouter balance available: `$5.00`
- Be mindful of token usage and avoid unnecessary long outputs.

## Project focus
When suggesting changes, prioritize:
- Correctness of modpack logic and metadata handling
- Reliability of scraping / parsing / automation flows
- Clear UX for the Streamlit dashboard (if applicable)
- Reproducibility (document steps and assumptions)

## Coding standards
- Keep code changes minimal and easy to review.
- Add lightweight checks/tests when they provide real regression value.
- Follow existing style conventions in the repository.

## Safety & integrity
- Do not invent APIs, files, or configuration that are not present in the repo.
- If key files are missing (e.g., config, metadata schema), ask before proceeding.

## To fill in
- Link to relevant docs (if any)
- Any environment variables / required configuration
- Any known limitations or next milestones

## PyInstaller — Dev Suite exe

### Agent / automation workflow

When you finish a task that modifies **anything bundled into the launcher** (`dashboard.py`, `run_dashboard.py`, `src/**`, bundled `scripts/`, `theme_rules/`, or `Forager_Dev_Suite.spec`), **run a clean rebuild in the same session** unless the user forbids it or the environment lacks PyInstaller. Skip for docs/tests-only deltas with no shipped behavior change. See **`.cursor/rules/forager-pyinstaller-exe.mdc`** for scope.

Whenever dashboard, launcher services, packaging (`Forager_Dev_Suite.spec`), or other **shipped exe** behavior changes, **always** do a **clean rebuild** so users never pick up stale binaries:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_forager_exe.ps1
```

Wipe PyInstaller outputs **without** rebuilding (e.g. before a manual PyInstaller run):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_forager_exe.ps1 -CleanOnly
```

- **Always** close a running `Forager_Dev_Suite*.exe` first (otherwise deletes may fail; the script warns if a matching process is still running).
- **`scripts/build_forager_exe.ps1`** removes **`dist/Forager_Dev_Suite*`** (exe/pkg and stray warn/xref files), wipes **`build/Forager_Dev_Suite*`** work dirs, runs PyInstaller with **`--noconfirm --clean`**, then prints the new **`dist\Forager_Dev_Suite*.exe`** path(s).

# Forager AI Project Standards
- **Minecraft Version**: 1.20.1 (Forge)
- **Key Mods**: Create, Ars Nouveau, Iron's Spells, Origins.
- **UI Style**: Professional Slate (#0f172a / #1e293b).
- **Architecture**: UI in `dashboard.py`, Logic in `services/`.
- **Safety**: No writing to `.ini` or `.toml` without a backup in `/backups`.