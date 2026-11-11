import { TRANSLATIONS } from '@/i18n/translations';

/**
 * The translation function and the store behind it.
 *
 * WHY THE KEY IS THE ENGLISH SENTENCE
 * -----------------------------------
 * Every entry in the catalogue is keyed by its English text rather than by an
 * invented identifier like `dashboard.header.title`. Two reasons, and both
 * matter more than tidiness:
 *
 *   1. A missing translation falls back to a correct English sentence. With
 *      invented keys a gap in the catalogue puts `dashboard.header.title` on
 *      the screen, which is worse than the untranslated word it replaced.
 *   2. The source stays readable. `t('Outstanding Balance')` says exactly what
 *      will be rendered. `t('dash.card.4')` does not.
 *
 * This is how GNU gettext has worked for thirty years, for the same reasons.
 *
 * WHY `t` IS A PLAIN FUNCTION AND NOT A HOOK
 * ------------------------------------------
 * Because interface text is not only written inside components. Navigation
 * entries, report catalogues and quick actions are declared as constants at
 * module level, where no hook can be called. A plain function reads the same
 * everywhere. Re-rendering is handled by I18nProvider, which remounts the tree
 * when the language changes, so nothing is left showing the old language.
 *
 * WHAT IS NOT TRANSLATED HERE
 * ---------------------------
 * Records: a customer's name, a region, a zone, an alarm text from the
 * provider's controller. Translating them would mean shipping a dictionary of
 * the provider's own records and would make a bill say something the bill does
 * not say, so they are shown as the database holds them.
 *
 * The sentences the backend writes (an alert, a recommendation, the reasons
 * beside a risk score, a zone's explanation) do not come through here either:
 * the server writes them in the reader's language, which this app sends with
 * every request (services/api.ts, backend/app/core/i18n.py). A refusal from the
 * server is the one exception that does: it is a fixed sentence with an entry
 * in this catalogue (utils/errors.ts).
 */

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'ar', label: 'العربية' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]['code'];

/**
 * Languages written right to left. Arabic is the only one here today, but the
 * set is what the code tests against rather than the string 'ar', so adding
 * Hebrew or Persian later is a one-line change and not a hunt through the app.
 */
const RTL_LANGUAGES = new Set<LanguageCode>(['ar']);

export function directionOf(code: LanguageCode): 'rtl' | 'ltr' {
  return RTL_LANGUAGES.has(code) ? 'rtl' : 'ltr';
}

export function getDirection(): 'rtl' | 'ltr' {
  return directionOf(current);
}

/**
 * Distance for a panel that slides in from the edge of the screen.
 *
 * Panels are anchored with logical properties (`start-0`, `end-0`), so in
 * Arabic the edge they are pinned to is the opposite physical side and the
 * animation has to travel the other way. Passing a raw pixel offset would slide
 * the mobile menu in from off-screen on the wrong side.
 */
export function slideFrom(pixels: number): number {
  return getDirection() === 'rtl' ? -pixels : pixels;
}

/**
 * WHERE THE CHOICE LIVES
 * ----------------------
 * In two places, like the theme, and for the same reasons:
 *
 *   - localStorage, read synchronously before the first paint, so the page is
 *     never drawn in English and then flipped, and so a right-to-left reader
 *     does not see the layout mirror itself a moment after it appears.
 *   - customers.language in the database, which is the source of truth. It is
 *     what makes the language belong to the account rather than to the machine:
 *     two people sharing a browser each keep their own, and a newly registered
 *     account starts from the default instead of inheriting the last person's.
 *
 * The cache below is only ever a cache. I18nProvider replaces it with the
 * signed-in user's stored value on sign-in and on reload.
 */
const STORAGE_KEY = 'energy-language';

/** True for a code this app actually ships a catalogue for. */
export function isLanguageCode(value: unknown): value is LanguageCode {
  return typeof value === 'string' && LANGUAGES.some((l) => l.code === value);
}

/** The stored choice, else the browser's own language, else English. */
function initialLanguage(): LanguageCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (isLanguageCode(stored)) return stored;

    const fromBrowser = navigator.language?.slice(0, 2).toLowerCase();
    if (isLanguageCode(fromBrowser)) return fromBrowser;
  } catch {
    // Storage can be unavailable in private browsing. English is the fallback.
  }
  return 'en';
}

let current: LanguageCode = initialLanguage();
const listeners = new Set<() => void>();

export function getLanguage(): LanguageCode {
  return current;
}

export function setLanguage(code: LanguageCode): void {
  if (code === current) return;
  current = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // Not being able to remember the choice is not a reason to refuse it.
  }
  // Screen readers and the browser's own translation prompt both read `lang`.
  // `dir` is what actually mirrors the page: it moves the sidebar to the right,
  // flips text alignment, and switches every logical CSS property in the
  // stylesheet. Setting it on <html> is what makes one attribute do the work of
  // a second stylesheet.
  document.documentElement.lang = code;
  document.documentElement.dir = directionOf(code);
  listeners.forEach((listener) => listener());
}

export function subscribeLanguage(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Translates one interface string. Returns the English text when there is no entry. */
export function t(text: string): string {
  if (current === 'en') return text;
  return TRANSLATIONS[current]?.[text] ?? text;
}
