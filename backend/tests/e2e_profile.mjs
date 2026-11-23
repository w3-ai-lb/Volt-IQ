/**
 * End-to-end check of the two ProfilePage fixes (audit gaps 1 and 2).
 *
 * Drives the real built frontend against the real backend, because both bugs
 * were invisible from the API alone: the endpoints did not exist and the page
 * only ever wrote to localStorage, so the UI reported success either way.
 *
 * Everything it changes it changes back, so the demo account is left exactly
 * as the seeder made it.
 */
import { chromium } from 'playwright';

const WEB = 'http://localhost:5173';
const EMAIL = 'customer@nxttrn.com';
const PASS = 'customer123';
const NEW_PASS = 'e2e-temp-8241';

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
const page = await browser.newPage();

const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

async function login(password) {
  await page.goto(`${WEB}/login`, { waitUntil: 'networkidle' });
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');
  try {
    await page.waitForURL('**/app/**', { timeout: 12000 });
    return true;
  } catch { return false; }
}

async function logout() {
  await page.evaluate(() => localStorage.clear());
}

// ---------------------------------------------------------------- gap 2
console.log('\n=== Profile edit persists (gap 2) ===');
check('signs in with the seeded password', await login(PASS));

await page.goto(`${WEB}/app/profile`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);

// Address the fields by the id the Input component derives from its label,
// rather than by position, the page has a header search box too.
const phoneBox = page.locator('#phone');
const addrBox = page.locator('#address');
const originalPhone = await phoneBox.inputValue();
const originalAddr = await addrBox.inputValue();

const stampPhone = '+961 3 449 077';
const stampAddr = 'Hamra Street, Ras Beirut, Beirut';
await phoneBox.fill(stampPhone);
await addrBox.fill(stampAddr);

const [saveRes] = await Promise.all([
  page.waitForResponse((r) => r.url().includes('/profile') && r.request().method() === 'PATCH',
                       { timeout: 12000 }).catch(() => null),
  page.locator('button:has-text("Save changes")').click(),
]);
check('the page actually calls PATCH /profile', saveRes !== null,
      'no PATCH request left the browser');
check('PATCH /profile returns 200', saveRes?.status() === 200, `status ${saveRes?.status()}`);
await page.waitForTimeout(600);
check('shows a success toast',
      await page.locator('text=Profile updated').count() > 0);

// Clear the browser's copy of the user, sign in again, and see whether the
// edit came back from the database rather than from localStorage.
await logout();
check('signs back in', await login(PASS));
await page.goto(`${WEB}/app/profile`, { waitUntil: 'networkidle' });
await page.waitForTimeout(900);
const phoneAfter = await page.locator('#phone').inputValue();
const addrAfter = await page.locator('#address').inputValue();
check('phone survived a fresh sign-in', phoneAfter === stampPhone, `got "${phoneAfter}"`);
check('address survived a fresh sign-in', addrAfter === stampAddr, `got "${addrAfter}"`);

// Put the seeded values back.
await page.locator('#phone').fill(originalPhone);
await page.locator('#address').fill(originalAddr);
await page.locator('button:has-text("Save changes")').click();
await page.waitForTimeout(900);

// ---------------------------------------------------------------- gap 1
console.log('\n=== Password change takes effect (gap 1) ===');
await page.goto(`${WEB}/app/profile`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);

// The Input component derives its id from `name` when one is given, and from
// the label otherwise. The profile fields gained `name` attributes when the
// interface was translated, because a label-derived id changes with the
// language; these ids are the stable ones.
const PWD_IDS = ['#current-password', '#new-password', '#confirm-password'];
const pwdBoxes = () => ({ nth: (i) => page.locator(PWD_IDS[i]) });

// Wrong current password must be refused, not silently "succeed".
await pwdBoxes().nth(0).fill('definitely-not-it');
await pwdBoxes().nth(1).fill(NEW_PASS);
await pwdBoxes().nth(2).fill(NEW_PASS);
await page.locator('button:has-text("Update password")').click();
await page.waitForTimeout(1200);
check('wrong current password is refused in the UI',
      await page.locator('text=Could not change password').count() > 0);

// Correct current password.
await pwdBoxes().nth(0).fill(PASS);
await pwdBoxes().nth(1).fill(NEW_PASS);
await pwdBoxes().nth(2).fill(NEW_PASS);
const [pwdRes] = await Promise.all([
  page.waitForResponse((r) => r.url().includes('/auth/change-password'),
                       { timeout: 12000 }).catch(() => null),
  page.locator('button:has-text("Update password")').click(),
]);
check('the page calls POST /auth/change-password', pwdRes !== null);
check('change-password returns 200', pwdRes?.status() === 200, `status ${pwdRes?.status()}`);
await page.waitForTimeout(700);
check('confirms the change', await page.locator('text=Password changed').count() > 0);
check('clears the password fields', (await pwdBoxes().nth(0).inputValue()) === '');

// The real test: does the new password work and the old one stop working?
await logout();
check('old password no longer signs in', (await login(PASS)) === false);
check('new password signs in', await login(NEW_PASS));

// Restore the documented demo password.
await page.goto(`${WEB}/app/profile`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
await pwdBoxes().nth(0).fill(NEW_PASS);
await pwdBoxes().nth(1).fill(PASS);
await pwdBoxes().nth(2).fill(PASS);
await page.locator('button:has-text("Update password")').click();
await page.waitForTimeout(1200);
await logout();
check('demo password restored', await login(PASS));

const realErrors = consoleErrors.filter(
  (t) => !/401|Failed to load resource|change-password|400|409/.test(t)
);
check('no unexpected console errors', realErrors.length === 0, realErrors.slice(0, 3).join(' | '));

await browser.close();
console.log('\n' + '='.repeat(58));
console.log(`  PASSED: ${pass}    FAILED: ${fail.length}`);
console.log('='.repeat(58));
if (fail.length) { fail.forEach((f) => console.log(`  x ${f}`)); process.exit(1); }
