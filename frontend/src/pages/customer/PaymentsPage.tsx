import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CreditCard, CheckCircle2, Clock, Download } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge, statusTone } from '@/components/ui/Badge';
import { DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { Link } from 'react-router-dom';
import { paymentsService, billsService } from '@/services/api';
import { useToast } from '@/context/ToastContext';
import { formatCurrency, formatDate, formatMonthLabel } from '@/utils/helpers';
import { errorMessage } from '@/utils/errors';
import { t } from '@/i18n/t';

interface Payment { id: string; date: string; amount: number; method: string; status: string; billId?: string | null }
interface Bill { id: string; month: string; amount: number; status: string; paid?: number; remaining?: number }

// Filter values are the stored statuses in lower case; the labels are translated.
const FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'completed', label: 'Completed' },
  { value: 'partial', label: 'Partial' },
];

export default function PaymentsPage() {
  const toast = useToast();
  const [downloading, setDownloading] = useState<string | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  // The bills are loaded beside the payments so a row can say WHICH bill it
  // went against and whether that bill is now settled. A row that reads
  // "Partial" and nothing else invites the customer to look for a way to
  // finish it: on a bill that has since been settled there is nothing to
  // finish, and on one that has not, the way to finish it is a page away and
  // was not linked from here.
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [params] = useSearchParams();
  // Set when the customer arrived from the header search, so the row they
  // picked is marked instead of lost among the others.
  const requestedPayment = params.get('payment');

  useEffect(() => {
    paymentsService.getAll().then((p) => { setPayments(p); setLoading(false); });
    billsService.getAll().then(setBills).catch(() => setBills([]));
  }, []);

  const billFor = (payment: Payment) => bills.find((b) => b.id === payment.billId);
  const owedOn = (bill: Bill) => bill.remaining ?? Math.max(0, bill.amount - (bill.paid ?? 0));

  // Clear the status filter on arrival from search, otherwise the payment the
  // customer just picked can be hidden by a filter they did not set.
  useEffect(() => {
    if (requestedPayment) setFilter('all');
  }, [requestedPayment]);

  const handleReceipt = async (id: string) => {
    setDownloading(id);
    try {
      const filename = await paymentsService.downloadReceipt(id);
      toast({ type: 'success', title: t('Receipt downloaded'), message: filename });
    } catch (error) {
      toast({ type: 'error', title: t('Could not download the receipt'), message: errorMessage(error) });
    } finally {
      setDownloading(null);
    }
  };

  const filtered = filter === 'all' ? payments : payments.filter((p) => p.status.toLowerCase() === filter);
  // Every payment that brought money in: a part payment is money received as
  // much as a full one. Counting only "Completed" left every part payment out
  // of the total. Same rule as the backend (RECEIVED in routers/billing.py).
  const totalPaid = payments.filter((p) => p.status !== 'Failed').reduce((s, p) => s + p.amount, 0);

  // The third tile used to count payments whose status is "Partial", which is
  // a fact about a receipt rather than about the account: a customer whose
  // part payment was followed by a settling one still saw "Partial: 1" and
  // went looking for something to pay. What belongs here is the only figure a
  // customer wants from this page, which is what they still owe.
  const stillOwed = bills.reduce((sum, b) => sum + owedOn(b), 0);

  const stats = [
    { label: t('Total paid'), value: formatCurrency(totalPaid), icon: CreditCard, tone: 'bg-emerald-500/15 text-emerald-600' },
    { label: t('Transactions'), value: String(payments.length), icon: CheckCircle2, tone: 'bg-primary-500/15 text-primary-600' },
    { label: t('Still owed'), value: formatCurrency(stillOwed), icon: Clock, tone: 'bg-warning-500/15 text-warning-600' },
  ];

  return (
    <div>
      <PageHeader title={t('Payment History')} description={t('All your past payments and their statuses.')} breadcrumb={[{ label: t('Dashboard'), href: '/app/dashboard' }, { label: t('Payments') }]} />

      <div className="grid sm:grid-cols-3 gap-4 mb-6">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="p-5 flex items-center gap-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${s.tone}`}><Icon className="w-5 h-5" /></div>
              <div><p className="text-xl font-bold text-slate-900 dark:text-slate-100 ltr-num">{s.value}</p><p className="text-xs text-slate-500">{s.label}</p></div>
            </Card>
          );
        })}
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-sm text-slate-500">{t('Filter:')}</span>
          {FILTERS.map((f) => (
            <button key={f.value} onClick={() => setFilter(f.value)} className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${filter === f.value ? 'bg-primary-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'}`}>{t(f.label)}</button>
          ))}
        </div>
        {loading ? (
          <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} cols={4} />)}</div>
        ) : (
          <DataTable
            columns={[
              { key: 'id', header: t('Payment ID'), render: (p: Payment) => <span className="font-mono text-xs font-semibold whitespace-nowrap ltr-num">{p.id}</span> },
              { key: 'date', header: t('Date'), render: (p: Payment) => formatDate(p.date) },
              { key: 'amount', header: t('Amount'), render: (p: Payment) => <span className="font-semibold">{formatCurrency(p.amount)}</span> },
              // Cash is a word; OMT and Whish are the names of the two transfer services.
              { key: 'method', header: t('Method'), render: (p: Payment) => t(p.method) },
              {
                key: 'bill',
                header: t('Bill'),
                render: (p: Payment) => {
                  const bill = billFor(p);
                  if (!bill) return <span className="text-xs text-slate-400">—</span>;
                  const left = owedOn(bill);
                  return (
                    <div>
                      <span className="text-sm">{formatMonthLabel(bill.month)}</span>
                      {left > 0 ? (
                        <Link
                          to={`/app/bills?bill=${bill.id}`}
                          className="block text-xs font-medium text-primary-600 hover:underline"
                        >
                          {t('{amount} still owed').replace('{amount}', formatCurrency(left))}
                        </Link>
                      ) : (
                        <p className="text-xs text-slate-500">{t('This bill is settled')}</p>
                      )}
                    </div>
                  );
                },
              },
              { key: 'status', header: t('Status'), render: (p: Payment) => <Badge tone={statusTone(p.status)}>{t(p.status)}</Badge> },
              {
                key: 'receipt',
                header: t('Receipt'),
                render: (p: Payment) => (
                  <button
                    onClick={() => handleReceipt(p.id)}
                    disabled={downloading === p.id}
                    aria-label={t('Download receipt for {id}').replace('{id}', p.id)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-primary-600 hover:bg-primary-50 dark:hover:bg-primary-500/10 disabled:opacity-50 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {downloading === p.id ? t('Preparing…') : 'PDF'}
                  </button>
                ),
              },
            ]}
            data={filtered}
            rowKey={(p) => p.id}
            highlightRow={(p) => p.id === requestedPayment}
          />
        )}
      </Card>
    </div>
  );
}
