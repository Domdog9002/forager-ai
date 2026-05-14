#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const baseUrl = process.env.FORAGER_DASHBOARD_URL || "http://127.0.0.1:8501";
const routes = [
  { label: "Home", heading: "START HERE" },
  { label: "Browse Modpacks", heading: "Search, browse, and download modpacks" },
  { label: "My Packs", heading: "My modpacks" },
  { label: "Power Center", heading: "FAST ACTIONS" },
  { label: "AI · Architect", heading: "Pack Architect" },
  { label: "Pack Health", heading: "Conflicts" },
];

function existingBrowserPath() {
  const candidates = [
    process.env.FORAGER_PLAYWRIGHT_BROWSER,
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function loadPlaywrightCore() {
  const candidates = [
    path.join(process.cwd(), "node_modules", "playwright-core"),
    "C:/Users/DCarl/.cursor/mcp-packages/playwright/node_modules/playwright-core",
    "C:/Users/DCarl/.cursor/mcp-packages/playwright/node_modules/playwright",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return require(candidate);
    }
  }
  throw new Error("playwright-core not found. Install Playwright or keep the Cursor Playwright MCP package available.");
}

async function dashboardIsReachable(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2500);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return response.ok || response.status < 500;
  } catch (_error) {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  if (!(await dashboardIsReachable(baseUrl))) {
    console.log(`SKIP: Forager dashboard is not reachable at ${baseUrl}. Start Streamlit first.`);
    process.exit(0);
  }

  const executablePath = existingBrowserPath();
  if (!executablePath) {
    console.log("SKIP: No Chrome/Edge executable found. Set FORAGER_PLAYWRIGHT_BROWSER to a browser path.");
    process.exit(0);
  }

  const { chromium } = loadPlaywrightCore();
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage();
  const results = [];
  async function assertNoPythonError(scope) {
    const body = await page.locator("body").innerText({ timeout: 15000 });
    if (/Traceback|NameError|ModuleNotFoundError|KeyError|AttributeError|TypeError|SyntaxError/i.test(body)) {
      throw new Error(`Python error visible after ${scope}`);
    }
  }
  async function clickSidebar(label) {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    await page.locator("label").filter({ hasText: new RegExp(`^\\s*${escaped}\\s*$`) }).first().click({ timeout: 15000 });
    await page.waitForTimeout(5000);
  }
  async function clickButton(label) {
    await page.getByRole("button", { name: label, exact: true }).first().click({ timeout: 15000 });
    await page.waitForTimeout(5000);
  }
  async function clickHomeAction(label, expectedText) {
    await clickSidebar("Home");
    await waitForBodyText("START HERE");
    await clickButton(label);
    await waitForBodyText(expectedText);
    await assertNoPythonError(`Home action ${label}`);
    results.push({ route: `Home action: ${label}`, ok: true });
  }
  async function waitForBodyText(text, timeout = 20000) {
    await page.waitForFunction(
      (expected) => document.body && document.body.innerText.includes(expected),
      text,
      { timeout },
    );
  }
  async function acceptStreamlitRerunIfNeeded() {
    const didClick = await page.evaluate(() => {
      const button = [...document.querySelectorAll("button")].find((node) =>
        ["Always rerun", "Rerun"].includes((node.textContent || "").trim()),
      );
      if (!button) {
        return false;
      }
      button.click();
      return true;
    });
    if (didClick) {
      await page.waitForTimeout(6000);
    }
  }
  try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
    await waitForBodyText("Forager AI");
    await acceptStreamlitRerunIfNeeded();

    for (const route of routes) {
      await clickSidebar(route.label);
      await waitForBodyText(route.heading);
      await assertNoPythonError(route.label);
      results.push({ route: route.label, ok: true });
    }

    await clickHomeAction("Power Center", "FAST ACTIONS");
    await clickHomeAction("Browse Modpacks", "Search, browse, and download modpacks");
    await clickHomeAction("Run Conflicts", "Compatibility command center");
    await clickHomeAction("Ask Assistant", "AI Assistant");
    await clickHomeAction("AI Council", "AI Council");
    await clickHomeAction("Open Power Center", "FAST ACTIONS");
    await clickHomeAction("Open Browse Modpacks", "Search, browse, and download modpacks");
    await clickHomeAction("Open My Packs", "Modpack Library");
    await clickHomeAction("Open AI Architect", "Pack Architect");

    await clickSidebar("Power Center");
    await waitForBodyText("FAST ACTIONS");
    await clickButton("Ask Assistant");
    await waitForBodyText("AI Assistant");
    await clickSidebar("Power Center");
    await waitForBodyText("FAST ACTIONS");
    results.push({ route: "Power Center hidden-route return", ok: true });

    await clickButton("Crashes");
    await waitForBodyText("Crashes");
    await clickSidebar("Power Center");
    await waitForBodyText("FAST ACTIONS");
    await clickButton("Advanced Tools");
    await waitForBodyText("Hub");
    await assertNoPythonError("Power Center shortcuts");
    results.push({ route: "Power Center shortcuts", ok: true });

    await clickSidebar("My Packs");
    const configure = page.locator("a.forager-card-link-button").filter({ hasText: "Configure" }).first();
    if (await configure.isVisible({ timeout: 5000 }).catch(() => false)) {
      await configure.click({ timeout: 15000 });
      await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
      await waitForBodyText("Configure Pack");
      await waitForBodyText("AI Atlas");
      await page.getByRole("tab", { name: "AI Mods", exact: true }).click({ timeout: 15000 });
      await waitForBodyText("AI Mod Foundry");
      await waitForBodyText("Professional Quality Gates");
      await waitForBodyText("Mini-Change Queue");
      await waitForBodyText("Texture Forge + Blockbench Assets");
      await waitForBodyText("Sound + Animation Requests");
      await waitForBodyText("Continuous Council Review");
      await waitForBodyText("Compiled Forge Mod Scaffold");
      await page.getByRole("tab", { name: "Texture Studio", exact: true }).click({ timeout: 15000 });
      await waitForBodyText("AI Texture Pack Studio");
      await waitForBodyText("Style Memory + Presets");
      await page.getByRole("button", { name: "Create / select texture pack", exact: true }).click({ timeout: 15000 });
      await page.waitForTimeout(5000);
      await waitForBodyText("Batch Replacement + Review Queue");
      await waitForBodyText("Pixel Tools + Repair");
      await waitForBodyText("Sound Forge");
      await waitForBodyText("Blockbench Hub");
      await waitForBodyText("Blockbench Animations");
      await waitForBodyText("Safety + Rollback");
      await assertNoPythonError("Configure Pack");
      results.push({ route: "My Packs Configure", ok: true });
    } else {
      results.push({ route: "My Packs Configure", ok: true, skipped: "no instances" });
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify({ baseUrl, executablePath, results }, null, 2));
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
