import { useEffect, useMemo, useState } from 'react';
import { Banknote, CreditCard, FileText, Landmark } from 'lucide-react';
import { AreaChart, BarChart, DoughnutChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { revenueService } from '@/services/api';
import { formatCurrency, formatCurrencyCompact, formatKwhCompact, formatMonthLabel, formatNumber } from '@/utils/helpers';
import { t } from '@/i18n/t';

interface RevenueData {
  revenueTrend: { month: string; revenue: number }[];
  regionalStats: { region: string; customers: number; revenue: number; consumption: number }[];
  billingStatuses: { status: string; count: number }[];
  billedThisMonth: number;
  collectedThisMonth: number;
  outstandingTotal: number;
  totalRevenue: number;
  /** Which month the two "This Month" cards actually cover, and whether it is now. */
  periodLabel?: string;
  periodIsCurrent?: boolean;
}

export default function RevenuePage() {
  const [data, setData] = useState<RevenueData | null>(null);

  useEffect(() => {
    revenueService.getOverview().then(setData);
  }, []);

  /**
   * Every figure here comes from the API.
   *
   * This block used to invent them: `collected = monthlyRevenue * 0.964` made
   * up a 96.4% collection rate, outstanding was the remainder of that made-up
   * number, and each card then multiplied by 1000, so the page reported
   * roughly a thousand times the revenue the database held.
   */
  const metrics = useMemo(() => {
    if (!data) return null;
    return {
      billed: data.billedThisMonth ?? 0,
      collected: data.collectedThisMonth ?? 0,
      outstanding: data.outstandingTotal ?? 0,
      totalRevenue: data.totalRevenue ?? 0,
    };
  }, [data]);

  if (!data || !metrics) {
    return <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">{Array.from({ length: 4 }).map((_, index) => <SkeletonCard key={index} />)}</div>;
  }

  /*
    The two "This Month" cards cover the last COMPLETE month, which against this
    provider's data is June 2026 while the calendar says August. Unlabelled,
    they read as "right now": a payment recorded today does not move them, and
    the provider watching for it concludes the page is broken. So the month is
    named under the figure. Outstanding and Total Revenue carry no month because
    they cover everything, and they DO move the moment a payment is recorded.
  */
  const period = data.periodLabel;
  const monthNote = period && data.periodIsCurrent === false ? period : undefined;

  const cards = [
    { label: t('Billed This Month'), value: formatCurrencyCompact(metrics.billed), icon: FileText, tone: 'bg-accent-500/15 text-accent-600', note: monthNote },
    { label: t('Collected This Month'), value: formatCurrencyCompact(metrics.collected), icon: CreditCard, tone: 'bg-primary-500/15 text-primary-600', note: monthNote },
    { label: t('Outstanding Balance'), value: formatCurrencyCompact(metrics.outstanding), icon: Banknote, tone: 'bg-warning-500/15 text-warning-600', note: t('all months') },
    { label: t('Total Revenue'), value: formatCurrencyCompact(metrics.totalRevenue), icon: Landmark, tone: 'bg-emerald-500/15 text-emerald-600', note: t('all months') },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title={t('Revenue')} description={t('Track billing performance, collections, and revenue by region.')} breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Revenue') }]} />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.label} hover className="p-5">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 ${card.tone}`}><Icon className="w-5 h-5" /></div>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{card.value}</p>
              <p className="text-xs text-slate-500 mt-1">{card.label}</p>
              {card.note && <p className="text-xs text-slate-400 mt-0.5">{card.note}</p>}
            </Card>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <AreaChart title={t('Revenue Trend')} labels={data.revenueTrend.map((entry) => formatMonthLabel(entry.month))} datasets={[{ label: t('Revenue (LBP)'), data: data.revenueTrend.map((entry) => entry.revenue), color: '#2563eb' }]} height={310} />
        <BarChart title={t('Revenue by Region')} labels={data.regionalStats.map((region) => region.region)} datasets={[{ label: t('Revenue (LBP)'), data: data.regionalStats.map((region) => region.revenue), color: '#10b981' }]} height={310} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <DoughnutChart title={t('Billing Collection Status')} labels={data.billingStatuses.map((item) => t(item.status))} data={data.billingStatuses.map((item) => item.count)} colors={['#10b981', '#f59e0b', '#ef4444']} height={280} />
        <Card className="lg:col-span-2 p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Regional Revenue Performance')}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-start text-xs uppercase tracking-wide text-slate-400 border-b border-slate-100 dark:border-slate-800">
                <tr><th className="pb-3 font-medium">{t('Region')}</th><th className="pb-3 font-medium">{t('Customers')}</th><th className="pb-3 font-medium">{t('Consumption')}</th><th className="pb-3 font-medium text-end">{t('Revenue')}</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.regionalStats.map((region) => (
                  <tr key={region.region} className="text-slate-700 dark:text-slate-300">
                    <td className="py-3 font-medium text-slate-900 dark:text-slate-100">{region.region}</td>
                    <td className="py-3">{formatNumber(region.customers)}</td>
                    <td className="py-3">{formatKwhCompact(region.consumption)}</td>
                    <td className="py-3 text-end font-semibold">{formatCurrency(region.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
