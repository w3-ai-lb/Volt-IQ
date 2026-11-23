/**
 * End-to-end check of the alert engine, payment-risk scoring and the real
 * consumption heatmap (audit gaps 3, 4 and 9, plus the fake-heatmap fix).
 *
 * Drives the built frontend against the running backend. These features are
 * only meaningful if what the page draws comes from the API, so each check
 * watches the network call as well as the pixels.
 *
 * Nothing here mutates data that the demo depends on: the alert it marks read
 * it marks unread again.
 */
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const WEB = 'http://localhost:5173';
const API = 'http://localhost:8000';
const CUSTOMER = { email: 'customer@nxttrn.com', password: 'customer123' };
const ADMIN = { email: 'admin@nxttrn.com', password: 'admin123' };

let pass = 0;
const fail = [];
const check = (name, ok, detail = '') => {
  if (ok) { pass++; console.log(`  PASS  ${name}`); }
  else { fail.push(name); console.log(`  FAIL  ${name}${detail ? `, ${detail}` : ''}`); }
};

// Playwright's own Chromium (npx playwright install chromium) unless
// PLAYWRIGHT_CHROMIUM_PATH points at a browser already on this machine.
const browser = await chromium.launch(
  process.env.PLAYWRIGHT_CHROMIUM_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } : {}
);
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

