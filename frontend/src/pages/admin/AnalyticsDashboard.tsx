import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Banknote, Zap, FileText, CreditCard, MapPin } from 'lucide-react';
import { LineChart, BarChart, AreaChart, DoughnutChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { analyticsService } from '@/services/api';
import { formatCurrency, formatCurrencyCompact, formatKwh, formatKwhCompact, formatMonthLabel, formatNumber } from '@/utils/helpers';
import { t } from '@/i18n/t';
import { ConsumerChange } from '@/components/ui/ConsumerChange';

interface AnalyticsData {
  revenue: number; consumption: number; bills: number; payments: number;
  topConsumers: { name: string; consumption: number; change: number | null }[];
  regionalStats: { region: string; customers: number; revenue: number; consumption: number }[];
  // Measured month-on-month movement. Null for a figure with no previous
  // month to compare against, which is why these are optional rather than
  // defaulted to zero.
  revenueTrend: { month: string; revenue: number }[];
  paymentTrend: { month: string; count: number }[];
  changes: { revenue: number | null; consumption: number | null; bills: number | null; payments: number | null };
}

/**
 * Renders a measured change, or nothing when there is none to show.
 *
 * The four badges here used to be the string literals '+12.4%', '-2.1%',
 * '+3.8%' and '+5.2%', copied from the mock data, and every one of them was
 * rendered with tone="success" so the negative figure showed green.
 */
function ChangeBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-slate-400">{t('No prior month')}</span>;
  }
  return (
    <Badge tone={value >= 0 ? 'success' : 'error'}>
      <span className="ltr-num">{value > 0 ? '+' : ''}{value}%</span>
    </Badge>
  );
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsData | null>(null);

  useEffect(() => { analyticsService.getBusinessKpis().then(setData); }, []);

  if (!data) return <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">{Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}</div>;

  const changes = data.changes ?? { revenue: null, consumption: null, bills: null, payments: null };
  const kpis = [
    { label: t('Revenue'), value: formatCurrencyCompact(data.revenue), icon: Banknote, tone: 'bg-emerald-500/15 text-emerald-600', change: changes.revenue },
    { label: t('Consumption'), value: formatKwhCompact(data.consumption), icon: Zap, tone: 'bg-primary-500/15 text-primary-600', change: changes.consumption },
    { label: t('Bills Issued'), value: formatNumber(data.bills), icon: FileText, tone: 'bg-accent-500/15 text-accent-600', change: changes.bills },
    { label: t('Payments'), value: formatNumber(data.payments), icon: CreditCard, tone: 'bg-warning-500/15 text-warning-600', change: changes.payments },
  ];

  const revenueTrend = data.revenueTrend ?? [];
  const paymentTrend = data.paymentTrend ?? [];

  return (
    <div className="space-y-6">
      <PageHeader title={t('Analytics')} description={t('Business KPIs, regional stats, and top consumers.')} breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Analytics') }]} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((k, i) => {
          const Icon = k.icon;
          return (
            <motion.div key={k.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${k.tone}`}><Icon className="w-5 h-5" /></div>
                  <ChangeBadge value={k.change} />
                </div>
                <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{k.value}</p>
                <p className="text-xs text-slate-500 mt-1">{k.label}</p>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Both series come from the API. They were hardcoded twelve-point
            arrays copied from the mock data, on a page whose other charts were
            live, so the two halves of the screen disagreed. */}
        <LineChart title={t('Revenue (12 months)')} labels={revenueTrend.map((r) => formatMonthLabel(r.month))} datasets={[{ label: t('Revenue (LBP)'), data: revenueTrend.map((r) => r.revenue), color: '#2563eb', fill: true }]} height={300} />
        <BarChart title={t('Consumption by Region')} labels={data.regionalStats.map((r) => r.region)} datasets={[{ label: t('kWh'), data: data.regionalStats.map((r) => r.consumption), color: '#10b981' }]} height={300} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <DoughnutChart title={t('Regional Revenue Share')} labels={data.regionalStats.map((r) => r.region)} data={data.regionalStats.map((r) => r.revenue)} colors={['#2563eb', '#10b981', '#06b6d4', '#f59e0b']} height={280} />
        <AreaChart title={t('Payment Trends')} labels={paymentTrend.map((p) => formatMonthLabel(p.month))} datasets={[{ label: t('Payments received'), data: paymentTrend.map((p) => p.count), color: '#06b6d4' }]} height={280} />
        <Card className="p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Top Consumers')}</h3>
          <div className="space-y-3">
            {data.topConsumers.map((c, i) => (
              <div key={c.name} className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-500">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{c.name}</p>
                  <p className="text-xs text-slate-500">{formatKwh(c.consumption)}</p>
                </div>
                <ConsumerChange value={c.change} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><MapPin className="w-4 h-4 text-slate-400" /><h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Regional Statistics')}</h3></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {data.regionalStats.map((r) => (
            <div key={r.region} className="rounded-xl border border-slate-100 dark:border-slate-800 p-4">
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{r.region}</p>
              <div className="mt-3 space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-slate-500">{t('Customers')}</span><span className="font-medium">{formatNumber(r.customers)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">{t('Revenue')}</span><span className="font-medium">{formatCurrency(r.revenue)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">{t('Consumption')}</span><span className="font-medium">{formatKwhCompact(r.consumption)}</span></div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
