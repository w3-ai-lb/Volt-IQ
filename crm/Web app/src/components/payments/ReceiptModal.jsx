import React from 'react';
import { formatCurrency } from '../../utils/invoiceGenerator';
import { X, Printer, CheckCircle2 } from 'lucide-react';

export default function ReceiptModal({ payment, isOpen, onClose }) {
  if (!isOpen || !payment) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Printable Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <span className="font-bold text-sm text-slate-300">Official Payment Receipt</span>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 font-bold text-white text-xs shadow-md hover:opacity-95 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Printer className="w-3.5 h-3.5" /> Print Receipt
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Paper Receipt Content */}
        <div className="p-8 bg-white text-slate-900 space-y-6 text-xs" id="printable-receipt">
          
          <div className="text-center space-y-1 pb-4 border-b border-slate-200">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 mb-1">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h2 className="font-black text-lg text-slate-900 uppercase">Payment Received</h2>
            <p className="text-[11px] text-slate-500">GridPower Utility Corporation</p>
            <p className="font-mono text-xs font-bold text-emerald-700">{payment.receiptNo}</p>
          </div>

          <div className="space-y-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
            <div className="flex justify-between border-b border-slate-200 pb-2">
              <span className="text-slate-500">Customer Account:</span>
              <span className="font-bold text-slate-900">{payment.customerName}</span>
            </div>
            <div className="flex justify-between border-b border-slate-200 pb-2">
              <span className="text-slate-500">Invoice Reference:</span>
              <span className="font-mono font-bold text-slate-800">{payment.invoiceNumber}</span>
            </div>
            <div className="flex justify-between border-b border-slate-200 pb-2">
              <span className="text-slate-500">Transaction Date:</span>
              <span className="font-medium text-slate-800">{payment.paymentDate}</span>
            </div>
            <div className="flex justify-between border-b border-slate-200 pb-2">
              <span className="text-slate-500">Payment Method:</span>
              <span className="font-bold text-slate-800">{payment.paymentMethod}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Reference No:</span>
              <span className="font-mono text-slate-700">{payment.referenceNo}</span>
            </div>
          </div>

          <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 flex items-center justify-between">
            <span className="font-extrabold text-xs text-emerald-900 uppercase">Total Amount Paid</span>
            <span className="text-2xl font-black text-emerald-700 font-mono">{formatCurrency(payment.amount)}</span>
          </div>

          <div className="text-[10px] text-slate-500 pt-2 text-center border-t border-slate-200 space-y-1">
            <p>Processed by: <span className="font-bold text-slate-700">{payment.recordedBy}</span></p>
            <p>Thank you for your prompt electricity bill payment.</p>
          </div>

        </div>

      </div>
    </div>
  );
}
