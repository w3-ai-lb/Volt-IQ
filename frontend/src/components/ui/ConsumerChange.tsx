import { t } from '@/i18n/t';

/**
 * A customer's month-on-month change in consumption, or a dash when there is
 * none to show.
 *
 * WHY THE NULL CASE HAS TO EXIST
 * ------------------------------
 * The top-consumers list compares the last 30 days of readings against the 30
 * before them. This provider's meters are read by hand once a month, so the
 * earlier window frequently holds no reading at all for a given customer, and
 * there is nothing to compare with.
 *
 * The API used to send 0.0 in that case and this rendered "0.0%" in green,
 * which any reader takes to mean the customer's consumption held steady. It
 * meant the opposite: that we could not tell. Three of the five names on the
 * dashboard were showing it.
 *
 * A rise in consumption is shown in red and a fall in green because this list
 * is read by the provider, for whom a customer's sudden jump is the thing
 * worth looking at.
 */
export function ConsumerChange({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    // A dash, as the comment above says and as every other empty value in the
    // app shows. It had become a stray comma.
    const why = t('No reading in the previous period to compare against');
    return <span className="text-xs text-slate-400" title={why} aria-label={why}>—</span>;
  }
  return (
    <span className={value > 0 ? 'text-xs font-semibold text-error-600' : 'text-xs font-semibold text-emerald-600'}>
      <span className="ltr-num">{value > 0 ? '+' : ''}{value}%</span>
    </span>
  );
}
