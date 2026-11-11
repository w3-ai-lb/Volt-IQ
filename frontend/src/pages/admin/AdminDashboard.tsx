import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Users, Banknote, Zap, Target, ArrowUpRight, ArrowDownRight, Activity, UserPlus, CreditCard, AlertTriangle, Cpu, FileText, ShieldAlert } from 'lucide-react';
import { LineChart, AreaChart, DoughnutChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { ConsumerChange } from '@/components/ui/ConsumerChange';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { consumptionService, dashboardService, riskService, type AdminDashboard as AdminData, type Heatmap, type RiskSummary } from '@/services/api';
import {
  formatCurrency, formatCurrencyCompact, formatDate, formatKwh, formatKwhCompact, formatMonthLabel, formatNumber,
  formatWeekLabel, formatWeekday,
} from '@/utils/helpers';
import { t } from '@/i18n/t';

const activityIcon: Record<string, typeof UserPlus> = { user: UserPlus, payment: CreditCard, alert: AlertTriangle, system: Cpu };

const bandTone: Record<string, string> = {
  High: 'bg-error-500/15 text-error-600',
  Medium: 'bg-warning-500/15 text-warning-600',
  Low: 'bg-emerald-500/15 text-emerald-600',
  Unknown: 'bg-slate-500/15 text-slate-500',
};

export default function AdminDashboard() {
  const [data, setData] = useState<AdminData | null>(null);
  const [risk, setRisk] = useState<RiskSummary | null>(null);
  const [heatmap, setHeatmap] = useState<Heatmap | null>(null);

  useEffect(() => { dashboardService.getAdminDashboard().then(setData); }, []);
  // Loaded separately: scoring every account is a heavier query than the rest
  // of the dashboard, and the page should not wait on it to render.
  useEffect(() => { riskService.getSummary().then(setRisk).catch(() => setRisk(null)); }, []);
  useEffect(() => { consumptionService.getHeatmap().then(setHeatmap).catch(() => setHeatmap(null)); }, []);

  if (!data) return <div className="grid sm:grid-cols-2 xl:grid-cols-5 gap-4">{Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}</div>;

  /**
   * `change` is measured; the arrow now follows it.
   *
   * The arrow direction and its colour used to be hardcoded per card (`up:
   * true` on three, `up: false` on one), so a month where revenue fell still
   * drew a green up-arrow beside the real negative figure. The share of active
   * customers was also being rendered in the change slot with an up-arrow, so
   * "93% of customers are active" read as "+93% growth".
   */
  const activeShare = data.stats.totalCustomers > 0
    ? Math.round((data.stats.activeCustomers / data.stats.totalCustomers) * 100)
    : 0;

  const cards: {
    label: string; value: string; icon: typeof Users; tone: string;
    change?: number; note?: string;
  }[] = [
    {
      label: t('Total Customers'),
      value: formatNumber(data.stats.totalCustomers),
      icon: Users,
      tone: 'bg-primary-500/15 text-primary-600',
      // Null when the loaded data carries no joining dates, so growth cannot be
      // measured. The note says that rather than printing a measured-looking 0%.
      change: data.stats.customersChange ?? undefined,
      note: data.stats.customersChange === null || data.stats.customersChange === undefined
        ? t('no joining dates in the data')
        : undefined,
    },
    { label: t('Active Customers'), value: formatNumber(data.stats.activeCustomers), icon: Activity, tone: 'bg-emerald-500/15 text-emerald-600', note: t('{n}% of all accounts').replace('{n}', String(activeShare)) },
    { label: t('Total Revenue'), value: formatCurrencyCompact(data.stats.revenue), icon: Banknote, tone: 'bg-emerald-500/15 text-emerald-600', change: data.stats.revenueChange },
    // The newest COMPLETE month (routers/dashboard.py), which is named: under an
    // "as of 12 June" heading an unnamed figure reads as June's, and it is May's.
    {
      label: data.stats.consumptionPeriod
        ? t('Consumption in {month}').replace('{month}', formatMonthLabel(data.stats.consumptionPeriod))
        : t('Total Consumption'),
      value: formatKwhCompact(data.stats.monthlyConsumption),
      icon: Zap,
      tone: 'bg-accent-500/15 text-accent-600',
      change: data.stats.consumptionChange,
    },
    // Null means the backtest could not run, not that the model scored zero.
    // A dataset shorter than 32 weeks is the ordinary case on a first real
    // load, and "0%" would be the first thing the platform said about itself.
    //
    // Labelled as a backtest, not "Prediction Accuracy". The figure is 100 minus
    // the backtest's error, and on a meter read once a month the weekly series
    // has readings in only some weeks, so the backtest measures the reading
    // schedule more than the model. It is a diagnostic, and the note says so.
    {
      label: t('Forecast backtest'),
      value: data.stats.predictionAccuracy === null || data.stats.predictionAccuracy === undefined
        ? t('Not enough data')
        : `${data.stats.predictionAccuracy}%`,
      icon: Target,
      tone: 'bg-warning-500/15 text-warning-600',
      note: data.stats.predictionAccuracy === null || data.stats.predictionAccuracy === undefined
        ? t('needs 32 weeks')
        : t('diagnostic, not validated accuracy'),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t('Executive Dashboard')}</h1>
        {/* It said "Real-time", over figures that end with the newest meter
            reading, months before today. The date is now printed instead. */}
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {data.stats.asOf
            ? t('Overview of your utility operations as of {date}, the newest meter reading in the data.').replace('{date}', formatDate(data.stats.asOf))
            : t('Overview of your utility operations.')}
        </p>
      </div>

      <div className="grid sm:grid-cols-2 xl:grid-cols-5 gap-4">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <motion.div key={c.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${c.tone}`}><Icon className="w-5 h-5" /></div>
                  {c.change !== undefined && (
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${c.change >= 0 ? 'text-emerald-600' : 'text-error-600'}`}>
                      {c.change >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                      <span className="ltr-num">{c.change > 0 ? '+' : ''}{c.change}%</span>
                    </span>
                  )}
                  {c.note && <span className="text-xs font-medium text-slate-400">{c.note}</span>}
                </div>
                <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{c.value}</p>
                <p className="text-xs text-slate-500 mt-1">{c.label}</p>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <AreaChart title={t('Revenue Trend')} labels={data.revenueTrend.map((d) => formatMonthLabel(d.month))} datasets={[{ label: t('Revenue (LBP)'), data: data.revenueTrend.map((d) => d.revenue), color: '#2563eb' }]} height={300} />
        </div>
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Active vs Inactive')}</h3>
          <DoughnutChart labels={[t('Active'), t('Inactive')]} data={[data.stats.activeCustomers, data.stats.totalCustomers - data.stats.activeCustomers]} colors={['#10b981', '#e2e8f0']} height={260} />
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* The values are kWh; the series was labelled MWh. */}
        <AreaChart title={t('Consumption Trend')} labels={data.consumptionTrend.map((d) => formatMonthLabel(d.period ?? d.month, true))} datasets={[{ label: t('Consumption (kWh)'), data: data.consumptionTrend.map((d) => d.kwh), color: '#06b6d4' }]} height={280} />
        {/*
          WHAT REPLACED "CUSTOMER GROWTH"
          A growth chart needs join dates, and the provider's export has none:
          not in subscribers.csv, not in subscriptions.csv, not in meters.csv.
          Drawing one bar of 300 in January would have read as three hundred
          people signing up at once, so the card said what was missing instead
          — correct, and it left an executive screen with a paragraph where a
          chart belongs.

          This is the question the same records CAN answer. The filled line is
          the size of the customer base each month, counted from the invoices
          actually issued. The second line is how many of those bills were
          settled in full. On this data the first is flat at 300 and the second
          drifts from 256 to 225 and back to 248: the base did not move and the
          paying part of it did, which is the finding, not the absence of one.
        */}
        {data.customerBase.length >= 2 ? (
          <LineChart
            title={t('The Customer Base, Month by Month')}
            labels={data.customerBase.map((d) => formatMonthLabel(d.month, true))}
            datasets={[
              { label: t('Subscribers billed'), data: data.customerBase.map((d) => d.billed), color: '#0891b2', fill: true },
              { label: t('Bills settled in full'), data: data.customerBase.map((d) => d.settled), color: '#f59e0b' },
            ]}
            height={280}
          />
        ) : (
          <Card className="p-5">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('The Customer Base, Month by Month')}</h3>
            <EmptyState
              icon={<UserPlus className="w-8 h-8" />}
              title={t('Not enough billed months yet')}
              description={t('This chart needs at least two months of issued invoices before it can show anything.')}
            />
          </Card>
        )}
      </div>

      <LineChart title={t('Demand Forecast')} labels={data.forecastData.map((d) => formatWeekLabel(d.label))} datasets={[{ label: t('Actual'), data: data.forecastData.map((d) => d.actual), color: '#2563eb' }, { label: t('Predicted'), data: data.forecastData.map((d) => d.predicted), color: '#10b981', dashed: true }]} height={280} />

      <Card className="p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-1">{t('Consumption Heatmap')}</h3>
          <p className="text-xs text-slate-500 mb-4">
            {heatmap
              ? t('Measured at the generators, over the last {n} days of recorded telemetry').replace('{n}', String(heatmap.windowDays))
              : t('Average load by weekday and hour')}
          </p>

          {/* Real aggregation from /consumption/heatmap. This used to be a
              hardcoded sine wave, which drew the same picture whatever the
              data said. */}
          {!heatmap ? (
            <div className="h-32 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />
          ) : (
            <div className="space-y-0.5">
              {heatmap.grid.map((row, day) => (
                <div key={heatmap.days[day]} className="flex items-center gap-1.5">
                  <span className="w-9 shrink-0 text-[10px] text-slate-400">{formatWeekday(heatmap.days[day])}</span>
                  <div className="grid flex-1 gap-0.5" style={{ gridTemplateColumns: 'repeat(24, 1fr)' }}>
                    {row.map((kwh, h) => {
                      const intensity = heatmap.maxKwh > 0 ? kwh / heatmap.maxKwh : 0;
                      return (
                        <div
                          key={h}
                          className="h-5 rounded-sm"
                          style={{ backgroundColor: `rgba(37, 99, 235, ${0.07 + intensity * 0.83})` }}
                          title={`${formatWeekday(heatmap.days[day])} ${heatmap.hours[h]}, ${formatKwh(kwh)}`}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between mt-3 text-xs text-slate-400">
            <span>0</span>
            <div className="flex-1 h-2 mx-2 rounded-full bg-gradient-to-r from-primary-100 to-primary-600" />
            <span>{heatmap ? formatKwh(heatmap.maxKwh) : t('High')}</span>
          </div>
      </Card>

      <div className="grid lg:grid-cols-3 gap-4">

        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Recent Activities')}</h3>
            <Activity className="w-4 h-4 text-slate-400" />
          </div>
          <div className="space-y-3">
            {data.recentActivities.map((a) => {
              const Icon = activityIcon[a.type] ?? FileText;
              return (
                <div key={a.id} className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0"><Icon className="w-4 h-4 text-slate-500" /></div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-700 dark:text-slate-300">{a.text}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{a.time}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Payment Risk')}</h3>
            <ShieldAlert className="w-4 h-4 text-slate-400" />
          </div>

          {risk === null ? (
            <div className="space-y-2 mt-4">
              {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-9 animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800" />)}
            </div>
          ) : (
            <>
              <p className="text-xs text-slate-500 mb-4">
                {(risk.high + risk.medium === 1
                  ? t('{amount} outstanding on 1 account needing attention')
                  : t('{amount} outstanding on {n} accounts needing attention').replace('{n}', String(risk.high + risk.medium))
                ).replace('{amount}', formatCurrency(risk.amountAtRisk))}
                {/* Scored against the newest data, not today (ai/risk.py). */}
                {risk.asOf && <> · {t('scored as of {date}').replace('{date}', formatDate(risk.asOf))}</>}
              </p>

              <div className="flex gap-2 mb-4">
                {([['High', risk.high], ['Medium', risk.medium], ['Low', risk.low]] as const).map(([band, count]) => (
                  <div key={band} className={`flex-1 rounded-lg px-2 py-1.5 text-center ${bandTone[band]}`}>
                    <p className="text-lg font-bold leading-tight">{count}</p>
                    <p className="text-[10px] font-semibold uppercase tracking-wide">{t(band)}</p>
                  </div>
                ))}
              </div>

              <div className="space-y-3">
                {risk.customers.filter((c) => c.band === 'High' || c.band === 'Medium').slice(0, 4).map((c) => (
                  <div key={c.customerId} className="flex items-start gap-3">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 mt-0.5 ${bandTone[c.band]}`}>{Math.round(c.score)}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{c.name}</p>
                      {/* The top reason, so staff see why rather than just a number. */}
                      <p className="text-xs text-slate-500 truncate">{c.reasons[0]}</p>
                    </div>
                    <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 shrink-0">{formatCurrency(c.outstanding)}</span>
                  </div>
                ))}
                {risk.high + risk.medium === 0 && (
                  <p className="text-sm text-slate-500">{t('Every account is paying on schedule.')}</p>
                )}
              </div>
            </>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Top Consumers')}</h3>
            <Zap className="w-4 h-4 text-slate-400" />
          </div>
          <div className="space-y-3">
            {data.topConsumers.map((consumer, index) => (
              <div key={consumer.name} className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-500">{index + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{consumer.name}</p>
                  <p className="text-xs text-slate-500">{formatKwh(consumer.consumption)}</p>
                </div>
                <ConsumerChange value={consumer.change} />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
