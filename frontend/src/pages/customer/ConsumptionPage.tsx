import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Download, Filter } from 'lucide-react';
import { LineChart, BarChart, AreaChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { useToast } from '@/context/ToastContext';
import { consumptionService, type MonthlyConsumption } from '@/services/api';
import { formatCurrency, formatKwh, formatMonthLabel } from '@/utils/helpers';
import { t } from '@/i18n/t';

// Ranges the two filters offer. Both are honoured by the backend: /consumption
// /monthly takes `months` and /consumption/daily takes `days`.
//
// Each has its own label rather than "{n} months" with the number put in:
// in Arabic the noun after a number changes form with the number (6 أشهر,
// 12 شهراً), which one sentence with a slot in it cannot get right.
const MONTH_RANGES: { months: number; label: string }[] = [
  { months: 6, label: '6 months' },
  { months: 12, label: '12 months' },
  { months: 24, label: '24 months' },
];
const DAY_RANGES: { days: number; label: string }[] = [
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
];

export default function ConsumptionPage() {
  const toast = useToast();
  const [monthly, setMonthly] = useState<MonthlyConsumption[]>([]);
  const [daily, setDaily] = useState<{ day: number; kwh: number }[]>([]);
  const [hourly, setHourly] = useState<{ hour: string; kwh: number }[]>([]);
  const [months, setMonths] = useState<number>(12);
  const [days, setDays] = useState<number>(30);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    consumptionService.getHourly().then(setHourly);
  }, []);

  // Refetch when the range changes, which is the point of the filters. They
  // used to set state that nothing read, so the charts never moved.
  useEffect(() => {
    consumptionService.getMonthly(months).then(setMonthly);
  }, [months]);

  useEffect(() => {
    consumptionService.getDaily(days).then(setDaily);
  }, [days]);

  /**
   * Downloads the statement the backend generates.
   *
   * This button used to raise a toast reading "Your PDF report is being
   * generated" and then do nothing whatsoever: there was no request and no
   * file. It now calls GET /consumption/export and saves what comes back.
   */
  const handleExport = async () => {
    setExporting(true);
    try {
      const filename = await consumptionService.exportStatement(months, 'pdf');
      toast({ type: 'success', title: t('Statement downloaded'), message: filename });
    } catch {
      toast({ type: 'error', title: t('Could not generate the statement'), message: t('Please try again.') });
    } finally {
      setExporting(false);
    }
  };

  const totalKwh = monthly.reduce((s, m) => s + m.kwh, 0);
  const totalCost = monthly.reduce((s, m) => s + m.cost, 0);

  /**
   * An average, over the period the meter can actually support.
   *
   * `daily` used to be summed and divided by its own LENGTH, then labelled
   * "avg daily usage". With a meter read once a month that divides two months
   * of electricity by two and calls the answer a day: one household using
   * about 3.4 kWh a day was shown 85.4. The rows were right; the denominator
   * was the number of rows and the label promised days.
   *
   * The backend now returns nothing at all for a meter that is not read daily,
   * so the presence of `daily` is itself the test. Where it is absent the
   * monthly series gives a true average per month, which is the finest
   * average this data supports.
   */
  const avgDaily = daily.length
    ? Math.round((daily.reduce((s, d) => s + d.kwh, 0) / days) * 10) / 10
    : null;
  const avgMonthly = monthly.length
    ? Math.round((totalKwh / monthly.length) * 10) / 10
    : null;

  // The customer's own busiest month. This was the fixed string 'Jul (740 kWh)',
  // printed on every account regardless of what the account actually used.
  const peak = monthly.reduce<MonthlyConsumption | null>(
    (best, m) => (best === null || m.kwh > best.kwh ? m : best),
    null,
  );

  // A month as the reader's language writes it, with its year when the
  // backend sent one (`period`), so two Januaries are never confused.
  const monthLabel = (m: MonthlyConsumption, shortYear = false) => formatMonthLabel(m.period ?? m.month, shortYear);

  // The window ends with the customer's newest reading, not with today (the
  // backend anchors it there: routers/consumption.py), and it can hold fewer
  // months than asked for when the history is shorter. So the label names the
  // first and last month it covers, instead of "last 12 months" over what
  // were, in October, nine.
  const oldest = monthly.length ? monthly[0] : null;
  const newest = monthly.length ? monthly[monthly.length - 1] : null;
  const totalLabel = !newest || !oldest
    ? t('Total consumption')
    : monthly.length === 1
      ? t('Total, {month}').replace('{month}', monthLabel(newest))
      : t('Total, {start} to {end}').replace('{start}', monthLabel(oldest)).replace('{end}', monthLabel(newest));

  // `figure` values are numbers and units, kept left to right in every
  // language; the others are words and follow the page.
  const stats: { label: string; value: string; figure: boolean; tone: string }[] = [
    newest
      ? { label: totalLabel, value: formatKwh(Math.round(totalKwh)), figure: true, tone: 'text-primary-600' }
      : { label: totalLabel, value: t('No readings yet'), figure: false, tone: 'text-primary-600' },
    { label: t('Total cost'), value: formatCurrency(totalCost), figure: true, tone: 'text-emerald-600' },
    avgDaily !== null
      // The range is the one chosen in the filter beside the daily chart.
      ? { label: t('Average per day'), value: formatKwh(avgDaily), figure: true, tone: 'text-accent-600' }
      : avgMonthly !== null
        ? { label: t('Average per month'), value: formatKwh(avgMonthly), figure: true, tone: 'text-accent-600' }
        : { label: t('Average per month'), value: t('No readings yet'), figure: false, tone: 'text-accent-600' },
    peak
      ? {
          label: t('Peak month: {month}').replace('{month}', monthLabel(peak)),
          value: formatKwh(Math.round(peak.kwh)), figure: true, tone: 'text-warning-600',
        }
      : { label: t('Peak month'), value: t('No readings yet'), figure: false, tone: 'text-warning-600' },
  ];

  return (
    <div>
      <PageHeader
        title={t('Consumption')}
        description={t('Track your electricity usage across months, days, and hours.')}
        breadcrumb={[{ label: t('Dashboard'), href: '/app/dashboard' }, { label: t('Consumption') }]}
        action={(
          <Button
            variant="outline"
            loading={exporting}
            leftIcon={<Download className="w-4 h-4" />}
            onClick={handleExport}
          >
            {t('Export PDF')}
          </Button>
        )}
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <Card className="p-5">
              <p className={`text-2xl font-bold ${s.figure ? 'ltr-num' : ''} ${s.tone}`}>{s.value}</p>
              <p className="text-xs text-slate-500 mt-1">{s.label}</p>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Filters */}
      <Card className="p-4 mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500"><Filter className="w-4 h-4" />{t('Filters:')}</div>
          <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl">
            {MONTH_RANGES.map((range) => (
              <button
                key={range.months}
                onClick={() => setMonths(range.months)}
                aria-pressed={months === range.months}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition ${months === range.months ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm' : 'text-slate-500'}`}
              >
                {t(range.label)}
              </button>
            ))}
          </div>
          {/*
            Hidden when there is no daily chart for it to change. A control that
            visibly does nothing teaches the user that the page is broken.
          */}
          {daily.length > 0 && (
            <select
              id="daily-range"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              aria-label={t('Daily chart range')}
              className="input-base h-9 w-auto text-sm"
            >
              {DAY_RANGES.map((range) => <option key={range.days} value={range.days}>{t(range.label)}</option>)}
            </select>
          )}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <LineChart
          title={t('Monthly Usage')}
          labels={monthly.map((m) => monthLabel(m, true))}
          datasets={[{ label: t('kWh'), data: monthly.map((m) => m.kwh), color: '#2563eb', fill: true }]}
          height={300}
        />
        <BarChart
          title={t('Monthly Cost')}
          labels={monthly.map((m) => monthLabel(m, true))}
          datasets={[{ label: t('Cost (LBP)'), data: monthly.map((m) => m.cost), color: '#10b981' }]}
          height={300}
        />
      </div>

      {/*
        Both of these draw nothing when the meter cannot produce the series,
        and say why. They used to render an empty grid with an axis running 0
        to 1, which reads as a measurement of zero rather than as an absence of
        measurement, the same distinction the rest of this system is careful
        about everywhere else.
      */}
      <div className="grid lg:grid-cols-2 gap-4">
        {daily.length > 0 ? (
          <AreaChart
            title={t('Daily Usage')}
            labels={daily.map((d) => String(d.day))}
            datasets={[{ label: t('kWh'), data: daily.map((d) => d.kwh), color: '#06b6d4' }]}
            height={260}
          />
        ) : (
          <Card className="p-6">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">{t('Daily Usage')}</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {t('Your meter is read once a month, so there is no day-by-day record to draw. The monthly chart above covers the same electricity.')}
            </p>
          </Card>
        )}
        {hourly.length > 0 ? (
          <LineChart
            // An average over the newest 14 days of readings (routers/consumption.py),
            // not today's hours, which is what this title used to claim.
            title={t('Hourly Usage (average of the last 14 days)')}
            labels={hourly.map((h) => h.hour)}
            datasets={[{ label: t('kWh'), data: hourly.map((h) => h.kwh), color: '#8b5cf6', fill: true }]}
            height={260}
          />
        ) : (
          <Card className="p-6">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">{t('Hourly Usage')}</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {t('An hour-by-hour profile needs a meter that reports through the day. Yours records one total per month, so there are no hours to compare.')}
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
