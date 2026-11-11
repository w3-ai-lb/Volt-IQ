import { useEffect, useState } from 'react';
import { AlertTriangle, MapPin, Wrench, Search, ShieldQuestion } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { ishtirakService, type IshtirakRules } from '@/services/api';
import { formatNumber } from '@/utils/helpers';
import { t } from '@/i18n/t';

/**
 * The rules engine's output, on a screen.
 *
 * WHY THIS PAGE EXISTS
 * --------------------
 * `/ishtirak/rules` has been computed and served since Phase 3 and read by
 * nothing. Thirty-eight flagged accounts out of three hundred, a ranked
 * shortlist of twenty with the evidence behind each one, a per-rule breakdown,
 * and two generator findings with the repair to carry out, all of it
 * recalculated on every request and displayed on no screen in the product.
 *
 * The measured precision of that engine, 89.5%, is one of the headline results
 * of the whole project. It was not possible to look at it.
 *
 * WHAT THIS PAGE IS CAREFUL ABOUT
 * -------------------------------
 * A flag is a hypothesis for a field visit, never a verdict, and the word theft
 * appears nowhere. Every entry shows its evidence AND the ordinary explanations
 * for the same pattern, side by side and with equal weight, because a meter
 * reading identically for eleven months is far more often a broken meter than a
 * dishonest household. Sending somebody to look is the action; deciding what
 * they find is not this system's job.
 */

const RULE_LABELS: Record<string, string> = {
  disconnected_use: 'Consumption while disconnected',
  stuck_meter: 'Meter not advancing',
  reading_went_backwards: 'Reading went backwards',
  over_draw: 'More than the contracted limit',
  sustained_drop: 'Sustained drop in consumption',
};

const RULE_MEANING: Record<string, string> = {
  disconnected_use: 'The account was marked disconnected and the dial still moved.',
  stuck_meter: 'The same number three months running or more. Usually the meter, not the household.',
  reading_went_backwards: 'A reading lower than the one before it, after ruling out a dial rollover.',
  over_draw: 'More energy than the contracted ampere limit can deliver in the hours the zone was supplied.',
  sustained_drop: 'Use fell sharply and stayed down. Four ordinary things look exactly like this.',
};

