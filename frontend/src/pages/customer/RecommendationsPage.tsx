import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { WashingMachine, Thermometer, Lightbulb, Unplug, Wind, BellRing, Check, Sparkles, TrendingDown } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { useToast } from '@/context/ToastContext';
import { recommendationsService } from '@/services/api';
import { formatCurrency } from '@/utils/helpers';
import { t } from '@/i18n/t';

// Every icon name the recommendation engine writes (backend/app/ai/recommender.py).
const ICONS: Record<string, typeof WashingMachine> = {
  WashingMachine, Thermostat: Thermometer, Lightbulb, Unplug, Wind, BellRing,
};

const priorityTone: Record<string, 'error' | 'warning' | 'success'> = {
  High: 'error', Medium: 'warning', Low: 'success',
};

interface Recommendation {
  id: string; title: string; description: string; estimatedSavings: number; priority: string; icon: string; completed: boolean;
}

export default function RecommendationsPage() {
  const toast = useToast();
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    recommendationsService.getAll().then((r) => { setItems(r); setLoading(false); });
  }, []);

  /**
   * Marks a recommendation done, on the server.
   *
   * This used to change local state and toast, without ever calling
   * `recommendationsService.markCompleted`, which already existed. The tick
   * therefore survived until the next page load and no further, and the engine
   * kept suggesting something the customer had already acted on. The row is
   * updated optimistically and rolled back if the request fails, so the page
   * never claims a save that did not happen.
   */
  const markCompleted = async (id: string) => {
    setItems((prev) => prev.map((r) => (r.id === id ? { ...r, completed: true } : r)));
    try {
      await recommendationsService.markCompleted(id);
      toast({ type: 'success', title: t('Marked as completed'), message: t('Great work on saving energy!') });
    } catch {
      setItems((prev) => prev.map((r) => (r.id === id ? { ...r, completed: false } : r)));
      toast({ type: 'error', title: t('Could not save'), message: t('Please try again.') });
    }
  };

  const totalSavings = items.filter((r) => !r.completed).reduce((s, r) => s + r.estimatedSavings, 0);

  return (
    <div>
      <PageHeader title={t('Recommendations')} description={t('AI-powered tips to lower your bill and carbon footprint.')} breadcrumb={[{ label: t('Dashboard'), href: '/app/dashboard' }, { label: t('Recommendations') }]} />

      <Card className="p-5 mb-6 bg-gradient-primary text-white">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <p className="text-sm text-white/80">{t('Potential monthly savings')}</p>
            <p className="text-3xl font-bold ltr-num">{formatCurrency(totalSavings)}</p>
          </div>
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/15 backdrop-blur">
            <Sparkles className="w-5 h-5" />
            <span className="text-sm font-medium">
              {t('Active recommendations: {n}').replace('{n}', String(items.filter((r) => !r.completed).length))}
            </span>
          </div>
        </div>
      </Card>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-48 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />)
        ) : (
          items.map((r, i) => {
            const Icon = ICONS[r.icon] ?? Lightbulb;
            return (
              <motion.div key={r.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <Card hover className={`p-5 h-full flex flex-col ${r.completed ? 'opacity-60' : ''}`}>
                  <div className="flex items-start justify-between mb-3">
                    <div className="w-11 h-11 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow"><Icon className="w-5 h-5 text-white" /></div>
                    <Badge tone={priorityTone[r.priority] ?? 'success'}>{t(r.priority)}</Badge>
                  </div>
                  <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{r.title}</h3>
                  <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400 flex-1">{r.description}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-emerald-600">
                      <TrendingDown className="w-4 h-4" />
                      <span className="text-sm font-semibold">{t('Save {amount} a month').replace('{amount}', formatCurrency(r.estimatedSavings))}</span>
                    </div>
                    {r.completed ? (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600"><Check className="w-4 h-4" />{t('Completed')}</span>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => markCompleted(r.id)}>{t('Mark as Completed')}</Button>
                    )}
                  </div>
                </Card>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
}
