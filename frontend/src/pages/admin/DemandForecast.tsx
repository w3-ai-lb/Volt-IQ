import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Calendar, TrendingUp, Gauge } from 'lucide-react';
import { LineChart, AreaChart } from '@/components/charts/Charts';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { forecastService } from '@/services/api';
import { formatKwh, formatNumber, formatWeekLabel } from '@/utils/helpers';
import { t } from '@/i18n/t';

interface ForecastData {
  forecastData: { label: string; actual: number | null; predicted: number; lower: number; upper: number }[];
  forecastCards: { period: string; kwh: number; lower: number; upper: number; change: number }[];
  // What the fit actually did. Null when there was nothing to fit.
  insights: {
    trend: string;
    peakPeriod: string | null;
    peakKwh: number | null;
    model: string;
    weeksObserved: number;
    horizonWeeks: number;
    seasonal: boolean;
    usesWeather: boolean;
  } | null;
}

export default function DemandForecast() {
  const [data, setData] = useState<ForecastData | null>(null);

  useEffect(() => { forecastService.getForecast().then(setData); }, []);

  if (!data) return <div className="grid sm:grid-cols-3 gap-4">{Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}</div>;

  const insights = data.insights ?? null;
  const insightRows: { label: string; value: string; tone: 'success' | 'warning' | 'info' | 'neutral' | 'error' }[] = insights
    ? [
        {
          label: t('Trend'),
          value: t(insights.trend),
          tone: insights.trend === 'Increasing' ? 'warning' : insights.trend === 'Decreasing' ? 'success' : 'neutral',
        },
        {
          label: t('Peak demand expected'),
          value: insights.peakPeriod
            ? `${formatWeekLabel(insights.peakPeriod)} (${formatKwh(insights.peakKwh ?? 0)})`
            : t('Not enough data'),
          tone: 'neutral',
        },
        // "SARIMA" is a name; "Damped-Trend" is a description and is translated.
        { label: t('Model'), value: t(insights.model), tone: 'info' },
        {
          label: t('Weeks of history used'),
          value: String(insights.weeksObserved),
          tone: 'neutral',
        },
        {
          label: t('Forecast horizon'),
          value: t('{n} weeks').replace('{n}', String(insights.horizonWeeks)),
          tone: 'neutral',
        },
        {
          label: t('Seasonal adjustment'),
          value: insights.seasonal ? t('Applied') : t('Not applied'),
          tone: insights.seasonal ? 'info' : 'neutral',
        },
        {
          // Stated plainly rather than claimed. The model reads consumption
          // history only.
          label: t('Weather factor'),
          value: insights.usesWeather ? t('Included') : t('Not used'),
          tone: 'neutral',
        },
      ]
    : [];

  return (
    <div className="space-y-6">
      <PageHeader title={t('Demand Forecast')} description={t('AI-powered predictions for future electricity demand.')} breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Forecast') }]} />

      <div className="grid sm:grid-cols-3 gap-4">
        {data.forecastCards.map((c, i) => (
          <motion.div key={c.period} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <Card hover className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="w-11 h-11 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow"><Calendar className="w-5 h-5 text-white" /></div>
                <Badge tone={c.change > 5 ? 'warning' : 'success'}><span className="ltr-num">{c.change > 0 ? '+' : ''}{c.change}%</span></Badge>
              </div>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{formatKwh(c.kwh)}</p>
              <p className="text-xs text-slate-500 mt-1">{t(c.period)}</p>
              {/*
                The model's own 90% interval, not a confidence percentage.
                These cards used to read "Confidence: 84%", a constant picked
                by model name, on a dashboard whose Prediction Accuracy card
                reports a measured 34.4% for the same model. The range says the
                same thing truthfully and widens with the horizon, which is
                exactly what a reader needs to see.
              */}
              <div className="mt-3 flex items-center gap-2">
                <Gauge className="w-4 h-4 text-slate-400" />
                <span className="text-xs text-slate-500">
                  {/* "1,200 to 1,800 kWh". The range used to be punctuated with
                      an en dash, which is the right typography and the wrong
                      thing to leave in a string that gets translated: the word
                      is written out, so each language can put it where its own
                      grammar wants it. */}
                  {/* Not isolated as a figure: it is a sentence, and in Arabic
                      its words have to run right to left. */}
                  {t('Likely range')}: <span className="font-semibold text-slate-600 dark:text-slate-300">{t('{lower} to {upper} kWh').replace('{lower}', formatNumber(c.lower)).replace('{upper}', formatNumber(c.upper))}</span>
                </span>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <LineChart
        title={t('Demand Forecast: Actual vs Predicted')}
        labels={data.forecastData.map((d) => formatWeekLabel(d.label))}
        datasets={[
          { label: t('Actual'), data: data.forecastData.map((d) => d.actual), color: '#2563eb' },
          { label: t('Predicted'), data: data.forecastData.map((d) => d.predicted), color: '#10b981', dashed: true },
          { label: t('Upper bound'), data: data.forecastData.map((d) => d.upper), color: '#10b981', fill: true },
          { label: t('Lower bound'), data: data.forecastData.map((d) => d.lower), color: '#10b981', fill: true },
        ]}
        height={320}
      />

      <div className="grid lg:grid-cols-2 gap-4">
        <AreaChart title={t('Confidence Interval')} labels={data.forecastData.map((d) => formatWeekLabel(d.label))} datasets={[{ label: t('Predicted'), data: data.forecastData.map((d) => d.predicted), color: '#06b6d4' }]} height={280} />
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4"><TrendingUp className="w-4 h-4 text-emerald-600" /><h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Forecast Insights')}</h3></div>
          <div className="space-y-3 text-sm">
            {/* Six fixed strings used to sit here, presented as model
                diagnostics: Trend Increasing, Peak Week 7-8, accuracy 94.2%,
                8,760 hours of data, seasonal Applied, weather Included. None
                was computed and the last was untrue, since no weather series
                exists anywhere in this project. These come from the fit. */}
            {insightRows.map((row) => (
              <div key={row.label} className="flex items-center justify-between py-2 border-b border-slate-100 dark:border-slate-800 last:border-0">
                <span className="text-slate-500">{row.label}</span>
                <Badge tone={row.tone}>{row.value}</Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
