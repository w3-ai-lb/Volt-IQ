// Electricity Tariff calculation formulas

export const TARIFF_RATES = {
  Residential: {
    baseFee: 10.00,
    tiers: [
      { maxKwh: 200, rate: 0.12 },
      { maxKwh: 500, rate: 0.18 },
      { maxKwh: Infinity, rate: 0.25 }
    ]
  },
  Commercial: {
    baseFee: 25.00,
    tiers: [
      { maxKwh: 1000, rate: 0.22 },
      { maxKwh: Infinity, rate: 0.28 }
    ]
  },
  Industrial: {
    baseFee: 75.00,
    tiers: [
      { maxKwh: Infinity, rate: 0.19 }
    ]
  }
};

export const VAT_RATE = 0.10; // 10% tax

export function calculateBillDetails(kwhConsumed, tariffType = 'Residential', customRate = null) {
  const kwh = Math.max(0, parseFloat(kwhConsumed) || 0);
  const tariff = TARIFF_RATES[tariffType] || TARIFF_RATES.Residential;
  
  let consumptionCharge = 0;
  if (customRate !== null && customRate !== undefined && customRate > 0) {
    consumptionCharge = kwh * customRate;
  } else {
    let remainingKwh = kwh;
    let prevLimit = 0;
    for (const tier of tariff.tiers) {
      if (remainingKwh <= 0) break;
      
      const tierCapacity = tier.maxKwh - prevLimit;
      const kwhInTier = Math.min(remainingKwh, tierCapacity);
      
      consumptionCharge += kwhInTier * tier.rate;
      remainingKwh -= kwhInTier;
      prevLimit = tier.maxKwh;
    }
  }

  const baseCharge = tariff.baseFee;
  const subtotal = baseCharge + consumptionCharge;
  const taxAmount = subtotal * VAT_RATE;
  const totalAmount = subtotal + taxAmount;

  return {
    kwhConsumed: Math.round(kwh * 10) / 10,
    baseCharge: Math.round(baseCharge * 100) / 100,
    consumptionCharge: Math.round(consumptionCharge * 100) / 100,
    taxAmount: Math.round(taxAmount * 100) / 100,
    subtotal: Math.round(subtotal * 100) / 100,
    totalAmount: Math.round(totalAmount * 100) / 100
  };
}

export function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2
  }).format(amount || 0);
}

export function formatKwh(kwh) {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 1
  }).format(kwh || 0) + ' kWh';
}
