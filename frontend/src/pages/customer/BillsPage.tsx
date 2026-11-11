import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Eye, Download, CreditCard, Info } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge, statusTone } from '@/components/ui/Badge';
import { DataTable } from '@/components/ui/DataTable';
import { PageHeader } from '@/components/ui/Breadcrumb';
import { Modal } from '@/components/ui/Modal';
import { SkeletonRow } from '@/components/ui/Skeleton';
import { useToast } from '@/context/ToastContext';
import { billsService, paymentsService } from '@/services/api';
import { formatCurrency, formatDate, formatMonthLabel } from '@/utils/helpers';
import { errorMessage } from '@/utils/errors';
import { t } from '@/i18n/t';

// `paid` and `remaining` come from the server, which is the only place that
// can see every payment against a bill. 845 of this provider's invoices are
// part paid, so the face value is not what pressing Pay will charge.
interface Bill {
  id: string; month: string; amount: number; dueDate: string; status: string;
  paid?: number; remaining?: number;
}
interface Payment { id: string; billId?: string | null; amount: number }

export default function BillsPage() {
  const toast = useToast();
  const [bills, setBills] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<Bill | null>(null);
  // Which row is mid-request, so its buttons show progress and cannot be
  // double-pressed into two payments for the same bill.
  const [busy, setBusy] = useState<string | null>(null);
  // Payments are loaded so the detail modal can state what has been paid
  // against a bill, in place of the invented charge breakdown it used to show.
  const [payments, setPayments] = useState<Payment[]>([]);
  const [params] = useSearchParams();
  const requestedBill = params.get('bill');
  // The bill waiting on a yes/no, and how the customer says they paid.
  // Nothing is sent until both are settled: see `confirmPay`.
  const [confirming, setConfirming] = useState<Bill | null>(null);
  const [method, setMethod] = useState<'Cash' | 'OMT' | 'Whish'>('Cash');

  /** Total recorded against one bill. Zero when nothing has been paid. */
  const paidFor = (bill: Bill) =>
    bill.paid ?? payments.filter((p) => p.billId === bill.id).reduce((sum, p) => sum + p.amount, 0);

  /**
   * What is still owed, and therefore whether there is anything to pay.
   *
   * The Pay button used to be decided by the status string alone. A bill can
   * read Pending and have nothing left on it — that is what a pipeline re-run
   * leaves behind, because it rebuilds the bills from the provider's file and
   * cannot see a payment taken here. The button appeared, the server refused
   * the click, and the customer was told a bill they had paid was "already
   * settled in full". Asking what is owed instead of what the row says fixes
   * the offer and the refusal together.
   */
  const owedOn = (bill: Bill) =>
    bill.remaining ?? Math.max(0, bill.amount - paidFor(bill));
  const isPayable = (bill: Bill) => bill.status !== 'Paid' && owedOn(bill) > 0;

  useEffect(() => {
    paymentsService.getAll().then(setPayments).catch(() => setPayments([]));
  }, []);

  useEffect(() => {
    billsService.getAll().then((b) => { setBills(b); setLoading(false); });
  }, []);

  // Arriving from the header search with ?bill=<id> opens that bill straight
  // away, rather than leaving the customer to find it in the table again.
  useEffect(() => {
    if (!requestedBill || bills.length === 0) return;
    const match = bills.find((b) => b.id === requestedBill);
    if (match) setViewing(match);
  }, [requestedBill, bills]);

  /**
   * Opens the confirmation. Nothing is sent from here.
   *
   * Pressing Pay used to settle the bill on the spot, with no question asked
   * and no way back: one stray click on a phone wrote a payment against an
   * account and there is no undo in the customer portal. A step that writes a
   * financial record has to be deliberate, and the customer has to be told what
   * the step actually is, which is the second half of the problem, this
   * records that money changed hands, it does not move any.
   */
  const handlePay = (bill: Bill) => {
    setMethod('Cash');
    setConfirming(bill);
  };

  /** Sends it, once the customer has said yes and chosen a channel. */
  const confirmPay = async () => {
    const bill = confirming;
    if (!bill) return;
    setConfirming(null);
    setBusy(bill.id);
    try {
      const payment = await billsService.pay(bill.id, method);
      // Taken from what the server recorded, not assumed. A Partial payment
      // leaves the bill open, and marking the row Paid on any 2xx told the
      // customer a bill was settled when it was not.
      setBills((current) => current.map((b) => {
        if (b.id !== bill.id) return b;
        const paid = paidFor(b) + payment.amount;
        const remaining = Math.max(0, b.amount - paid);
        return { ...b, paid, remaining, status: remaining > 0 ? b.status : 'Paid' };
      }));
      paymentsService.getAll().then(setPayments).catch(() => undefined);
      setViewing(null);
      toast({
        type: 'success',
        title: t('Payment recorded'),
        message: `${formatCurrency(payment.amount)} · ${payment.id}`,
      });
    } catch (error) {
      toast({ type: 'error', title: t('Could not record the payment'), message: errorMessage(error) });
    } finally {
      setBusy(null);
    }
  };

  /** Downloads the bill the server renders. The button used to only say it would. */
  const handleDownload = async (bill: Bill) => {
    setBusy(bill.id);
    try {
      const filename = await billsService.download(bill.id);
      toast({ type: 'success', title: t('Bill downloaded'), message: filename });
    } catch {
      toast({ type: 'error', title: t('Could not download the bill'), message: t('Please try again.') });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader
        title={t('Bills')}
        description={t('View, download, and pay your electricity bills.')}
        breadcrumb={[{ label: t('Dashboard'), href: '/app/dashboard' }, { label: t('Bills') }]}
      />

      <Card className="p-5">
        {loading ? (
          <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={5} />)}</div>
        ) : (
          <DataTable
            columns={[
              { key: 'id', header: t('Bill Number'), render: (b: Bill) => <span className="font-mono text-xs font-semibold text-slate-900 dark:text-slate-100 whitespace-nowrap ltr-num">{b.id}</span> },
              { key: 'month', header: t('Billing Month'), render: (b: Bill) => formatMonthLabel(b.month) },
              {
                key: 'amount', header: t('Amount'),
                render: (b: Bill) => (
                  <div>
                    <span className="font-semibold">{formatCurrency(b.amount)}</span>
                    {/* A part-paid bill shown at face value tells the customer
                        to find several million pounds they do not owe. */}
                    {paidFor(b) > 0 && owedOn(b) > 0 && (
                      <p className="text-xs text-slate-500">
                        {t('{amount} still owed').replace('{amount}', formatCurrency(owedOn(b)))}
                      </p>
                    )}
                  </div>
                ),
              },
              { key: 'dueDate', header: t('Due Date'), render: (b: Bill) => formatDate(b.dueDate) },
              { key: 'status', header: t('Status'), render: (b: Bill) => <Badge tone={statusTone(b.status)}>{t(b.status)}</Badge> },
              {
                key: 'actions', header: t('Actions'), className: 'text-end',
                render: (b: Bill) => (
                  <div className="flex items-center justify-end gap-2">
                    <Button size="sm" variant="ghost" leftIcon={<Eye className="w-4 h-4" />} onClick={() => setViewing(b)}>{t('View')}</Button>
                    <Button size="sm" variant="outline" loading={busy === b.id} leftIcon={<Download className="w-4 h-4" />} onClick={() => handleDownload(b)}>{t('PDF')}</Button>
                    {isPayable(b) && (
                      <Button size="sm" loading={busy === b.id} leftIcon={<CreditCard className="w-4 h-4" />} onClick={() => handlePay(b)}>{t('Pay')}</Button>
                    )}
                  </div>
                ),
              },
            ]}
            data={bills}
            rowKey={(b) => b.id}
            highlightRow={(b) => b.id === requestedBill}
          />
        )}
      </Card>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={viewing?.id} description={viewing ? t('Bill for {month}').replace('{month}', formatMonthLabel(viewing.month)) : undefined} size="md"
        footer={(
          <>
            <Button variant="outline" onClick={() => setViewing(null)}>{t('Close')}</Button>
            {/* A paid bill has nothing to pay, and offering the button anyway
                only produced a 409 from the server. */}
            {viewing && isPayable(viewing) && (
              <Button loading={busy === viewing.id} leftIcon={<CreditCard className="w-4 h-4" />} onClick={() => handlePay(viewing)}>{t('Pay Now')}</Button>
            )}
          </>
        )}
      >
        {viewing && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div><p className="text-xs text-slate-500">{t('Billing period')}</p><p className="text-sm font-medium text-slate-900 dark:text-slate-100">{formatMonthLabel(viewing.month)}</p></div>
              <div><p className="text-xs text-slate-500">{t('Due date')}</p><p className="text-sm font-medium text-slate-900 dark:text-slate-100">{formatDate(viewing.dueDate)}</p></div>
              <div><p className="text-xs text-slate-500">{t('Status')}</p><Badge tone={statusTone(viewing.status)}>{t(viewing.status)}</Badge></div>
              <div><p className="text-xs text-slate-500">{t('Total amount')}</p><p className="text-lg font-bold text-slate-900 dark:text-slate-100">{formatCurrency(viewing.amount)}</p></div>
            </div>
            {/* An "Energy charge / Delivery fee / Taxes" breakdown used to sit
                here, produced by multiplying the total by 0.7, 0.2 and 0.1. The
                Bill entity stores one amount and no components, so those three
                lines were invented. Replaced by what the record actually holds:
                the total, and what has been paid against it. */}
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800/50 p-4 space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">{t('Total')}</span><span className="ltr-num">{formatCurrency(viewing.amount)}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">{t('Paid to date')}</span><span className="ltr-num">{formatCurrency(paidFor(viewing))}</span></div>
              <div className="flex justify-between font-semibold pt-2 border-t border-slate-200 dark:border-slate-700">
                <span>{t('Outstanding')}</span>
                <span className="ltr-num">{formatCurrency(Math.max(0, viewing.amount - paidFor(viewing)))}</span>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/*
        The confirmation.

        It states three things the customer needs before saying yes: how much,
        against which bill, and WHAT PRESSING YES ACTUALLY DOES. The last is the
        one that is easy to leave out and the one that matters most: this
        platform has no connection to any payment provider and moves no money.
        It writes down that a payment was made through one of the provider's own
        channels. A button labelled "Pay" with no explanation invites somebody to
        believe their bill has just been settled from their phone.
      */}
      <Modal
        open={!!confirming}
        onClose={() => setConfirming(null)}
        title={t('Record this payment?')}
        size="sm"
        footer={(
          <>
            <Button variant="outline" onClick={() => setConfirming(null)}>{t('Cancel')}</Button>
            <Button loading={busy === confirming?.id} leftIcon={<CreditCard className="w-4 h-4" />} onClick={confirmPay}>
              {t('Yes, record it')}
            </Button>
          </>
        )}
      >
        {confirming && (
          <div className="space-y-4">
            <div className="rounded-xl bg-slate-50 dark:bg-slate-800/50 p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500">{t('Bill')}</span>
                <span className="font-medium">{confirming.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">{t('Billing period')}</span>
                <span className="font-medium">{formatMonthLabel(confirming.month)}</span>
              </div>
              {paidFor(confirming) > 0 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{t('Bill total')}</span>
                    <span className="ltr-num">{formatCurrency(confirming.amount)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{t('Already paid')}</span>
                    <span className="ltr-num">{formatCurrency(paidFor(confirming))}</span>
                  </div>
                </>
              )}
              {/*
                What is STILL OWED, not the face value of the bill.
                845 of this provider's invoices are part paid. Offering the full
                amount on one of those invited the customer to pay it twice, and
                the server used to accept it: one subscriber owing 4,725,839 on
                a 20,711,549 bill recorded the whole 20,711,549, and the admin's
                revenue rose by sixteen million pounds nobody had handed over.
              */}
              <div className="flex justify-between font-semibold pt-2 border-t border-slate-200 dark:border-slate-700">
                <span>{paidFor(confirming) > 0 ? t('Still owed') : t('Amount')}</span>
                <span className="ltr-num">
                  {formatCurrency(Math.max(0, confirming.amount - paidFor(confirming)))}
                </span>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                {t('How was it paid?')}
              </p>
              <div className="flex gap-2">
                {(['Cash', 'OMT', 'Whish'] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMethod(m)}
                    aria-pressed={method === m}
                    className={`px-4 py-2 rounded-xl text-sm font-medium transition border ${
                      method === m
                        ? 'border-primary-500 bg-primary-500/10 text-primary-700 dark:text-primary-300'
                        : 'border-slate-200 dark:border-slate-700 text-slate-500'
                    }`}
                  >
                    {t(m)}
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-xl bg-warning-500/10 p-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-warning-600 shrink-0 mt-0.5" />
              <p className="text-xs text-slate-600 dark:text-slate-300">
                {t('This records that you paid the provider through one of his channels. No money is taken from a card or a wallet here, and this cannot be undone from your side.')}
              </p>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
