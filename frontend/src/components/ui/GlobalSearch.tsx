import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Search, FileText, CreditCard, Lightbulb, Bell, User, AlertTriangle, ArrowRight, Loader2, CornerDownLeft,
} from 'lucide-react';
import { searchService, type SearchResult, type SearchKind } from '@/services/api';
import { formatDate, ltr, severityLabel } from '@/utils/helpers';
import { t } from '@/i18n/t';

/**
 * The search box in the dashboard header.
 *
 * It used to be an <input> with no value, no onChange and no handler: typing
 * in it did nothing at all. It now does two things at once.
 *
 * PAGES are matched here in the browser, from the list below. They are a fixed
 * set known to the frontend, and a round-trip to ask the server what its own
 * pages are called would be absurd.
 *
 * RECORDS are matched by the backend at GET /search, which is role-aware: an
 * administrator searches the customer base and open anomalies, a customer
 * searches their own bills, payments, recommendations and alerts. That query
 * is debounced, so holding a key down does not fire a request per character.
 */

interface PageEntry {
  label: string;
  keywords: string;
  to: string;
}

const customerPages: PageEntry[] = [
  { label: 'Dashboard', keywords: 'dashboard home overview summary', to: '/app/dashboard' },
  { label: 'Consumption', keywords: 'consumption usage kwh energy electricity charts', to: '/app/consumption' },
  { label: 'Bills', keywords: 'bills billing invoice amount due statement', to: '/app/bills' },
  { label: 'Payments', keywords: 'payments paid receipt transaction history', to: '/app/payments' },
  { label: 'Recommendations', keywords: 'recommendations advice savings tips suggestions', to: '/app/recommendations' },
  { label: 'Alerts', keywords: 'alerts notifications warnings anomalies', to: '/app/alerts' },
  { label: 'Chatbot', keywords: 'chatbot chat assistant ai help ask', to: '/app/chatbot' },
  { label: 'Profile', keywords: 'profile account personal details address phone', to: '/app/profile' },
  { label: 'Settings', keywords: 'settings preferences theme language notifications alerts security password', to: '/app/settings' },
];

const adminPages: PageEntry[] = [
  { label: 'Dashboard', keywords: 'dashboard executive overview summary', to: '/admin/dashboard' },
  // The two pages the sidebar lists after the dashboard, which this list had
  // never been told about: searching "loss" found nothing.
  { label: 'Energy Loss', keywords: 'energy loss losses generators zones delivered billed unaccounted', to: '/admin/loss' },
  { label: 'Accounts to visit', keywords: 'accounts to visit field visits rules shortlist flagged meter', to: '/admin/visits' },
  { label: 'Customers', keywords: 'customers accounts users manage', to: '/admin/customers' },
  { label: 'Analytics', keywords: 'analytics insights statistics', to: '/admin/analytics' },
  { label: 'Revenue', keywords: 'revenue income money billing outstanding', to: '/admin/revenue' },
  { label: 'Forecast', keywords: 'forecast demand prediction sarima future', to: '/admin/forecast' },
  { label: 'Segmentation', keywords: 'segmentation clusters kmeans groups', to: '/admin/segmentation' },
  { label: 'Anomalies', keywords: 'anomalies anomaly detection fraud unusual', to: '/admin/anomalies' },
  { label: 'Reports', keywords: 'reports export pdf excel download', to: '/admin/reports' },
  { label: 'Profile', keywords: 'profile account my name email password personal', to: '/admin/profile' },
  { label: 'Settings', keywords: 'settings preferences theme language security notifications', to: '/admin/settings' },
];

const kindIcons: Record<SearchKind, typeof FileText> = {
  customer: User,
  bill: FileText,
  payment: CreditCard,
  recommendation: Lightbulb,
  alert: Bell,
  anomaly: AlertTriangle,
};

const kindLabels: Record<SearchKind, string> = {
  customer: 'Customer',
  bill: 'Bill',
  payment: 'Payment',
  recommendation: 'Recommendation',
  alert: 'Alert',
  anomaly: 'Anomaly',
};

/**
 * Where a result sends you.
 *
 * Bills and payments carry the record id in the query string so the target
 * page can open that exact record, rather than dropping the customer at the
 * top of a list of forty rows and leaving them to find it again. Customers go
 * to the management page with its own search pre-filled for the same reason.
 */
function routeFor(result: SearchResult): string {
  switch (result.kind) {
    case 'customer':
      return `/admin/customers?q=${encodeURIComponent(result.id)}`;
    case 'anomaly':
      return '/admin/anomalies';
    case 'bill':
      return `/app/bills?bill=${encodeURIComponent(result.id)}`;
    case 'payment':
      return `/app/payments?payment=${encodeURIComponent(result.id)}`;
    case 'recommendation':
      return '/app/recommendations';
    case 'alert':
      return '/app/alerts';
    default:
      return '/';
  }
}

