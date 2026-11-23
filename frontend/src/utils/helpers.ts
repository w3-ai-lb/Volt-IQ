import { getDirection, getLanguage, t, type LanguageCode } from '@/i18n/t';

/**
 * Money, and why it is not dollars.
 *
 * THE BUG THIS REPLACES
 * ---------------------
 * `formatCurrency` defaulted to USD, and not one of its thirty call sites
 * passed a currency, so every amount in the product wore a dollar sign: the
 * revenue card, every bill, every payment, every outstanding balance.
 *
 * The provider's data disagrees on every row of it. All 5,400 invoices, all
 * 5,229 payments and all 18 monthly tariffs are marked LBP. This is a Lebanese
 * ishtirak billing in Lebanese pounds, and a bill that says $2,900 when the
 * invoice says 2,900,000 LBP is not a formatting preference, it is a wrong
 * number by a factor of about a thousand.
 *
 * WHY THE CODE IS PRINTED RATHER THAN A SYMBOL, AND NOT TRANSLATED
 * ---------------------------------------------------------------
 * `LBP` is treated the same way `kWh` is: a unit, identical in every language,
 * left out of the catalogue on purpose. See the note at the top of
 * i18n/translations.ts. It also matches what the database literally stores in
 * its `currency` column, so a figure on screen and a figure in a query read
 * the same, and the Energy Loss page already prints it that way.
 *
 * WHY NO DECIMALS
 * ---------------
 * The smallest note in circulation is 1,000 LBP. Two decimal places on a
 * nine-digit number are noise that pushes the digits that matter off the edge
 * of a card.
 */

export const DISPLAY_CURRENCY = 'LBP';

/**
 * A figure kept in left-to-right order in a right-to-left page.
 *
 * In Arabic the bidi algorithm reorders a run such as "4,725,839 LBP",
 * "453.9 kWh" or "-6.5%" into "LBP 4,725,839", "kWh 453.9" and "6.5%-",
 * wherever it stands: in a table cell as much as in a sentence. A figure with
 * an element of its own can be isolated by the `ltr-num` class (index.css), but
 * most are plain text: a cell, a chart label, a value put into a translated
 * sentence by t(). So the formatters below return them wrapped in the Unicode
 * isolate marks (U+2066 LEFT-TO-RIGHT ISOLATE ... U+2069 POP DIRECTIONAL
 * ISOLATE), which do in plain text what the class does in CSS and are not
 * displayed. Only in a right-to-left interface: elsewhere there is nothing to
 * reorder and the text is returned as it is.
 */
export function ltr(text: string): string {
  return getDirection() === 'rtl' ? `\u2066${text}\u2069` : text;
}

/**
 * "16,301,139 LBP", "453.9 kWh": a figure and its unit, joined by a no-break
 * space so a narrow column cannot put the unit on a line of its own.
 */
export function withUnit(figure: string, unit: string): string {
  return ltr(`${figure}\u00a0${unit}`);
}

/**
 * Full precision. For tables, invoice detail, anywhere with room for it.
 *
 *     formatCurrency(16301139)  ->  '16,301,139 LBP'
 */
export function formatCurrency(value: number, currency = DISPLAY_CURRENCY): string {
  const amount = Number.isFinite(value) ? value : 0;

  // Intl renders LBP as "LBP 16,301,139.00" with the code in front and two
  // decimals it does not have. Everything else, a provider paid in USD or
  // EUR one day, is left to Intl, which knows those conventions better.
  if (currency === 'LBP') {
    return withUnit(new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(amount), currency);
  }
  return ltr(new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(amount));
}

/**
 * Shortened, for the stat cards where five sit across one row.
 *
 *     formatCurrencyCompact(50334857806)  ->  '50.3B LBP'
 *
 * LBP amounts run to eleven digits, and the full figure does not fit beside
 * four others at card size. The kWh cards were already shortened this way, so
 * this is the same decision applied to the column next to them. Tables and
 * detail views keep the exact figure.
 */
export function formatCurrencyCompact(value: number, currency = DISPLAY_CURRENCY): string {
  const amount = Number.isFinite(value) ? value : 0;
  return withUnit(formatCompact(amount), currency);
}

/** Energy, in full: '6,902.5 kWh'. */
export function formatKwh(value: number): string {
  return withUnit(formatNumber(Number.isFinite(value) ? value : 0), 'kWh');
}

