// Money and energy formatting for the CRM screens.
//
// Invoices are calculated by the backend (POST /crm/readings), from the tariff
// stored there, so no billing formula lives in the browser any more. The
// currency is the one the backend reports (GET /crm/tariff), LBP by default.

let currency = 'LBP';

export function setCurrency(code) {
  if (code) currency = code;
}

export function getCurrency() {
  return currency;
}

export function formatCurrency(amount) {
  const digits = currency === 'LBP' ? 0 : 2;
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(amount || 0);
  } catch {
    return `${(amount || 0).toFixed(digits)} ${currency}`;
  }
}

export function formatKwh(kwh) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(kwh || 0) + ' kWh';
}

// For headline cards: "LBP 538.8M" instead of "LBP 538,809,412", which does
// not fit a card once amounts are in Lebanese pounds.
export function formatCurrencyShort(amount) {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(amount || 0);
  } catch {
    return formatCurrency(amount);
  }
}
