import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, FileText, Wallet, Gauge, MessageSquare, Download, CreditCard, User, ArrowUpRight, ArrowDownRight, Sparkles, Bell, TrendingUp } from 'lucide-react';
import { LineChart, BarChart, AreaChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { dashboardService, type CustomerDashboard as DashboardData } from '@/services/api';
import { formatCurrency, formatDate, formatKwh, formatMonthLabel, severityLabel } from '@/utils/helpers';
import { t } from '@/i18n/t';

// The stored priority, and the phrase it is shown as.
const PRIORITY_LABEL: Record<string, string> = {
  High: 'High priority', Medium: 'Medium priority', Low: 'Low priority',
};

// Labels stay in English here and are translated where they are rendered:
// this array is evaluated once at import time, so t() would freeze the
// language it happened to be in.
const quickActions = [
  { label: 'Chat with AI', icon: MessageSquare, to: '/app/chatbot', color: 'from-primary-600 to-primary-400' },
  { label: 'Download Bill', icon: Download, to: '/app/bills', color: 'from-emerald-600 to-emerald-400' },
  { label: 'Pay Bill', icon: CreditCard, to: '/app/bills', color: 'from-accent-600 to-accent-400' },
  { label: 'Profile', icon: User, to: '/app/profile', color: 'from-primary-600 to-emerald-400' },
];

/**
 * Colour for the small badge on a summary card.
 *
 * Deliberately separate from the direction of the arrow. Consumption going UP
 * is bad news and consumption going DOWN is good news, so tying the colour to
 * the arrow would paint a rising bill green.
 */
type Sentiment = 'good' | 'bad' | 'neutral';

const sentimentStyles: Record<Sentiment, string> = {
  good: 'text-emerald-600',
  bad: 'text-error-600',
  neutral: 'text-slate-400',
};

interface CardNote {
  /** A figure such as "+4.2%", kept left to right in every language. */
  figure?: string;
  /** Words, which follow the direction of the page. */
  text: string;
  direction: 'up' | 'down' | 'flat';
  sentiment: Sentiment;
}

const severityStyles: Record<string, { bg: string; text: string; tone: 'error' | 'warning' | 'info' | 'success' }> = {
  error: { bg: 'bg-error-500/15', text: 'text-error-600', tone: 'error' },
  warning: { bg: 'bg-warning-500/15', text: 'text-warning-600', tone: 'warning' },
  info: { bg: 'bg-primary-500/15', text: 'text-primary-600', tone: 'info' },
  success: { bg: 'bg-emerald-500/15', text: 'text-emerald-600', tone: 'success' },
};

export default function CustomerDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    dashboardService.getCustomerDashboard().then(setData);
  }, []);

  if (!data) {
    return (
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    );
  }

  // Month-over-month change, measured from the customer's own trend rather
  // than the fixed '+4.2%' that used to sit here and was shown to everybody.
  const trend = data.consumptionTrend ?? [];
  const latestKwh = trend.length ? trend[trend.length - 1].kwh : 0;
  const priorKwh = trend.length > 1 ? trend[trend.length - 2].kwh : 0;
  const consumptionChange = priorKwh > 0 ? ((latestKwh - priorKwh) / priorKwh) * 100 : null;

  const score = data.energySavingScore;
  const hasScore = score !== null && score !== undefined;
  const scoreBasis = data.energySavingBasis === 'year' ? t('vs last year') : data.energySavingBasis === 'month' ? t('vs last month') : null;

  const cards: { label: string; value: string; valueClass: string; icon: typeof Zap; tone: string; note: CardNote | null }[] = [
    {
      label: t('Monthly Consumption'),
      value: formatKwh(data.monthlyConsumption?.kwh ?? 0),
      valueClass: 'text-2xl',
      icon: Zap,
      tone: 'bg-primary-500/15 text-primary-600',
      note: consumptionChange === null
        ? null
        : {
            // Labelled. The Energy Saving Score beside this one is measured
            // against the same month LAST YEAR, so an unlabelled percentage
            // here sat next to a score that appeared to contradict it: one
            // subscriber's card read "+47.0%" above a score of 93/100, and
            // both were right about different questions.
            figure: `${consumptionChange > 0 ? '+' : ''}${consumptionChange.toFixed(1)}%`,
            text: t('vs last month'),
            direction: consumptionChange > 0 ? 'up' : consumptionChange < 0 ? 'down' : 'flat',
            // Using more electricity than last month is not good news.
            sentiment: consumptionChange > 0 ? 'bad' : consumptionChange < 0 ? 'good' : 'neutral',
          },
    },
    {
      label: t('Current Bill'),
      value: formatCurrency(data.currentBill?.amount ?? 0),
      valueClass: 'text-2xl',
      icon: FileText,
      tone: 'bg-emerald-500/15 text-emerald-600',
      note: data.currentBill?.month ? { text: formatMonthLabel(data.currentBill.month), direction: 'flat', sentiment: 'neutral' } : null,
    },
    {
      label: t('Outstanding Balance'),
      value: formatCurrency(data.outstandingBalance),
      valueClass: 'text-2xl',
      icon: Wallet,
      tone: 'bg-warning-500/15 text-warning-600',
      note: data.outstandingBalance > 0
        ? { text: t('Unpaid'), direction: 'flat', sentiment: 'bad' }
        : { text: t('All paid'), direction: 'flat', sentiment: 'good' },
    },
    {
      label: t('Energy Saving Score'),
      value: hasScore ? `${score}/100` : t('Not enough data'),
      valueClass: hasScore ? 'text-2xl' : 'text-base',
      icon: Gauge,
      tone: 'bg-accent-500/15 text-accent-600',
      note: hasScore
        ? { text: scoreBasis ?? '', direction: 'flat', sentiment: score >= 70 ? 'good' : 'bad' }
        : { text: t('Needs 30 days of readings'), direction: 'flat', sentiment: 'neutral' },
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t('Dashboard')}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{t('Welcome back! Here\'s your energy overview.')}</p>
      </div>

      {/* Top cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <motion.div key={c.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${c.tone}`}><Icon className="w-5 h-5" /></div>
                  {c.note && (c.note.figure || c.note.text) && (
                    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${sentimentStyles[c.note.sentiment]}`}>
                      {c.note.direction === 'up' && <ArrowUpRight className="w-3.5 h-3.5" />}
                      {c.note.direction === 'down' && <ArrowDownRight className="w-3.5 h-3.5" />}
                      {c.note.figure && <span className="ltr-num">{c.note.figure}</span>}
                      {c.note.text && <span>{c.note.text}</span>}
                    </span>
                  )}
                </div>
                <p className={`${c.valueClass} font-bold text-slate-900 dark:text-slate-100 ltr-num`}>{c.value}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{c.label}</p>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <LineChart
            title={t('Consumption Trend')}
            labels={(data.consumptionTrend ?? []).map((d) => formatMonthLabel(d.period ?? d.month, true))}
            datasets={[{ label: t('kWh'), data: (data.consumptionTrend ?? []).map((d) => d.kwh), color: '#2563eb', fill: true }]}
            height={300}
          />
        </div>
        <BarChart
          title={t('Monthly Bills')}
          labels={(data.monthlyBills ?? []).map((b) => formatMonthLabel(b.month, true))}
          datasets={[{ label: t('Amount'), data: (data.monthlyBills ?? []).map((b) => b.amount), color: '#10b981' }]}
          height={300}
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <AreaChart
          title={t('Payment History')}
          labels={(data.paymentHistory ?? []).map((p) => formatDate(p.date))}
          datasets={[{ label: t('Amount'), data: (data.paymentHistory ?? []).map((p) => p.amount), color: '#06b6d4' }]}
          height={260}
        />

        {/* Recent recommendations */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Recent Recommendations')}</h3>
            <Link to="/app/recommendations" className="text-xs font-medium text-primary-600 hover:text-primary-700">{t('View all')}</Link>
          </div>
          <div className="space-y-3">
            {(data.recentRecommendations ?? []).map((r) => (
              <div key={r.id} className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50">
                <div className="w-9 h-9 rounded-lg bg-primary-500/15 flex items-center justify-center shrink-0"><Sparkles className="w-4 h-4 text-primary-600" /></div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{r.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {t('Save about {amount} a month').replace('{amount}', formatCurrency(r.estimatedSavings))}
                    {' · '}
                    {t(PRIORITY_LABEL[r.priority] ?? r.priority)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Recent alerts + quick actions */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Recent Alerts')}</h3>
            <Link to="/app/alerts" className="text-xs font-medium text-primary-600 hover:text-primary-700">{t('View all')}</Link>
          </div>
          <div className="space-y-3">
            {(data.recentAlerts ?? []).map((a) => (
              <div key={a.id} className="flex items-start gap-3 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${severityStyles[a.severity]?.bg ?? 'bg-slate-500/15'}`}>
                  <Bell className={`w-4 h-4 ${severityStyles[a.severity]?.text ?? 'text-slate-600'}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{a.title}</p>
                    <Badge tone={severityStyles[a.severity]?.tone ?? 'neutral'}>{severityLabel(a.severity)}</Badge>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">{a.message}</p>
                </div>
                <span className="text-xs text-slate-400 shrink-0">{formatDate(a.date)}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Quick Actions')}</h3>
          <div className="grid grid-cols-2 gap-3">
            {quickActions.map((a) => {
              const Icon = a.icon;
              return (
                <Link key={a.label} to={a.to}>
                  <motion.div whileHover={{ y: -4 }} className="rounded-xl border border-slate-100 dark:border-slate-800 p-4 hover:shadow-card-hover transition-all h-full">
                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${a.color} flex items-center justify-center mb-3`}>
                      <Icon className="w-5 h-5 text-white" />
                    </div>
                    <p className="text-xs font-semibold text-slate-900 dark:text-slate-100">{t(a.label)}</p>
                  </motion.div>
                </Link>
              );
            })}
          </div>
          <Link to="/app/chatbot" className="mt-4 block">
            <Button fullWidth leftIcon={<TrendingUp className="w-4 h-4" />}>{t('Ask AI for savings tips')}</Button>
          </Link>
        </Card>
      </div>
    </div>
  );
}
