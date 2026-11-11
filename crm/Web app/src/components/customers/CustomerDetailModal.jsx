import React from 'react';
import { useData } from '../../context/DataContext';
import { formatCurrency, formatKwh } from '../../utils/invoiceGenerator';
import {
  X,
  User,
  Phone,
  Mail,
  MapPin,
  CreditCard
} from 'lucide-react';

export default function CustomerDetailModal({ customer, isOpen, onClose, onRecordPayment }) {
  const { invoices } = useData();

  if (!isOpen || !customer) return null;

  const customerInvoices = invoices.filter(i => i.customerId === customer.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-3xl bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-800 bg-gradient-to-r from-slate-900 via-slate-850 to-slate-900">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-extrabold text-xl">
              {customer.name.charAt(0)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-extrabold text-lg text-white">{customer.name}</h3>
                <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-bold">
                  {customer.tariffType}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">Account: {customer.accountNo} | Meter: {customer.meterNo}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto text-xs">
          
          {/* Quick Info Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            
            <div className="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/60 space-y-2">
              <span className="text-slate-400 block font-semibold">Account Balance</span>
              <div className="text-xl font-extrabold text-amber-400">{formatCurrency(customer.balance)}</div>
              <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                customer.balance === 0 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
              }`}>
                {customer.balance === 0 ? 'Fully Paid' : 'Outstanding Balance'}
              </span>
            </div>

            <div className="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/60 space-y-2">
              <span className="text-slate-400 block font-semibold">Current Meter Reading</span>
              <div className="text-xl font-extrabold text-cyan-400 font-mono">{formatKwh(customer.currentReading)}</div>
              <span className="text-[10px] text-slate-500 block">Last log: {customer.lastReadingDate}</span>
            </div>

            <div className="p-4 rounded-2xl bg-slate-800/40 border border-slate-700/60 space-y-2">
              <span className="text-slate-400 block font-semibold">Assigned Field Agent</span>
              <div className="font-bold text-slate-200 text-sm flex items-center gap-1.5">
                <User className="w-4 h-4 text-cyan-400" />
                {customer.assignedEmployeeName}
              </div>
              <span className="text-[10px] text-slate-400 block">{customer.zone}</span>
            </div>

          </div>

          {/* Contact Details */}
          <div className="p-4 rounded-2xl bg-slate-800/20 border border-slate-800 space-y-3">
            <h4 className="font-bold text-slate-300 uppercase tracking-wider text-[10px]">Customer Contact Info</h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-slate-300">
              <div className="flex items-center gap-2">
                <Phone className="w-4 h-4 text-slate-500" />
                <span>{customer.phone || 'N/A'}</span>
              </div>
              <div className="flex items-center gap-2">
                <Mail className="w-4 h-4 text-slate-500" />
                <span>{customer.email || 'N/A'}</span>
              </div>
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-slate-500" />
                <span className="truncate">{customer.address || 'N/A'}</span>
              </div>
            </div>
          </div>

          {/* Action Bar */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                onClose();
                onRecordPayment(customer);
              }}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 font-bold text-white shadow-md hover:opacity-95 transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <CreditCard className="w-4 h-4" /> Record Payment
            </button>
          </div>

          {/* Billing & Invoice History */}
          <div className="space-y-3">
            <h4 className="font-bold text-slate-300 text-sm">Customer Invoice History</h4>
            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full text-left">
                <thead className="bg-slate-800/80 text-slate-400 uppercase font-semibold text-[10px]">
                  <tr>
                    <th className="px-3 py-2.5">Invoice #</th>
                    <th className="px-3 py-2.5">Billing Period</th>
                    <th className="px-3 py-2.5">kWh</th>
                    <th className="px-3 py-2.5">Total ($)</th>
                    <th className="px-3 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 text-slate-300">
                  {customerInvoices.length > 0 ? (
                    customerInvoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-800/30">
                        <td className="px-3 py-2.5 font-mono text-cyan-400 font-semibold">{inv.invoiceNumber}</td>
                        <td className="px-3 py-2.5 text-slate-400">{inv.billingPeriod}</td>
                        <td className="px-3 py-2.5 font-mono">{formatKwh(inv.kwhConsumed)}</td>
                        <td className="px-3 py-2.5 font-bold text-slate-200">{formatCurrency(inv.totalAmount)}</td>
                        <td className="px-3 py-2.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            inv.status === 'Paid' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'
                          }`}>
                            {inv.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="5" className="px-3 py-4 text-center text-slate-500">No invoices recorded for this customer.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
