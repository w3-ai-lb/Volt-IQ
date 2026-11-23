import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Zap, Receipt, TrendingDown, AlertTriangle, Fuel, Activity, Gauge, Search,
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ishtirakService, type IshtirakDashboard, type IshtirakAnswer } from '@/services/api';
import { formatDate, formatKwhCompact, formatNumber, withUnit } from '@/utils/helpers';
import { getLanguage, t } from '@/i18n/t';

/**
 * What the owner opens with his morning coffee.
 *
 * THE DESIGN RULE THIS PAGE IS BUILT AROUND
 * -----------------------------------------
 * "The owner is not an engineer. If a number needs explaining, explain it on
 * the screen. Green / amber / red, not raw statistics."
 *
 * So every zone carries the sentence the backend wrote for it, and the ranking
 * is by the part he can act on rather than by the biggest number. A zone losing
 * 14% because it sits 520 m down a cable needs nothing from him; one losing 8%
 * with half of it unaccounted for is worth an afternoon.
 *
 * WHY THE PERIOD IS PRINTED AT THE TOP
 * ------------------------------------
 * The dataset ends before today. A dashboard headed "today" showing zeroes
 * would be reporting a quiet night at the generators rather than the absence of
 * a file, so the banner says which day the figures are actually for, and says
 * plainly when that is not today.
 */

const band = (pct: number | null | undefined): { tone: string; label: string } => {
  if (pct === null || pct === undefined) return { tone: 'bg-slate-500/15 text-slate-500', label: '—' };
  if (pct >= 3) return { tone: 'bg-error-500/15 text-error-600', label: t('Worth a visit') };
  if (pct >= 1) return { tone: 'bg-warning-500/15 text-warning-600', label: t('Keep watching') };
  return { tone: 'bg-emerald-500/15 text-emerald-600', label: t('Explained') };
};