export default function FieldVisits() {
  const [data, setData] = useState<IshtirakRules | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    ishtirakService.getRules().then(setData).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <Card className="p-5">
        <EmptyState
          icon={<Search className="w-8 h-8" />}
          title={t('The rules could not be run')}
          description={t('Load the provider data first, then reopen this page.')}
        />
      </Card>
    );
  }

  if (!data) {
    return <div className="grid sm:grid-cols-3 gap-4">{Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}</div>;
  }

  const flaggedShare = data.totalSubscribers > 0
    ? Math.round((data.flaggedCount / data.totalSubscribers) * 100)
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{t('Accounts worth a visit')}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          {t('Ranked by how far past the thresholds each case sits. A flag is a reason to go and look, not a conclusion.')}
        </p>
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <Card className="p-5">
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">
            {formatNumber(data.flaggedCount)}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {t('Accounts flagged: {pct}% of {total}')
              .replace('{pct}', String(flaggedShare))
              .replace('{total}', formatNumber(data.totalSubscribers))}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">
            {formatNumber(data.shortlist.length)}
          </p>
          <p className="text-xs text-slate-500 mt-1">{t('On the shortlist below, worst first')}</p>
        </Card>
        <Card className="p-5">
          <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 ltr-num">
            {formatNumber(data.gridFindings.length)}
          </p>
          <p className="text-xs text-slate-500 mt-1">{t('Generator faults: a technician, not a visit')}</p>
        </Card>
      </div>

      {/* The generator findings come first on purpose: correcting one phase
          imbalance is worth more than every flagged household put together, and
          it needs no accusation of anybody. */}
      {data.gridFindings.length > 0 && (
        <Card className="p-5">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
            {t('Fix these first')}
          </h3>
          <p className="text-xs text-slate-500 mb-4">
            {t('These are faults on the network itself. Nobody is at fault and the gain is larger than anything on the shortlist.')}
          </p>
          <div className="space-y-3">
            {data.gridFindings.map((g) => (
              <div key={`${g.generatorId}-${g.rule}`} className="flex items-start gap-3 rounded-xl bg-warning-500/10 p-4">
                <Wrench className="w-5 h-5 text-warning-600 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{g.generatorName}</p>
                  {/* A sentence, translated by the server: it runs in the page's
                      direction, so it is not isolated as a figure. */}
                  <p className="text-sm text-slate-600 dark:text-slate-300 mt-0.5">{g.evidence}</p>
                  <p className="text-sm text-slate-700 dark:text-slate-200 mt-1.5 font-medium">{g.action}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="p-5">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-1">
          {t('Shortlist')}
        </h3>
        <p className="text-xs text-slate-500 mb-4">
          {t('Each entry shows what was measured and, beside it, every ordinary reason the same pattern appears. Read both before sending anyone.')}
        </p>

        {data.shortlist.length === 0 ? (
          <EmptyState
            icon={<Search className="w-8 h-8" />}
            title={t('Nothing is flagged')}
            description={t('No account crossed any of the thresholds in the loaded data.')}
          />
        ) : (
          <div className="space-y-3">
            {data.shortlist.map((s, index) => (
              <div key={s.subscriberId} className="rounded-xl border border-slate-200 dark:border-slate-800 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-start gap-3">
                    <span className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 text-xs font-bold text-slate-500 flex items-center justify-center shrink-0 ltr-num">
                      {index + 1}
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        {s.subscriberName || s.subscriberId}
                      </p>
                      <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3 h-3" />
                        <span className="ltr-num">{s.zoneName || s.zoneId || '—'}</span>
                        {s.subscriberName && <span className="ltr-num">· {s.subscriberId}</span>}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {s.rules.map((r) => (
                      <Badge key={r} tone="warning">{t(RULE_LABELS[r] || r)}</Badge>
                    ))}
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-4 mt-3">
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5 text-error-500" />
                      {t('What was measured')}
                    </p>
                    <ul className="space-y-1">
                      {s.evidence.map((e, i) => (
                        <li key={i} className="text-sm text-slate-700 dark:text-slate-300">{e}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                      <ShieldQuestion className="w-3.5 h-3.5 text-emerald-600" />
                      {t('Ordinary explanations for the same pattern')}
                    </p>
                    <ul className="space-y-1">
                      {s.innocentExplanations.map((e, i) => (
                        <li key={i} className="text-sm text-slate-600 dark:text-slate-400">{e}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/*
                  What to do at the door. The two columns above deliberately
                  reach no conclusion, which left this screen with nothing
                  actionable on it: whoever was sent had the evidence, the
                  innocent explanations, and no idea what to check. These are
                  checks on the meter and the supply, never on the person, and
                  they differ by what was actually found.
                */}
                {s.visitChecks?.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800">
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                      <Wrench className="w-3.5 h-3.5 text-primary-600" />
                      {t('What to check on the visit')}
                    </p>
                    <ul className="space-y-1">
                      {s.visitChecks.map((c, i) => (
                        <li key={i} className="text-sm text-slate-600 dark:text-slate-400">{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="p-5">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">
          {t('What each rule found')}
        </h3>
        <div className="space-y-3">
          {Object.entries(data.perRule).map(([rule, subs]) => (
            <div key={rule} className="flex items-start justify-between gap-4 py-2 border-b border-slate-100 dark:border-slate-800 last:border-0">
              <div>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {t(RULE_LABELS[rule] || rule)}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{t(RULE_MEANING[rule] || '')}</p>
              </div>
              <span className={`text-sm font-semibold shrink-0 ltr-num ${subs.length ? 'text-slate-900 dark:text-slate-100' : 'text-slate-400'}`}>
                {subs.length ? formatNumber(subs.length) : t('none')}
              </span>
            </div>
          ))}
        </div>
        {data.note && <p className="text-xs text-slate-400 mt-4">{data.note}</p>}
      </Card>
    </div>
  );
}
