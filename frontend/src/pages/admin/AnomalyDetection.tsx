import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertTriangle, ArrowRight, ShieldAlert, Cpu, Activity, ShieldCheck, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { anomalyService } from '@/services/api';
import { useToast } from '@/context/ToastContext';
import { dateLocale, formatDate } from '@/utils/helpers';
import { t } from '@/i18n/t';

const config: Record<string, { icon: typeof AlertTriangle; bg: string; text: string }> = {
  'Unusual Consumption': { icon: Activity, bg: 'bg-warning-500/15', text: 'text-warning-600' },
  'Possible Fraud': { icon: ShieldAlert, bg: 'bg-error-500/15', text: 'text-error-600' },
  'Meter Error': { icon: Cpu, bg: 'bg-accent-500/15', text: 'text-accent-600' },
  'Abnormal Spike': { icon: AlertTriangle, bg: 'bg-error-500/15', text: 'text-error-600' },
  // What the monthly detector produces. Its own icon, because a finding built
  // from eighteen months of readings is a different kind of claim from one
  // built from a single strange day.
  'Unusual Monthly Profile': { icon: Activity, bg: 'bg-primary-500/15', text: 'text-primary-600' },
};

const MONTHLY = 'Unusual Monthly Profile';

const severityLabel = (severity: string) => (severity ? severity.charAt(0).toUpperCase() + severity.slice(1) : severity);

const severityTone: Record<string, 'error' | 'warning' | 'info' | 'success'> = {
  critical: 'error', high: 'error', medium: 'warning', low: 'info',
};

const severityBorder: Record<string, string> = {
  critical: 'border-error-500/40', high: 'border-error-500/30', medium: 'border-warning-500/30', low: 'border-slate-200 dark:border-slate-700',
};

interface Anomaly { id: string; type: string; customer: string; severity: string; value: string; description: string; date: string }

