import React, { useState } from 'react';
import { useData } from '../../context/DataContext';
import { useAuth, PERMISSIONS } from '../../context/AuthContext';
import { formatCurrency, formatKwh, getCurrency } from '../../utils/invoiceGenerator';
import InvoicePrintView from '../billing/InvoicePrintView';
import RecordPaymentModal from '../payments/RecordPaymentModal';
import ReceiptModal from '../payments/ReceiptModal';
import {
  CreditCard,
  FileText,
  Search,
  Filter,
  Printer,
  PlusCircle,
  DollarSign
} from 'lucide-react';

export default function BillingAndPaymentsView({ initialTab = 'invoices' }) {
  const { invoices, payments } = useData();
  const { hasPermission } = useAuth();

  const [activeSubTab, setActiveSubTab] = useState(initialTab);

  // Invoice States
  const [invoiceSearch, setInvoiceSearch] = useState('');
  const [invoiceStatus, setInvoiceStatus] = useState('All');
  const [selectedPrintInvoice, setSelectedPrintInvoice] = useState(null);
  const [isPrintInvoiceOpen, setIsPrintInvoiceOpen] = useState(false);

  // Payment States
  const [paymentSearch, setPaymentSearch] = useState('');
  const [isRecordPaymentOpen, setIsRecordPaymentOpen] = useState(false);
  const [selectedPayInvoice, setSelectedPayInvoice] = useState(null);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);

  // Filtered Data
  const filteredInvoices = invoices.filter((inv) => {
    const matchesSearch =
      inv.invoiceNumber.toLowerCase().includes(invoiceSearch.toLowerCase()) ||
      inv.customerName.toLowerCase().includes(invoiceSearch.toLowerCase()) ||
      inv.accountNo.toLowerCase().includes(invoiceSearch.toLowerCase());

    const matchesStatus = invoiceStatus === 'All' || inv.status === invoiceStatus;
    return matchesSearch && matchesStatus;
  });

  const filteredPayments = payments.filter((p) =>
    p.customerName.toLowerCase().includes(paymentSearch.toLowerCase()) ||
    p.receiptNo.toLowerCase().includes(paymentSearch.toLowerCase()) ||
    p.invoiceNumber.toLowerCase().includes(paymentSearch.toLowerCase()) ||
    p.referenceNo.toLowerCase().includes(paymentSearch.toLowerCase())
  );

  const totalCollected = filteredPayments.reduce((sum, p) => sum + (parseFloat(p.amount) || 0), 0);

  return (
    <div className="space-y-6 pb-12">
      
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            Billing & Payments Management <CreditCard className="w-5 h-5 text-cyan-400" />
          </h2>
          <p className="text-xs text-slate-400">
            Unified Utility Portal: View invoices, print tax billing statements, record customer payments, and issue receipts.
          </p>
        </div>

        {hasPermission(PERMISSIONS.RECORD_PAYMENTS) && (
          <button
            onClick={() => {
              setSelectedPayInvoice(null);
              setIsRecordPaymentOpen(true);
            }}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 font-bold text-white text-xs shadow-md shadow-emerald-500/20 hover:opacity-95 transition-all flex items-center gap-2 cursor-pointer self-start sm:self-auto"
          >
            <PlusCircle className="w-4 h-4" /> Record New Payment
          </button>
        )}
      </div>

      {/* Navigation Sub-Tabs Switcher */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveSubTab('invoices')}
          className={`px-4 py-2.5 rounded-xl font-bold text-xs transition-all flex items-center gap-2 cursor-pointer ${
            activeSubTab === 'invoices'
              ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" /> Invoices Ledger ({invoices.length})
        </button>

        <button
          onClick={() => setActiveSubTab('payments')}
          className={`px-4 py-2.5 rounded-xl font-bold text-xs transition-all flex items-center gap-2 cursor-pointer ${
            activeSubTab === 'payments'
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <CreditCard className="w-4 h-4" /> Payment Logs & Receipts ({payments.length})
        </button>
      </div>

      {/* --- INVOICES SUB-TAB --- */}
      {activeSubTab === 'invoices' && (
        <div className="space-y-4">
          
          {/* Invoice Filters */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-slate-900/80 p-4 rounded-2xl border border-slate-800">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search Invoice #, Customer Name, Account #..."
                value={invoiceSearch}
                onChange={(e) => setInvoiceSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-100 placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-slate-400 shrink-0" />
              <select
                value={invoiceStatus}
                onChange={(e) => setInvoiceStatus(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-200 focus:border-cyan-500 focus:outline-none"
              >
                <option value="All">All Invoice Statuses</option>
                <option value="Unpaid">Unpaid</option>
                <option value="Paid">Paid</option>
                <option value="Overdue">Overdue</option>
                <option value="Partial">Partial</option>
              </select>
            </div>
          </div>

          {/* Invoices Ledger Table */}
          <div className="p-4 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
                  <tr>
                    <th className="px-4 py-3 rounded-l-xl">Invoice No</th>
                    <th className="px-4 py-3">Customer & Account</th>
                    <th className="px-4 py-3">Billing Period</th>
                    <th className="px-4 py-3">Consumed</th>
                    <th className="px-4 py-3">Amount ({getCurrency()})</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 rounded-r-xl text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {filteredInvoices.length > 0 ? (
                    filteredInvoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-cyan-400">{inv.invoiceNumber}</td>
                        
                        <td className="px-4 py-3">
                          <span className="font-bold text-slate-100 block">{inv.customerName}</span>
                          <span className="text-[10px] text-slate-400 font-mono">{inv.accountNo}</span>
                        </td>

                        <td className="px-4 py-3 text-slate-400">{inv.billingPeriod}</td>

                        <td className="px-4 py-3 font-mono text-slate-200 font-semibold">{formatKwh(inv.kwhConsumed)}</td>

                        <td className="px-4 py-3 font-bold text-slate-100">{formatCurrency(inv.totalAmount)}</td>

                        <td className="px-4 py-3">
                          <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${
                            inv.status === 'Paid'
                              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                              : inv.status === 'Overdue'
                              ? 'bg-red-500/20 text-red-400 border-red-500/30'
                              : 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                          }`}>
                            {inv.status}
                          </span>
                        </td>

                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => {
                                setSelectedPrintInvoice(inv);
                                setIsPrintInvoiceOpen(true);
                              }}
                              className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-cyan-400 hover:bg-slate-700 transition-colors cursor-pointer"
                              title="Print Tax Invoice"
                            >
                              <Printer className="w-4 h-4" />
                            </button>

                            {inv.status !== 'Paid' && (
                              <button
                                onClick={() => {
                                  setSelectedPayInvoice(inv);
                                  setIsRecordPaymentOpen(true);
                                }}
                                className="px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/30 font-semibold text-[11px] transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <CreditCard className="w-3.5 h-3.5" /> Record Pay
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                        No invoices match your search query.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* --- PAYMENTS SUB-TAB --- */}
      {activeSubTab === 'payments' && (
        <div className="space-y-4">
          
          {/* Summary Banner */}
          <div className="p-4 rounded-2xl bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                <DollarSign className="w-6 h-6" />
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-400">Total Revenue Collected</span>
                <div className="text-xl font-extrabold text-emerald-400 font-mono">{formatCurrency(totalCollected)}</div>
              </div>
            </div>

            <span className="text-xs text-slate-400">
              Showing {filteredPayments.length} Processed Receipts
            </span>
          </div>

          {/* Payment Search */}
          <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800">
            <div className="relative max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                placeholder="Search by Receipt #, Customer Name, Ref #..."
                value={paymentSearch}
                onChange={(e) => setPaymentSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Payment Table */}
          <div className="p-4 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-800/80 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
                  <tr>
                    <th className="px-4 py-3 rounded-l-xl">Receipt #</th>
                    <th className="px-4 py-3">Customer Account</th>
                    <th className="px-4 py-3">Invoice Ref</th>
                    <th className="px-4 py-3">Method</th>
                    <th className="px-4 py-3">Amount ({getCurrency()})</th>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Recorded By</th>
                    <th className="px-4 py-3 rounded-r-xl text-right">Receipt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {filteredPayments.length > 0 ? (
                    filteredPayments.map((pay) => (
                      <tr key={pay.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-emerald-400">{pay.receiptNo}</td>
                        <td className="px-4 py-3 font-semibold text-slate-100">{pay.customerName}</td>
                        <td className="px-4 py-3 font-mono text-slate-400">{pay.invoiceNumber}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-300 font-medium">
                            {pay.paymentMethod}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-extrabold text-emerald-400 font-mono">{formatCurrency(pay.amount)}</td>
                        <td className="px-4 py-3 text-slate-400">{pay.paymentDate}</td>
                        <td className="px-4 py-3 text-slate-400">{pay.recordedBy}</td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => {
                              setSelectedReceipt(pay);
                              setIsReceiptOpen(true);
                            }}
                            className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-colors cursor-pointer"
                            title="View Official Receipt"
                          >
                            <Printer className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="8" className="px-4 py-8 text-center text-slate-500">
                        No payment logs match your search.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Printable Invoice Modal */}
      <InvoicePrintView
        isOpen={isPrintInvoiceOpen}
        onClose={() => setIsPrintInvoiceOpen(false)}
        invoice={selectedPrintInvoice}
      />

      {/* Record Payment Modal */}
      <RecordPaymentModal
        isOpen={isRecordPaymentOpen}
        onClose={() => {
          setIsRecordPaymentOpen(false);
          setSelectedPayInvoice(null);
        }}
        preselectedInvoice={selectedPayInvoice}
        onPaymentSuccess={(newPay) => {
          setSelectedReceipt(newPay);
          setIsReceiptOpen(true);
        }}
      />

      {/* Receipt Modal */}
      <ReceiptModal
        isOpen={isReceiptOpen}
        onClose={() => setIsReceiptOpen(false)}
        payment={selectedReceipt}
      />

    </div>
  );
}