/** Energy, shortened for the stat cards: '1.2M kWh'. */
export function formatKwhCompact(value: number): string {
  return withUnit(formatCompact(Number.isFinite(value) ? value : 0), 'kWh');
}

export function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

/*
 * DATES AND MONTH NAMES ARE WRITTEN IN THE INTERFACE LANGUAGE
 * ------------------------------------------------------------
 * Numbers keep one style in every language (see the note on numerals in
 * i18n/arabic.ts), but a month is a word, and "Jun 2026" on an Arabic page is
 * an untranslated word. The browser knows every month name in every language,
 * so these ask it, with Western digits kept throughout. Arabic uses the
 * Levantine month names (ar-LB), as on the provider's own bills.
 */
const LOCALES: Record<LanguageCode, string> = {
  en: 'en-US',
  ar: 'ar-LB-u-nu-latn',
  es: 'es-ES',
  fr: 'fr-FR',
  de: 'de-DE',
  zh: 'zh-CN',
  ja: 'ja-JP',
};

/** The locale dates are written in for the current interface language. */
export function dateLocale(): string {
  return LOCALES[getLanguage()] ?? 'en-US';
}

/**
 * A date as "Mar 31, 2025" in English, "31 آذار 2025" in Arabic, and so on.
 *
 * A bare YYYY-MM-DD is a calendar day, not an instant. The browser reads it as
 * midnight UTC, which west of Greenwich is the evening before, so it is
 * formatted in UTC to keep the day the server meant.
 */
export function formatDate(iso: string): string {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  return new Date(iso).toLocaleDateString(dateLocale(), {
    month: 'short', day: 'numeric', year: 'numeric', ...(dateOnly ? { timeZone: 'UTC' } : {}),
  });
}

const EN_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const EN_MONTHS_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
  'September', 'October', 'November', 'December'];

/**
 * A month label from the API in the interface language.
 *
 * Accepts what the backend sends: "2026-06" (a `period`), "Jun 2026" or
 * "June 2026" (a bill, a revenue period), or "Jun" alone (a chart point).
 * With a year the year is kept; `shortYear` writes it with two digits, for
 * chart axes where twelve labels have to fit. Anything else comes back as it
 * was, so an unexpected value is shown rather than lost.
 */
export function formatMonthLabel(label: string, shortYear = false): string {
  let year: number | null = null;
  let month = -1;
  const period = /^(\d{4})-(\d{2})$/.exec(label);
  const named = /^([A-Z][a-z]+)(?:\s+(\d{4}))?$/.exec(label.trim());
  if (period) {
    year = Number(period[1]);
    month = Number(period[2]) - 1;
  } else if (named) {
    month = EN_MONTHS.indexOf(named[1]);
    if (month < 0) month = EN_MONTHS_FULL.indexOf(named[1]);
    year = named[2] ? Number(named[2]) : null;
  }
  if (month < 0 || month > 11) return label;
  const at = new Date(Date.UTC(year ?? 2000, month, 1));
  return new Intl.DateTimeFormat(dateLocale(), {
    month: 'short',
    ...(year !== null ? { year: shortYear ? '2-digit' : 'numeric' } : {}),
    timeZone: 'UTC',
  }).format(at);
}

/**
 * What an alert's severity is called on screen.
 *
 * The stored values are error / warning / info / success, which are software
 * states: a customer shown "error" beside an unpaid bill reasonably thinks the
 * site has broken. The value stays as stored (it chooses the colour); only its
 * name on the badge changes.
 */
const SEVERITY_LABELS: Record<string, string> = {
  error: 'Urgent',
  warning: 'Attention',
  info: 'For information',
  success: 'Good news',
};

export function severityLabel(severity: string): string {
  return t(SEVERITY_LABELS[severity] ?? severity);
}

/** "Week 12", as the forecast labels its points, in the interface language. */
export function formatWeekLabel(label: string): string {
  const match = /^Week (\d+)$/.exec(label.trim());
  return match ? t('Week {n}').replace('{n}', match[1]) : label;
}

/** "Mon" ... "Sun" from the API in the interface language. */
export function formatWeekday(abbr: string): string {
  const index = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(abbr);
  if (index < 0) return abbr;
  // 1 January 2024 was a Monday.
  return new Intl.DateTimeFormat(dateLocale(), { weekday: 'short', timeZone: 'UTC' })
    .format(new Date(Date.UTC(2024, 0, 1 + index)));
}

export function classNames(...parts: Array<string | false | null | undefined | 0>): string {
  return parts.filter(Boolean).join(' ');
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
