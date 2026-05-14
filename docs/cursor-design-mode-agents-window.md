# Cursor Design Mode (Agents Window)

How to use Cursor **Design Mode** in the **Agents Window** browser: select UI, describe changes, and **Apply** so Cursor updates your code.

## Prerequisites

- Cursor **3+** with Agents Window / Browser features enabled for your account.
- A **running UI** you can open in the Agents Window browser (local dev URL or deployed site).

### Forager AI (this repo)

The dashboard is **Streamlit** (`dashboard.py`). Design Mode targets **HTML/CSS in the browser**. It does not replace editing `st.*` layout in Python—you still review diffs and may need to map visual tweaks back to Streamlit widgets and injected CSS.

---

## 1. Open the Agents Window

1. Press **Command Palette**: `Ctrl + Shift + P` (Windows/Linux) or `Cmd + Shift + P` (Mac).
2. Search **`agents`** and run one of these (wording depends on Cursor build):
   - **View: New Agents Window** (common in current builds)
   - **Open Agents Window** (older docs / some builds)
3. Optional: **View: All Agents** (`Ctrl + Shift + /`) opens the agents list from the palette.

---

## 2. Load the page you want to edit

1. In the **Agents Window**, use the **Browser** pane.
2. Navigate to your app’s URL (e.g. local Streamlit: `http://localhost:8501` or whatever port you use).

Until the correct page is visible, Design Mode has nothing meaningful to attach to.

---

## 3. Toggle Design Mode

1. `Ctrl + Shift + P` / `Cmd + Shift + P`.
2. Run **Toggle Design Mode** (exact name may vary slightly by Cursor version; search `design` if needed).

You should see selectable regions or a design sidebar when the browser is on a real UI page.

---

## 4. Select UI and describe changes

- **Shift + drag** to select an area, or click individual elements (depends on Cursor version).
- Use the **design sidebar** or chat-style prompt to say what to change (layout, copy, spacing, etc.).

---

## 5. Apply changes

1. Click **Apply** in the design sidebar (wording may be **Apply changes**).
2. Wait for the agent to patch files; refresh the browser if the UI does not hot-reload.

Review the **git diff** before committing.

---

## Troubleshooting

| Symptom | What to try |
|--------|-------------|
| **Toggle Design Mode** does nothing or no targets | Focus the **Agents Window** browser on the live page URL, not a markdown tab. |
| No **Open Agents Window** in palette | Search **`agents`** and use **View: New Agents Window** (current label in many builds). |
| Command palette shows unrelated “mode” commands | For Design Mode, search **Toggle Design** (not “language mode”). |
| Shortcut ignored | Click inside Cursor first, then `Ctrl + Shift + P` again. |
| Changes don’t match Streamlit structure | Expect to translate browser tweaks into `dashboard.py` / CSS blocks manually. |

---

## Acceptance checklist

- [ ] Agents Window open.
- [ ] Browser shows the target UI URL.
- [ ] Design Mode toggled on.
- [ ] Element selected; change described; **Apply** used.
- [ ] Code updated and verified in diff / rerun app.
