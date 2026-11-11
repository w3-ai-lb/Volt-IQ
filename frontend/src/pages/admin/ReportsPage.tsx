import { useEffect, useState } from 'react';
import { FileText, Download, FileSpreadsheet, Calendar, Filter } from 'lucide-react';
import { Card, CardBody } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { useToast } from '@/context/ToastContext';
import { reportService } from '@/services/api';
import { t } from '@/i18n/t';

/** YYYY-MM-DD in local time. `toISOString` would shift the date across UTC. */
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/**
 * The quick-select ranges, each computed from today when it is pressed rather
 * than baked in, so the label and the dates agree.
 */
const QUICK_RANGES: { label: string; range: () => [string, string] }[] = [
  {
    label: 'This week',
    range: () => {
      const now = new Date();
      // Monday as the first day, which is the convention in Lebanon and in the
      // weekday ordering the heatmap already uses.
      const monday = new Date(now);
      monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
      return [iso(monday), iso(now)];
    },
  },
  {
    label: 'This month',
    range: () => {
      const now = new Date();
      return [iso(new Date(now.getFullYear(), now.getMonth(), 1)), iso(now)];
    },
  },
  {
    label: 'This quarter',
    range: () => {
      const now = new Date();
      const firstMonth = Math.floor(now.getMonth() / 3) * 3;
      return [iso(new Date(now.getFullYear(), firstMonth, 1)), iso(now)];
    },
  },
  {
    label: 'This year',
    range: () => {
      const now = new Date();
      return [iso(new Date(now.getFullYear(), 0, 1)), iso(now)];
    },
  },
  {
    label: 'Last 30 days',
    range: () => {
      const now = new Date();
      const start = new Date(now);
      start.setDate(now.getDate() - 29);
      return [iso(start), iso(now)];
    },
  },
];

/**
 * The six report types, kept in step with GET /reports.
 *
 * Used as the initial list so the page renders instantly, then replaced by
 * what the server reports. Hardcoding it alone would let the page drift from
 * the endpoint that actually produces the files.
 */
const reportTypes = [
  { id: 'revenue', label: 'Revenue Report', description: 'Monthly revenue breakdown by region and plan' },
  { id: 'consumption', label: 'Consumption Report', description: 'Aggregate consumption patterns and trends' },
  { id: 'customers', label: 'Customer Report', description: 'Customer growth, churn, and segmentation' },
  { id: 'anomalies', label: 'Anomaly Report', description: 'All detected anomalies and resolutions' },
  { id: 'forecast', label: 'Forecast Report', description: 'Demand forecast predictions and a backtest diagnostic' },
  { id: 'billing', label: 'Billing Report', description: 'Bills issued, payments, and outstanding balances' },
];