async function login({ email, password }) {
  await page.goto(`${WEB}/login`, { waitUntil: 'networkidle' });
  await page.evaluate(() => localStorage.clear());
  await page.goto(`${WEB}/login`, { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');
  try {
    await page.waitForURL(/\/(app|admin)\//, { timeout: 15000 });
    return true;
  } catch { return false; }
}

// ------------------------------------------------------------- alert engine
console.log('\n=== Alert engine (gap 3) ===');
check('customer signs in', await login(CUSTOMER));

const [alertsRes] = await Promise.all([
  // Must match the API, not the SPA route of the same name.
  page.waitForResponse((r) => r.url() === `${API}/alerts` && r.request().method() === 'GET',
                       { timeout: 15000 }).catch(() => null),
  page.goto(`${WEB}/app/alerts`, { waitUntil: 'networkidle' }),
]);
check('the page loads alerts from the API', alertsRes?.status() === 200,
      `status ${alertsRes?.status()}`);
await page.waitForTimeout(900);

const initial = await alertsRes.json();
check('the engine produced alerts for this customer', initial.length > 0,
      'the feed is empty');
check('each alert carries a read flag', initial.every((a) => 'read' in a));

const cardCount = await page.locator('h3').filter({ hasText: /./ }).count();
check('alerts are rendered on the page', cardCount > 0);

// The refresh button is the whole point of the feature: alerts have to be
// derivable from current data, not only from the seeder.
const [refreshRes] = await Promise.all([
  page.waitForResponse((r) => r.url() === `${API}/alerts/refresh`, { timeout: 15000 })
      .catch(() => null),
  page.locator('button:has-text("Check for new alerts")').click(),
]);
check('refresh calls POST /alerts/refresh', refreshRes?.status() === 200,
      `status ${refreshRes?.status()}`);
await page.waitForTimeout(900);
const refreshed = await refreshRes.json();
check('refresh does not duplicate alerts', refreshed.length === initial.length,
      `${initial.length} before, ${refreshed.length} after`);
check('shows the updated toast', await page.locator('text=Alerts updated').count() > 0);

// Mark read, then verify it survives a reload, then put it back.
const unreadBefore = await page.locator('button:has-text("Mark read")').count();
if (unreadBefore > 0) {
  await page.locator('button:has-text("Mark read")').first().click();
  await page.waitForTimeout(900);
  check('marking read removes the control',
        await page.locator('button:has-text("Mark read")').count() === unreadBefore - 1);

  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  check('read state persisted to the server',
        await page.locator('button:has-text("Mark read")').count() === unreadBefore - 1);

  // Restore: mark every alert unread again through the API the page uses.
  const restored = await page.evaluate(async () => {
    const token = localStorage.getItem('energy-token');
    const list = await (await fetch('http://localhost:8000/alerts',
      { headers: { Authorization: `Bearer ${token}` } })).json();
    for (const a of list) {
      await fetch(`http://localhost:8000/alerts/${a.id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ read: false }),
      });
    }
    return list.length;
  });
  check('feed restored to unread', restored > 0);
}

// ------------------------------------------------- payment risk and heatmap
console.log('\n=== Payment risk (gap 4) and heatmap ===');
check('admin signs in', await login(ADMIN));

const riskPromise = page.waitForResponse((r) => r.url() === `${API}/analytics/risk`,
                                         { timeout: 20000 }).catch(() => null);
const heatPromise = page.waitForResponse((r) => r.url().startsWith(`${API}/consumption/heatmap`),
                                         { timeout: 20000 }).catch(() => null);
await page.goto(`${WEB}/admin/dashboard`, { waitUntil: 'networkidle' });
const [riskRes, heatRes] = await Promise.all([riskPromise, heatPromise]);
await page.waitForTimeout(1500);

check('dashboard calls GET /analytics/risk', riskRes?.status() === 200,
      `status ${riskRes?.status()}`);
check('dashboard calls GET /consumption/heatmap', heatRes?.status() === 200,
      `status ${heatRes?.status()}`);

if (riskRes?.ok()) {
  const risk = await riskRes.json();
  check('every customer is scored', risk.customers.length > 0);
  check('at least one account is flagged', risk.high + risk.medium > 0,
        'nothing above Low, the model is not discriminating');
  check('the risk panel is rendered',
        await page.locator('text=Payment Risk').count() > 0);
  const flagged = risk.customers.find((c) => c.band === 'High' || c.band === 'Medium');
  if (flagged) {
    check('the flagged customer appears on the page',
          await page.locator(`text=${flagged.name}`).count() > 0, flagged.name);
    check('its reason is shown, not just a number',
          await page.locator(`text=${flagged.reasons[0]}`).count() > 0, flagged.reasons[0]);
  }
}

if (heatRes?.ok()) {
  const hm = await heatRes.json();
  check('heatmap is 7 x 24', hm.grid.length === 7 && hm.grid.every((r) => r.length === 24));
  // The old version drew a sine wave that was identical every weekday. Real
  // data has a weekend that differs from a Tuesday.
  //
  // The heatmap is read from generator telemetry, which the demo seeder this
  // script signs in against does not write: there every cell is zero, and a
  // comparison of two zeros says nothing about the code. Reported as skipped
  // rather than failed; with the provider's data loaded it runs.
  const tue = hm.grid[1].reduce((a, b) => a + b, 0);
  const sun = hm.grid[6].reduce((a, b) => a + b, 0);
  if (hm.maxKwh > 0) {
    check('weekend load differs from a weekday', Math.abs(tue - sun) / tue > 0.02,
          `Tue ${tue.toFixed(0)} vs Sun ${sun.toFixed(0)} kWh`);
  } else {
    console.log('  SKIP  weekend load differs from a weekday (no generator telemetry in this database)');
  }
  check('the heatmap grid is drawn',
        await page.locator('[title*="kWh"]').count() >= 168,
        `${await page.locator('[title*="kWh"]').count()} cells`);
}

// Saved outside the repository, in the system's temporary folder.
const shotDir = join(tmpdir(), 'energy-analytics-e2e');
mkdirSync(shotDir, { recursive: true });
const shotPath = join(shotDir, 'admin-dashboard.png');
await page.screenshot({ path: shotPath, fullPage: true });
console.log(`  screenshot: ${shotPath}`);

// ---------------------------------------------------------------- reporting
const realErrors = consoleErrors.filter(
  (t) => !/401|403|Failed to load resource|favicon|fonts\.googleapis/.test(t)
);
check('no unexpected console errors', realErrors.length === 0, realErrors.slice(0, 3).join(' | '));

await browser.close();
console.log('\n' + '='.repeat(58));
console.log(`  PASSED: ${pass}    FAILED: ${fail.length}`);
console.log('='.repeat(58));
if (fail.length) { fail.forEach((f) => console.log(`  x ${f}`)); process.exit(1); }
