import React, { useState, useEffect } from 'react';
import { useData } from '../../context/DataContext';
import { useAuth } from '../../context/AuthContext';
import { formatCurrency } from '../../utils/invoiceGenerator';
import { X, CreditCard, CheckCircle2 } from 'lucide-react';

export default function RecordPaymentModal({
  isOpen,
  onClose,
  preselectedCustomer = null,
  preselectedInvoice = null,
  onPaymentSuccess
}) {
  const { customers, recordPayment } = useData();
  const { currentUser } = useAuth();

  const [selectedCustomerId, setSelectedCustomerId] = useState(preselectedCustomer?.id || customers[0]?.id || '');
  const [amount, setAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('Credit Card');
  const [referenceNo, setReferenceNo] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (preselectedInvoice) {
      setSelectedCustomerId(preselectedInvoice.customerId);
      const due = (preselectedInvoice.totalAmount || 0) - (preselectedInvoice.paidAmount || 0);
      setAmount(due > 0 ? String(Math.round(due * 100) / 100) : '');
    } else if (preselectedCustomer) {
      setSelectedCustomerId(preselectedCustomer.id);
      setAmount(preselectedCustomer.balance > 0 ? String(preselectedCustomer.balance) : '');
    } else if (customers.length > 0) {
      const c = customers.find(item => item.id === selectedCustomerId) || customers[0];
      if (c && c.balance > 0) {
        setAmount(String(c.balance));
      }
    }
  }, [preselectedCustomer, preselectedInvoice, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!selectedCustomerId || !amount) return;

    const payment = recordPayment({
      customerId: selectedCustomerId,
      invoiceId: preselectedInvoice?.id || null,
      amount: parseFloat(amount),
      paymentMethod,
      referenceNo: referenceNo || `TXN-${Math.floor(100000 + Math.random() * 900000)}`,
      notes,
      recordedBy: currentUser ? `${currentUser.name} (${currentUser.roleTitle})` : 'Office Employee'
    });

    if (onPaymentSuccess && payment) {
      onPaymentSuccess(payment);
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md overflow-y-auto animate-in fade-in">
      <div className="relative w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-3xl shadow-2xl overflow-hidden my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <CreditCard className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">Record Customer Payment</h3>
              <p className="text-xs text-slate-400">Office Payment Processing Terminal</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 text-xs">
          
          <div>
            <label className="block font-semibold text-slate-300 mb-1">Customer Account *</label>
            <select
              value={selectedCustomerId}
              onChange={(e) => {
                const id = e.target.value;
                setSelectedCustomerId(id);
                const c = customers.find(item => item.id === id);
                if (c && c.balance > 0) {
                  setAmount(String(c.balance));
                } else {
                  setAmount('');
                }
              }}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-emerald-500 focus:outline-none"
            >
              {customers.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.accountNo}) - Outstanding Balance: {formatCurrency(c.balance)}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Payment Amount ($) *</label>
              <input
                type="number"
                step="0.01"
                required
                placeholder="0.00"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 font-mono text-sm focus:border-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Payment Method</label>
              <select
                value={paymentMethod}
                onChange={e => setPaymentMethod(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 focus:border-emerald-500 focus:outline-none"
              >
                <option value="Credit Card">Credit Card</option>
                <option value="Cash">Cash</option>
                <option value="Check">Check</option>
                <option value="Bank Transfer">Bank Transfer (ACH/Wire)</option>
                <option value="Mobile Money">Mobile Money App</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block font-semibold text-slate-300 mb-1">Transaction Ref / Check No</label>
            <input
              type="text"
              placeholder="e.g. TXN-9912048 / Check # 8820"
              value={referenceNo}
              onChange={e => setReferenceNo(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-100 font-mono focus:border-emerald-500 focus:outline-none"
            />
          </div>

          {/* Form Actions */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-semibold transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 font-bold text-white shadow-md hover:opacity-95 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" /> Record Payment & Issue Receipt
            </button>
          </div>

        </form>

      </div>
    </div>
  );
}