/** One part of a result's subtitle, ready to show (see `sublabel` below). */
function segment(part: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(part)) return formatDate(part);
  if (['error', 'warning', 'info', 'success'].includes(part)) return severityLabel(part);
  if (/^[-+]?[\d.,]+(\s?\S+)?$/.test(part) || /^[A-Z][A-Z0-9]*-[A-Z0-9-]+$/.test(part)) return ltr(part);
  return t(part);
}

const DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 2;

type Row =
  | { type: 'page'; key: string; label: string; sublabel: string; to: string; icon: typeof FileText }
  | { type: 'record'; key: string; label: string; sublabel: string; to: string; icon: typeof FileText };

export function GlobalSearch({ role }: { role: 'customer' | 'admin' }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [records, setRecords] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const pages = role === 'admin' ? adminPages : customerPages;
  const trimmed = query.trim();

  // Page matches, computed locally and instantly.
  const pageMatches = useMemo(() => {
    if (trimmed.length < 1) return [];
    const needle = trimmed.toLowerCase();
    // The translated name too: a reader typing in Arabic types the Arabic name.
    return pages
      .filter((p) => p.label.toLowerCase().includes(needle)
        || t(p.label).toLowerCase().includes(needle)
        || p.keywords.includes(needle))
      .slice(0, 4);
  }, [trimmed, pages]);

  // Record matches, fetched from the backend after a pause in typing.
  useEffect(() => {
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setRecords([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    // `cancelled` guards against an earlier, slower response overwriting the
    // results of a later query: without it, results can flicker back to a
    // previous term.
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchService
        .search(trimmed)
        .then((response) => {
          if (!cancelled) setRecords(response.results ?? []);
        })
        .catch(() => {
          if (!cancelled) setRecords([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmed]);

  const rows: Row[] = useMemo(() => {
    const pageRows: Row[] = pageMatches.map((p) => ({
      type: 'page',
      key: `page:${p.to}`,
      label: t(p.label),
      sublabel: t('Go to page'),
      to: p.to,
      icon: ArrowRight,
    }));
    const recordRows: Row[] = records.map((r) => ({
      type: 'record',
      key: `${r.kind}:${r.id}`,
      label: r.title,
      // The subtitle is assembled on the server from a mix of data and closed
      // enumerations, e.g. "11,504,672 LBP · Paid" or "2026-06-12 · Cash".
      // Each segment is shown as what it is: a day in the reader's language, a
      // figure or an ID kept left to right, and anything else through t(),
      // which translates the interface words and returns the rest unchanged.
      sublabel: [t(kindLabels[r.kind]), ...r.subtitle.split(' · ').map(segment)].join(' · '),
      to: routeFor(r),
      icon: kindIcons[r.kind] ?? FileText,
    }));
    return [...pageRows, ...recordRows];
  }, [pageMatches, records]);

  // Keep the highlighted row in range as results arrive and disappear.
  useEffect(() => {
    setActive((current) => (current >= rows.length ? 0 : current));
  }, [rows.length]);

  // Close when the click lands outside the box.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  const go = (to: string) => {
    setOpen(false);
    setQuery('');
    setRecords([]);
    inputRef.current?.blur();
    navigate(to);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (!rows.length) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((i) => (i + 1) % rows.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((i) => (i - 1 + rows.length) % rows.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      go(rows[active].to);
    }
  };

  const showPanel = open && trimmed.length > 0;

  return (
    <div ref={containerRef} className="relative">
      <Search className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
      <input
        ref={inputRef}
        id="global-search"
        type="search"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={role === 'admin' ? t('Search customers and pages...') : t('Search your bills, alerts and pages...')}
        aria-label={t('Search')}
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="global-search-results"
        autoComplete="off"
        className="w-64 h-10 ps-10 pe-9 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
      />
      {loading && <Loader2 className="absolute end-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 animate-spin" />}

      <AnimatePresence>
        {showPanel && (
          <motion.div
            id="global-search-results"
            role="listbox"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="absolute start-0 mt-2 w-[22rem] max-h-96 overflow-y-auto scrollbar-thin rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-card-hover p-2 z-30"
          >
            {rows.length === 0 ? (
              <p className="px-3 py-4 text-sm text-slate-500">
                {loading
                  ? t('Searching...')
                  : trimmed.length < MIN_QUERY_LENGTH
                    ? t('Keep typing to search your records.')
                    : t('Nothing matches "{query}".').replace('{query}', trimmed)}
              </p>
            ) : (
              rows.map((row, index) => {
                const Icon = row.icon;
                return (
                  <button
                    key={row.key}
                    role="option"
                    aria-selected={index === active}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(row.to)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-start transition ${
                      index === active ? 'bg-slate-100 dark:bg-slate-800' : ''
                    }`}
                  >
                    <span className="w-8 h-8 rounded-lg bg-primary-500/10 flex items-center justify-center shrink-0">
                      <Icon className="w-4 h-4 text-primary-600" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{row.label}</span>
                      <span className="block text-xs text-slate-500 truncate">{row.sublabel}</span>
                    </span>
                    {index === active && <CornerDownLeft className="w-3.5 h-3.5 text-slate-400 shrink-0" />}
                  </button>
                );
              })
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
