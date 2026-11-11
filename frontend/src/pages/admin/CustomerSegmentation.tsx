import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Users, TrendingUp, Clock, Heart } from 'lucide-react';
import { BarChart, DoughnutChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { segmentationService } from '@/services/api';
import { formatNumber } from '@/utils/helpers';
import { t } from '@/i18n/t';

// Keyed by the names the backend gives the segments (ai/segmentation.py). The
// name is also the catalogue key it is shown through, so it is never changed
// on the way in, only translated on the way out.
const segmentIcons = { 'High Consumers': TrendingUp, 'Average Consumers': Users, 'Low Consumers': Users, 'Late Payment': Clock, 'Loyal Customers': Heart } as const;

export default function CustomerSegmentation() {
  const [segments, setSegments] = useState<{ name: string; count: number; percentage: number; color: string; description: string }[]>([]);
  // A run that produces no segments is a result, not a pending request. The
  // page used to show loading skeletons for ever in that case.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    segmentationService.getSegments()
      .then(setSegments)
      .catch(() => setSegments([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}</div>;

  return (
    <div className="space-y-6">
      <PageHeader title={t('Customer Segmentation')} description={t('AI-driven segments based on consumption and behavior patterns.')} breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Segmentation') }]} />

      {segments.length === 0 && (
        <Card className="p-10 text-center">
          <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('No segments yet')}</p>
          <p className="text-sm text-slate-500 mt-1">{t('Segmentation needs consumption history for several customers before it can group them.')}</p>
        </Card>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {segments.map((s, i) => {
          const Icon = segmentIcons[s.name as keyof typeof segmentIcons] ?? Users;
          return (
            <motion.div key={s.name} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className="p-5">
                <div className="flex items-start justify-between mb-4">
                  <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${s.color}22` }}>
                    <Icon className="w-5 h-5" style={{ color: s.color }} />
                  </div>
                  <Badge tone="neutral">{s.percentage}%</Badge>
                </div>
                <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{formatNumber(s.count)}</p>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mt-1">{t(s.name)}</p>
                <p className="text-xs text-slate-500 mt-1">{s.description}</p>
                <div className="mt-4 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <motion.div initial={{ width: 0 }} animate={{ width: `${s.percentage}%` }} transition={{ delay: 0.2 + i * 0.05, duration: 0.6 }} className="h-full rounded-full" style={{ backgroundColor: s.color }} />
                </div>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <DoughnutChart title={t('Segment Distribution')} labels={segments.map((s) => t(s.name))} data={segments.map((s) => s.count)} colors={segments.map((s) => s.color)} height={300} />
        <BarChart title={t('Customers by Segment')} labels={segments.map((s) => t(s.name))} datasets={[{ label: t('Customers'), data: segments.map((s) => s.count), color: '#2563eb' }]} height={300} />
      </div>

      <Card className="p-5">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Segment Insights')}</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
          {segments.map((s) => (
            <div key={s.name} className="rounded-xl border border-slate-100 dark:border-slate-800 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="w-3 h-3 rounded-full" style={{ backgroundColor: s.color }} />
                <p className="font-semibold text-slate-900 dark:text-slate-100">{t(s.name)}</p>
              </div>
              <p className="text-xs text-slate-500">
                {t('Customers: {n} · {pct}% of the total').replace('{n}', formatNumber(s.count)).replace('{pct}', String(s.percentage))}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
