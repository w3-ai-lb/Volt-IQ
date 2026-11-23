import React from 'react';
import { formatCurrency, formatKwh, getCurrency } from '../../utils/invoiceGenerator';
import { X, Printer, Zap, QrCode } from 'lucide-react';

export default function InvoicePrintView({ invoice, isOpen, onClose }) {
  if (!isOpen || !invoice) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Printable Action Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <span className="font-bold text-sm text-slate-300">Invoice Viewer & Print Document</span>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white text-xs shadow-md hover:opacity-95 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Printer className="w-4 h-4" /> Print / Save as PDF
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Invoice Paper Document Body */}
        <div className="p-8 bg-white text-slate-900 space-y-6 text-xs max-h-[80vh] overflow-y-auto" id="printable-invoice">
          
          {/* Header */}
          <div className="flex items-start justify-between border-b-2 border-slate-900 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-cyan-600 flex items-center justify-center text-white">
                  <Zap className="w-5 h-5" />
                </div>
                <span className="font-black text-xl text-slate-900 tracking-tight">VoltIQ Utility Corp</span>
              </div>
              <p className="text-[11px] text-slate-600 mt-1">100 Electric Avenue, Utility Plaza, Suite 400</p>
              <p className="text-[11px] text-slate-600">Customer Support: 1-800-POWER-GRID</p>
            </div>
            
            <div className="text-right">
              <h2 className="text-xl font-extrabold uppercase text-slate-800 tracking-wider">TAX INVOICE</h2>
              <p className="font-mono font-bold text-sm text-cyan-700">{invoice.invoiceNumber}</p>
              <p className="text-[11px] text-slate-600 mt-1">Issue Date: {invoice.issueDate}</p>
              <p className="text-[11px] font-bold text-red-600">Due Date: {invoice.dueDate}</p>
            </div>
          </div>

          {/* Customer & Billing Info Grid */}
          <div className="grid grid-cols-2 gap-6 bg-slate-50 p-4 rounded-xl border border-slate-200">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Billed To Customer:</span>
              <p className="font-extrabold text-sm text-slate-900">{invoice.customerName}</p>
              <p className="text-slate-600">Account No: <span className="font-mono font-bold text-slate-900">{invoice.accountNo}</span></p>
              <p className="text-slate-600">Meter Serial: <span className="font-mono font-bold text-slate-900">{invoice.meterNo}</span></p>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Billing Summary:</span>
              <p className="text-slate-600">Tariff Class: <span className="font-bold text-slate-900">{invoice.tariffType}</span></p>
              <p className="text-slate-600">Billing Cycle: <span className="font-medium text-slate-800">{invoice.billingPeriod}</span></p>
              <p className="text-slate-600">Payment Status: <span className="font-bold uppercase text-slate-900">{invoice.status}</span></p>
            </div>
          </div>

          {/* Meter Readings Table */}
          <div>
            <h4 className="font-bold text-slate-800 text-xs mb-2 uppercase tracking-wider">Meter Reading Details</h4>
            <table className="w-full text-left border border-slate-200 rounded-lg overflow-hidden">
              <thead className="bg-slate-100 text-slate-700 font-bold text-[10px] uppercase">
                <tr>
                  <th className="p-2.5">Previous Reading</th>
                  <th className="p-2.5">Current Reading</th>
                  <th className="p-2.5">Multiplier</th>
                  <th className="p-2.5 text-right">Net Consumption</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono text-slate-800">
                <tr>
                  <td className="p-2.5">{formatKwh(invoice.previousReading)}</td>
                  <td className="p-2.5">{formatKwh(invoice.currentReading)}</td>
                  <td className="p-2.5">1.0x</td>
                  <td className="p-2.5 text-right font-bold text-cyan-800">{formatKwh(invoice.kwhConsumed)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Charges Breakdown */}
          <div>
            <h4 className="font-bold text-slate-800 text-xs mb-2 uppercase tracking-wider">Itemized Line Charges</h4>
            <table className="w-full text-left border border-slate-200 rounded-lg overflow-hidden">
              <thead className="bg-slate-100 text-slate-700 font-bold text-[10px] uppercase">
                <tr>
                  <th className="p-2.5">Description</th>
                  <th className="p-2.5 text-right">Amount ({getCurrency()})</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-800">
                <tr>
                  <td className="p-2.5 font-medium">Standard Grid Connection Base Fee ({invoice.tariffType})</td>
                  <td className="p-2.5 text-right font-mono">{formatCurrency(invoice.baseCharge)}</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-medium">Energy Consumption ({formatKwh(invoice.kwhConsumed)})</td>
                  <td className="p-2.5 text-right font-mono">{formatCurrency(invoice.consumptionCharge)}</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-medium">State Electricity Value Added Tax (VAT 10%)</td>
                  <td className="p-2.5 text-right font-mono">{formatCurrency(invoice.taxAmount)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Total Footer */}
          <div className="flex items-center justify-between border-t-2 border-slate-900 pt-4">
            <div className="flex items-center gap-3">
              <QrCode className="w-12 h-12 text-slate-800" />
              <div className="text-[10px] text-slate-500">
                <span>Scan QR code to pay via customer mobile portal app.</span>
                <span className="block font-mono text-[9px]">REF: {invoice.id}</span>
              </div>
            </div>

            <div className="text-right space-y-1">
              <span className="text-slate-500 font-bold uppercase text-[10px] block">TOTAL AMOUNT DUE</span>
              <span className="text-2xl font-black text-slate-900 font-mono">{formatCurrency(invoice.totalAmount)}</span>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
