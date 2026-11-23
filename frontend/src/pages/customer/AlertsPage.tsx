import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, Bell, CreditCard, TrendingDown, Zap, Info, CheckCircle2, RefreshCw, Check } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { alertsService } from '@/services/api';
import { useToast } from '@/context/ToastContext';
import { formatDate, severityLabel } from '@/utils/helpers';
import { slideFrom, t } from '@/i18n/t';

const alertConfig: Record<string, { icon: typeof Bell; bg: string; text: string; tone: 'error' | 'warning' | 'info' | 'success' }> = {
  'high-usage': { icon: Zap, bg: 'bg-warning-500/15', text: 'text-warning-600', tone: 'warning' },
  payment: { icon: CreditCard, bg: 'bg-primary-500/15', text: 'text-primary-600', tone: 'info' },
  anomaly: { icon: AlertTriangle, bg: 'bg-error-500/15', text: 'text-error-600', tone: 'error' },
  'low-usage': { icon: TrendingDown, bg: 'bg-emerald-500/15', text: 'text-emerald-600', tone: 'success' },
};

const severityBadge: Record<string, 'error' | 'warning' | 'info' | 'success'> = {
  error: 'error', warning: 'warning', info: 'info', success: 'success',
};

interface Alert { id: string; type: string; title: string; message: string; severity: string; date: string; read: boolean }

export default function AlertsPage() {
  const toast = useToast();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    alertsService.getAll()
      .then((a) => setAlerts(a))
      .catch(() => toast({ type: 'error', title: t('Could not load alerts') }))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Re-runs the engine server-side. Alerts are derived from readings, bills and
   * detected anomalies, so this is how a customer sees the effect of a payment
   * they just made or a reading that just arrived.
   */
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const fresh = await alertsService.refresh();
      setAlerts(fresh);
      toast({
        type: 'success',
        title: t('Alerts updated'),
        message: fresh.length
          ? t('Active alerts: {n}').replace('{n}', String(fresh.length))
          : t('Nothing needs your attention'),
      });
    } catch {
      toast({ type: 'error', title: t('Could not refresh'), message: t('Please try again.') });
    } finally {
      setRefreshing(false);
    }
  };

  const handleRead = async (id: string) => {
    // Optimistic: the unread dot clears immediately and is restored if the
    // request fails, so the list never shows a state the server rejected.
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read: true } : a)));
    try {
      await alertsService.markRead(id);
    } catch {
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read: false } : a)));
      toast({ type: 'error', title: t('Could not mark as read') });
    }
  };

  // Counted by TYPE, which is what the four labels below name.
  //
  // These were counted by SEVERITY: warning, error, info, success. Severity and
  // type are different axes and they only line up by accident. An overdue bill
  // carries severity 'error', so it was counted under "Anomalies": a customer
  // with one unpaid bill and nothing else wrong was shown "1 Anomaly" and
  // "0 Reminders", which is exactly backwards, and "anomaly" on this screen
  // means a reading the system could not explain.
  const counts = {
    high: alerts.filter((a) => a.type === 'high-usage').length,
    anomaly: alerts.filter((a) => a.type === 'anomaly').length,
    info: alerts.filter((a) => a.type === 'payment').length,
    success: alerts.filter((a) => a.type === 'low-usage').length,
  };

  const unread = alerts.filter((a) => !a.read).length;

  const summary = [
    { label: t('High usage'), value: counts.high, icon: Zap, tone: 'text-warning-600 bg-warning-500/15' },
    { label: t('Anomalies'), value: counts.anomaly, icon: AlertTriangle, tone: 'text-error-600 bg-error-500/15' },
    { label: t('Reminders'), value: counts.info, icon: Bell, tone: 'text-primary-600 bg-primary-500/15' },
    { label: t('Milestones'), value: counts.success, icon: CheckCircle2, tone: 'text-emerald-600 bg-emerald-500/15' },
  ];

  return (
    <div>
      <PageHeader
        title={t('Alerts')}
        description={t('Stay informed about your energy usage and account.')}
        breadcrumb={[{ label: t('Dashboard'), href: '/app/dashboard' }, { label: t('Alerts') }]}
        action={
          <Button variant="outline" onClick={handleRefresh} loading={refreshing} leftIcon={<RefreshCw className="w-4 h-4" />}>{t('Check for new alerts')}
          </Button>
        }
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {summary.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="p-5 flex items-center gap-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${s.tone}`}><Icon className="w-5 h-5" /></div>
              <div><p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{s.value}</p><p className="text-xs text-slate-500">{s.label}</p></div>
            </Card>
          );
        })}
      </div>

      {!loading && alerts.length > 0 && (
        <p className="text-sm text-slate-500 mb-3">
          {unread > 0 ? t('{n} unread').replace('{n}', String(unread)) : t('All caught up')}
          {' · '}
          {t('{n} total').replace('{n}', String(alerts.length))}
        </p>
      )}

      <div className="space-y-3">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800" />)
        ) : alerts.length === 0 ? (
          <Card className="p-10 text-center">
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500 mb-3" />
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Nothing needs your attention')}</h3>
            <p className="text-sm text-slate-500 mt-1">{t('No unusual readings, no bill due, and your consumption is in line with your usual pattern.')}
            </p>
          </Card>
        ) : (
          alerts.map((a, i) => {
            const cfg = alertConfig[a.type] ?? { icon: Info, bg: 'bg-slate-500/15', text: 'text-slate-600', tone: 'neutral' as const };
            const Icon = cfg.icon;
            return (
              <motion.div key={a.id} initial={{ opacity: 0, x: slideFrom(-16) }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                <Card hover className={`p-4 flex items-start gap-4 ${a.read ? 'opacity-60' : ''}`}>
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${cfg.bg}`}><Icon className={`w-5 h-5 ${cfg.text}`} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{a.title}</h3>
                      <Badge tone={severityBadge[a.severity] ?? 'neutral'}>{severityLabel(a.severity)}</Badge>
                      {!a.read && <span className="w-2 h-2 rounded-full bg-primary-500" aria-label={t('Unread')} />}
                    </div>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{a.message}</p>
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <span className="text-xs text-slate-400 hidden sm:block">{formatDate(a.date)}</span>
                    {!a.read && (
                      <button
                        type="button"
                        onClick={() => handleRead(a.id)}
                        className="text-xs text-slate-400 hover:text-primary-600 inline-flex items-center gap-1"
                      >
                        <Check className="w-3 h-3" />{t('Mark read')}
                      </button>
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