export default function AnomalyDetection() {
  const toast = useToast();
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  // Separate from `anomalies.length`, because a system with nothing wrong is
  // not a system that is still loading. The page used to render skeletons for
  // ever whenever the detector returned zero findings.
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  // What the last run actually did. The button used to hand back a toast that
  // said "Detection complete" whether it had found thirty-seven cases or
  // nothing at all, on a page that was empty either way, so pressing it felt
  // like pressing a button that was not connected to anything.
  const [lastRun, setLastRun] = useState<{ found: number; at: Date } | null>(null);

  const load = () => anomalyService.getAll().then(setAnomalies).catch(() => setAnomalies([])).finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  /** Re-runs detection. The endpoint existed with no button anywhere. */
  const rerun = async () => {
    setRunning(true);
    try {
      const found = await anomalyService.run();
      await load();
      setLastRun({ found: found.length, at: new Date() });
      toast({
        type: 'success',
        title: t('Detection complete'),
        message: found.length === 0
          ? t('The detector ran and found nothing to report.')
          : found.length === 1
            ? t('1 account flagged.')
            : t('{count} accounts flagged.').replace('{count}', String(found.length)),
      });
    } catch {
      toast({ type: 'error', title: t('Could not run detection'), message: t('Please try again.') });
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">{Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}</div>;

  const counts = { critical: anomalies.filter((a) => a.severity === 'critical').length, high: anomalies.filter((a) => a.severity === 'high').length, medium: anomalies.filter((a) => a.severity === 'medium').length, low: anomalies.filter((a) => a.severity === 'low').length };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Anomaly Detection')}
        description={t('AI-flagged anomalies in consumption, metering, and potential fraud.')}
        breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Anomalies') }]}
        action={<Button variant="outline" loading={running} leftIcon={<RefreshCw className="w-4 h-4" />} onClick={rerun}>{t('Run detection')}</Button>}
      />

      {/* A line that changes when the button is pressed, so a run that finds
          the same thing twice still shows that it ran. */}
      {lastRun && (
        <p className="text-xs text-slate-500 -mt-3">
          {(lastRun.found === 1 ? t('Last run at {time}: 1 account flagged.') : t('Last run at {time}: {count} accounts flagged.'))
            .replace('{time}', lastRun.at.toLocaleTimeString(dateLocale()))
            .replace('{count}', String(lastRun.found))}
        </p>
      )}

      {/*
        An empty list here used to say "Every account is reading within its
        established pattern", which is a claim that everything was checked and
        found well. On this provider's data nothing was checked at all: this
        detector compares a day with the days around it, and a meter
        photographed once a month gives one reading per month, so it has nothing
        to compare. Telling an owner his network is clean when no test ran is
        the worst thing this page could do.

        What CAN be found in monthly readings is found by the rules engine, so
        the page points there instead of reassuring anybody.
      */}
      {anomalies.length === 0 && (
        <Card className="p-8">
          <div className="max-w-2xl">
            <p className="text-base font-semibold text-slate-900 dark:text-slate-100">
              {t('Nothing to detect from monthly readings')}
            </p>
            <p className="text-sm text-slate-500 mt-2">
              {t('This detector compares one day against the days around it. The meters here are read once a month, so there are no daily patterns to compare and no test has been run. That is not a statement that every account is well.')}
            </p>
            <p className="text-sm text-slate-500 mt-2">
              {t('What monthly readings can show (stuck meters, sustained drops, consumption while disconnected) is on the Accounts to visit page, with the evidence behind each one.')}
            </p>
            <Link to="/admin/visits" className="inline-block mt-5">
              <Button variant="outline" rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>
                {t('Open Accounts to visit')}
              </Button>
            </Link>
          </div>
        </Card>
      )}

      {/*
        A dash, not a zero, when the detector could not run.
        The message above says in words that no test was performed; a row of
        four zeros underneath says the opposite, that four counts were taken
        and every one came back empty. Somebody reading only the numbers takes
        away "no critical anomalies", which is a finding nobody made.
      */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: t('Critical'), value: counts.critical, tone: 'text-error-600 bg-error-500/15' },
          { label: t('High'), value: counts.high, tone: 'text-error-600 bg-error-500/15' },
          { label: t('Medium'), value: counts.medium, tone: 'text-warning-600 bg-warning-500/15' },
          { label: t('Low'), value: counts.low, tone: 'text-primary-600 bg-primary-500/15' },
        ].map((s) => (
          <Card key={s.label} className="p-5 flex items-center gap-4">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${s.tone}`}><ShieldCheck className="w-5 h-5" /></div>
            <div>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">
                {anomalies.length === 0 ? '—' : s.value}
              </p>
              <p className="text-xs text-slate-500">{s.label}</p>
            </div>
          </Card>
        ))}
      </div>
      {anomalies.length === 0 && (
        <p className="text-xs text-slate-400 -mt-3">
          {t('Not counted: the detector did not run against these readings.')}
        </p>
      )}

      {/*
        WHERE THIS SHORTLIST CAME FROM, AND WHAT BEAT IT
        The day-level detector cannot run on monthly readings, so these come
        from the model that can. It is the same IsolationForest reported in the
        evaluation, and the evaluation is the reason this paragraph exists: the
        simple rules scored higher on the labelled sample, so a page that
        offered the model's shortlist without saying so would be selling it.
      */}
      {anomalies.some((a) => a.type === MONTHLY) && (
        <Card className="p-5">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {t('These come from the monthly model, not the day-level detector: the meters are read once a month, so there are no daily patterns to compare. It ranks each subscriber against the others on eighteen months of readings and contract data, and every card says which features made it stand out.')}
          </p>
          <p className="text-sm text-slate-500 mt-2">
            {t('Measured against the same labelled sample, the rules engine scored higher than this model (89.5% precision against 60.5%). Work the Accounts to visit list first; treat this one as a second opinion.')}
          </p>
          <Link to="/admin/visits" className="inline-block mt-4">
            <Button variant="outline" rightIcon={<ArrowRight className="w-4 h-4 rtl:-scale-x-100" />}>
              {t('Open Accounts to visit')}
            </Button>
          </Link>
        </Card>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {anomalies.map((a, i) => {
          const cfg = config[a.type] ?? { icon: AlertTriangle, bg: 'bg-slate-500/15', text: 'text-slate-600' };
          const Icon = cfg.icon;
          return (
            <motion.div key={a.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className={`p-5 border-2 ${severityBorder[a.severity] ?? 'border-slate-200 dark:border-slate-700'}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${cfg.bg}`}><Icon className={`w-5 h-5 ${cfg.text}`} /></div>
                  {/* Stored lower-case ("high"); shown as the cards above name it ("High"). */}
                  <Badge tone={severityTone[a.severity] ?? 'neutral'}>{t(severityLabel(a.severity))}</Badge>
                </div>
                {/* `type` stays the stored English: the icon above is chosen by it. */}
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t(a.type)}</h3>
                <p className="text-sm text-slate-500 mt-1">{a.description}</p>
                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs">
                  <span className="font-mono text-slate-600 dark:text-slate-300 ltr-num">{a.customer}</span>
                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{a.value}</Badge>
                    <span className="text-slate-400">{formatDate(a.date)}</span>
                  </div>
                </div>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