function AskBox() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<IshtirakAnswer | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    try {
      setAnswer(await ishtirakService.ask(question));
    } catch {
      setAnswer(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="p-5">
      <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
        {t('Ask about your data')}
      </h3>
      <p className="text-sm text-slate-500 mb-4">
        {t('Every figure in an answer comes from a query you can check.')}
      </p>

      <form onSubmit={submit} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
          <input
            id="ask-question"
            name="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('How much did I lose last month?')}
            // A question typed in Arabic reads right to left, in English left
            // to right, whatever the language of the page.
            dir="auto"
            className="w-full ps-9 pe-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-primary-500 outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="px-4 py-2.5 rounded-xl bg-primary-600 text-white text-sm font-medium disabled:opacity-60"
        >
          {loading ? t('Asking…') : t('Ask')}
        </button>
      </form>
      {/* The question engine reads English, and the common questions in
          Arabic as well (the patterns in app/rag/queries.py and engine.py),
          and it answers in English. The placeholder above is translated, so in
          every other language the page says what will actually be understood. */}
      {getLanguage() !== 'en' && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{t('Questions are understood in English, and the common ones in Arabic too. Answers are given in English.')}</p>
      )}

      {answer && (
        <div className="mt-4 space-y-3">
          <div
            className={`p-4 rounded-xl text-sm leading-relaxed ${
              answer.answered
                ? 'bg-slate-50 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                : 'bg-warning-500/10 text-warning-700 dark:text-warning-400'
            }`}
            // The answer is English: laid out left to right even on an Arabic
            // page, so its full stops and figures stay where they belong.
            dir="auto"
          >
            {answer.answer}
          </div>

          {/* NFR-5: a number on screen has to be traceable to a query. This is
              where the owner sees which one, without taking it on trust. */}
          {answer.answered && (answer.readsFrom.length > 0 || answer.citations.length > 0) && (
            <p className="text-xs text-slate-400">
              {answer.source === 'database'
                ? `${t('Read from')}: ${answer.readsFrom.join(', ')}`
                : `${t('Source')}: ${answer.citations.join('; ')}`}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

export default function LossDashboard() {
  const [data, setData] = useState<IshtirakDashboard | null>(null);
  const [months, setMonths] = useState(1);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setData(null);
    setFailed(false);
    ishtirakService.getDashboard(months).then(setData).catch(() => setFailed(true));
  }, [months]);

  if (failed) {
    return (
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {t('No generator data has been loaded yet')}
        </h2>
        <p className="text-sm text-slate-500 mt-2">
          {t('Load the dataset first, then this page fills itself:')}
        </p>
        <code className="block mt-2 text-xs bg-slate-100 dark:bg-slate-800 p-3 rounded-lg ltr-num text-left">
          python -m app.pipeline.ishtirak --dir data/ishtirak
        </code>
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    );
  }

  const cards = [
    { label: t('Delivered'), value: formatKwhCompact(data.producedKwh), icon: Zap, tone: 'bg-primary-500/15 text-primary-600' },
    { label: t('Billed'), value: formatKwhCompact(data.billedKwh), icon: Receipt, tone: 'bg-emerald-500/15 text-emerald-600' },
    { label: t('Unaccounted for'), value: formatKwhCompact(data.gapKwh), icon: TrendingDown, tone: 'bg-warning-500/15 text-warning-600' },
    { label: t('Loss'), value: data.lossPct === null ? t('Not enough data') : `${data.lossPct}%`, icon: Gauge, tone: 'bg-accent-500/15 text-accent-600' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {t('Where the electricity went')}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {t('Produced, billed, and an account of the difference.')}
          </p>
        </div>
        <select
          id="loss-period"
          aria-label={t('Period')}
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-900 dark:text-slate-100"
        >
          <option value={1}>{t('Latest month')}</option>
          <option value={3}>{t('Last 3 months')}</option>
          <option value={12}>{t('Last 12 months')}</option>
          <option value={18}>{t('Everything on record')}</option>
        </select>
      </div>

      {/* The data stops before today, and pretending otherwise is the defect
          this banner exists to prevent. */}
      {!data.isLive && (
        <div className="px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm text-slate-600 dark:text-slate-300">
          {/* One sentence with its dates in the reader's language. It was three
              fragments around ISO dates, which no translation could put in its
              own word order. */}
          {t('These figures are for {start} to {end}. The generator data ends on {date}, so this is not a live view.')
            .replace('{start}', formatDate(data.periodStart))
            .replace('{end}', formatDate(data.periodEnd))
            .replace('{date}', formatDate(data.asOf))}
        </div>
      )}

      <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <motion.div key={c.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <Card hover className="p-5">
                <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 ${c.tone}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{c.value}</p>
                <p className="text-xs text-slate-500 mt-1">{c.label}</p>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* The paragraph the briefing calls the good outcome. */}
      <Card className="p-5 border-s-4 border-s-primary-500">
        <h3 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
          {t('In short')}
        </h3>
        <p className="text-base text-slate-800 dark:text-slate-200 leading-relaxed">{data.summary}</p>
      </Card>

      <AskBox />

      {/* Zones, ranked by what can be acted on. */}
      <Card className="p-5">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
          {t('Neighbourhoods')}
        </h3>
        <p className="text-sm text-slate-500 mb-4">
          {t('Ordered by the part nobody can account for, not by the biggest number.')}
        </p>
        <div className="space-y-3">
          {data.zones.map((z) => {
            const b = band(z.unexplainedPct);
            return (
              <div key={z.zoneId} className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60">
                <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 dark:text-slate-100">{z.name}</span>
                    {z.avgDistanceM && (
                      <span className="text-xs text-slate-400 ltr-num">{z.avgDistanceM} m</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-500">
                      {t('loses')} <span className="ltr-num">{z.lossPct}%</span>
                    </span>
                    <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold ${b.tone}`}>
                      {b.label}
                    </span>
                  </div>
                </div>

                {/* The split, as one bar. Physics first because it is the part
                    that needs no decision from anybody. */}
                <div className="flex h-2 rounded-full overflow-hidden mb-2" title={t('How the loss splits')}>
                  {[
                    ['bg-slate-400', z.normalTechnicalKwh],
                    ['bg-amber-400', z.excessTechnicalKwh],
                    ['bg-sky-400', z.measurementKwh],
                    ['bg-emerald-400', z.unbilledKwh],
                    ['bg-error-500', z.unexplainedKwh],
                  ].map(([cls, value], i) => (
                    <div
                      key={i}
                      className={cls as string}
                      style={{ width: `${z.lossKwh ? ((value as number) / z.lossKwh) * 100 : 0}%` }}
                    />
                  ))}
                </div>

                <p className="text-sm text-slate-600 dark:text-slate-300">{z.explanation}</p>
              </div>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-4 mt-4 text-xs text-slate-500">
          {[
            ['bg-slate-400', t('Normal technical')],
            ['bg-amber-400', t('Excess technical')],
            ['bg-sky-400', t('Measurement')],
            ['bg-emerald-400', t('Your own supply')],
            ['bg-error-500', t('Unexplained')],
          ].map(([cls, label]) => (
            <span key={label as string} className="flex items-center gap-1.5">
              <span className={`w-3 h-2 rounded-full ${cls}`} />
              {label}
            </span>
          ))}
        </div>
      </Card>

      {/* Generators */}
      <Card className="p-5">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">
          {t('Generators')}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-start text-xs uppercase tracking-wide text-slate-400">
                <th className="text-start pb-2">{t('Set')}</th>
                <th className="text-end pb-2">{t('Produced')}</th>
                <th className="text-end pb-2">{t('Hours')}</th>
                <th className="text-end pb-2">{t('Litres per kWh')}</th>
                <th className="text-end pb-2">{t('Phase balance')}</th>
                {/* Named for what it counts. "Alarms" beside a phase-balance
                    column reads as the same signal, and it is not: the sets
                    flagged for imbalance here raised none, and the two that
                    raised one are not flagged. See the note under the table. */}
                <th className="text-end pb-2">{t('Controller alarms')}</th>
              </tr>
            </thead>
            <tbody>
              {data.generators.map((g) => (
                <tr key={g.generatorId} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2.5 font-medium text-slate-900 dark:text-slate-100">{g.name}</td>
                  {/* The figure is isolated, not the cell: a cell set to left-to-right
                      puts "end" on the other side from its header in Arabic. */}
                  <td className="py-2.5 text-end"><span className="ltr-num">{formatKwhCompact(g.producedKwhPeriod)}</span></td>
                  <td className="py-2.5 text-end"><span className="ltr-num">{formatNumber(Math.round(g.runHoursPeriod ?? 0))}</span></td>
                  <td className="py-2.5 text-end">
                    {/* Six sets in seven have no ECU. A zero here would read as
                        a generator that burns no diesel. */}
                    {g.litresPerKwh === null ? (
                      <span className="text-xs text-slate-400">{t('No engine link')}</span>
                    ) : (
                      <span className="ltr-num">{g.litresPerKwh}</span>
                    )}
                  </td>
                  <td className="py-2.5 text-end">
                    {g.phaseImbalancePct === null ? (
                      <span className="text-xs text-slate-400">—</span>
                    ) : (
                      <span
                        className={`inline-flex items-center gap-1 ltr-num ${
                          g.imbalanceFlagged ? 'text-error-600 font-semibold' : 'text-slate-600 dark:text-slate-300'
                        }`}
                      >
                        {g.imbalanceFlagged && <AlertTriangle className="w-3.5 h-3.5" />}
                        {g.phaseImbalancePct}%
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-end">
                    {/* A zero is the ordinary case and should not compete with
                        the figures beside it for attention. */}
                    <span className={`ltr-num ${g.activeAlarms > 0
                      ? 'text-slate-700 dark:text-slate-200 font-semibold'
                      : 'text-slate-400'}`}>{g.activeAlarms}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.generators.some((g) => g.imbalanceFlagged) && (
          <p className="text-sm text-slate-600 dark:text-slate-300 mt-4 flex items-start gap-2">
            <Fuel className="w-4 h-4 mt-0.5 shrink-0 text-error-500" />
            {t('Unequal phase currents return through the neutral wire, which heats up and serves no customer. A technician can correct this.')}
          </p>
        )}
        {/* TWO COLUMNS, TWO DIFFERENT SIGNALS
            Read side by side they invite one conclusion: that the set needing
            a technician is the one with the alarm. On this month's data they
            point at different machines, and neither reading is wrong. So the
            table says what each column is instead of leaving it to be
            inferred. */}
        <p className="text-xs text-slate-500 mt-3 leading-relaxed">
          {t('Controller alarms are counted for the month shown and come from the generator\u2019s own controller log. They are a separate signal from phase balance: a set can run badly out of balance without ever raising one, and raise one without being out of balance. Both are worth acting on, for different reasons.')}
        </p>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">
            {t('Collections')}
          </h3>
          {[
            [t('Invoiced'), data.collections.invoiced],
            [t('Collected'), data.collections.collected],
            [t('Outstanding'), data.collections.outstanding],
          ].map(([label, value]) => (
            <div key={label as string} className="flex justify-between py-2 border-b border-slate-100 dark:border-slate-800 last:border-0">
              <span className="text-sm text-slate-500">{label}</span>
              <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 ltr-num">
                {withUnit(formatNumber(Math.round(value as number)), data.collections.currency)}
              </span>
            </div>
          ))}
          <p className="text-xs text-slate-400 mt-3">
            {t('Invoices with no payment recorded: {n}').replace('{n}', formatNumber(data.collections.unpaidInvoices))}
          </p>
        </Card>

        <Card className="p-5">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">
            {t('Recent alarms')}
          </h3>
          {data.alarms.length === 0 ? (
            <p className="text-sm text-slate-500">{t('No alarms in this period.')}</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {data.alarms.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <Activity
                    className={`w-4 h-4 mt-0.5 shrink-0 ${
                      a.severity === 'alarm' ? 'text-error-500' : 'text-warning-500'
                    }`}
                  />
                  <div>
                    <span className="text-slate-900 dark:text-slate-100">{a.message}</span>
                    <span className="text-xs text-slate-400 ms-2">
                      <span className="ltr-num">{a.generatorName}</span> · {formatDate(a.timestamp.slice(0, 10))}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