export default function ReportsPage() {
  const toast = useToast();
  const [selected, setSelected] = useState('revenue');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [format, setFormat] = useState<'pdf' | 'excel'>('pdf');
  const [generating, setGenerating] = useState(false);
  const [types, setTypes] = useState(reportTypes);

  useEffect(() => {
    reportService
      .getTypes()
      .then((rows) => { if (rows.length) setTypes(rows); })
      .catch(() => undefined);   // the built-in list stays as the fallback
  }, []);

  const handleGenerate = async () => {
    if (!from || !to) { toast({ type: 'error', title: t('Date range required'), message: t('Please select a start and end date.') }); return; }
    if (from > to) { toast({ type: 'error', title: t('Invalid range'), message: t('The start date must be before the end date.') }); return; }

    setGenerating(true);
    try {
      // The backend builds the report and returns a file; this saves it.
      const filename = await reportService.download(selected, from, to, format);
      toast({ type: 'success', title: t('Report downloaded'), message: filename });
    } catch (error) {
      // A failed download arrives as a Blob, so the JSON error has to be read out of it.
      const err = error as { response?: { data?: unknown } };
      let message = t('Could not generate the report. Is the backend running?');
      const data = err?.response?.data;
      if (data instanceof Blob) {
        try {
          const parsed = JSON.parse(await data.text());
          // The server's refusals are catalogue phrases (see utils/errors.ts).
          if (typeof parsed?.detail === 'string' && parsed.detail) message = t(parsed.detail);
        } catch {
          /* not JSON, keep the generic message */
        }
      }
      toast({ type: 'error', title: t('Report failed'), message });
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div>
      <PageHeader title={t('Reports')} description={t('Generate and export detailed reports for any period.')} breadcrumb={[{ label: t('Dashboard'), href: '/admin/dashboard' }, { label: t('Reports') }]} />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardBody>
              <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Select Report Type')}</h3>
              <div className="grid sm:grid-cols-2 gap-3">
                {types.map((r) => (
                  <button key={r.id} onClick={() => setSelected(r.id)} className={`text-start p-4 rounded-xl border-2 transition ${selected === r.id ? 'border-primary-600 bg-primary-50 dark:bg-primary-500/10' : 'border-slate-200 dark:border-slate-700 hover:border-slate-300'}`}>
                    <div className="flex items-center gap-2.5 mb-1">
                      <FileText className={`w-4 h-4 ${selected === r.id ? 'text-primary-600' : 'text-slate-400'}`} />
                      <p className={`text-sm font-semibold ${selected === r.id ? 'text-primary-700 dark:text-primary-300' : 'text-slate-900 dark:text-slate-100'}`}>{t(r.label)}</p>
                    </div>
                    <p className="text-xs text-slate-500">{t(r.description)}</p>
                  </button>
                ))}
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardBody>
              <div className="flex items-center gap-2 mb-4"><Filter className="w-4 h-4 text-slate-400" /><h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{t('Date Range')}</h3></div>
              <div className="grid sm:grid-cols-2 gap-4">
                <Input label={t('From')} type="date" value={from} onChange={(e) => setFrom(e.target.value)} leftIcon={<Calendar className="w-4 h-4" />} />
                <Input label={t('To')} type="date" value={to} onChange={(e) => setTo(e.target.value)} leftIcon={<Calendar className="w-4 h-4" />} />
              </div>
              <div className="mt-4">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">{t('Quick select')}</p>
                {/* All five of these used to set the same fixed range,
                    2025-11-01 to 2025-11-30, so four of the labels were simply
                    untrue and the fifth was right by accident. */}
                <div className="flex flex-wrap gap-2">
                  {QUICK_RANGES.map((q) => (
                    <button
                      key={q.label}
                      onClick={() => { const [start, end] = q.range(); setFrom(start); setTo(end); }}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-primary-50 dark:hover:bg-primary-500/10 hover:text-primary-600 transition"
                    >
                      {t(q.label)}
                    </button>
                  ))}
                </div>
              </div>
            </CardBody>
          </Card>
        </div>

        <Card className="p-6 h-fit sticky top-24">
          <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100 mb-4">{t('Export Options')}</h3>
          <div className="space-y-3 mb-6">
            <button onClick={() => setFormat('pdf')} className={`w-full flex items-center gap-3 p-4 rounded-xl border-2 transition ${format === 'pdf' ? 'border-primary-600 bg-primary-50 dark:bg-primary-500/10' : 'border-slate-200 dark:border-slate-700'}`}>
              <div className="w-10 h-10 rounded-lg bg-error-500/15 flex items-center justify-center"><FileText className="w-5 h-5 text-error-600" /></div>
              <div className="text-start"><p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('PDF')}</p><p className="text-xs text-slate-500">{t('Print-ready document')}</p></div>
            </button>
            <button onClick={() => setFormat('excel')} className={`w-full flex items-center gap-3 p-4 rounded-xl border-2 transition ${format === 'excel' ? 'border-primary-600 bg-primary-50 dark:bg-primary-500/10' : 'border-slate-200 dark:border-slate-700'}`}>
              <div className="w-10 h-10 rounded-lg bg-emerald-500/15 flex items-center justify-center"><FileSpreadsheet className="w-5 h-5 text-emerald-600" /></div>
              <div className="text-start"><p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{t('Excel')}</p><p className="text-xs text-slate-500">{t('Spreadsheet format')}</p></div>
            </button>
          </div>
          <Button fullWidth loading={generating} leftIcon={<Download className="w-4 h-4" />} onClick={handleGenerate}>{t('Generate & Export')}</Button>
          <p className="text-xs text-slate-400 mt-3 text-center">{t('The report is generated by the server and saved to your device.')}</p>
        </Card>
      </div>
    </div>
  );
}
