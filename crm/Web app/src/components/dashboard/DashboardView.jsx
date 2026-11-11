import React from 'react';
import { useData } from '../../context/DataContext';
import { useAuth, PERMISSIONS } from '../../context/AuthContext';
import { useSettings } from '../../context/SettingsContext';
import { formatCurrency, formatKwh } from '../../utils/invoiceGenerator';
import {
  Users,
  DollarSign,
  AlertCircle,
  Zap,
  UserPlus,
  CreditCard,
  ArrowUpRight,
  TrendingUp
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

export default function DashboardView({ onNavigate }) {
  const { getDashboardStats, invoices, payments, customers } = useData();
  const { hasPermission } = useAuth();
  const { t } = useSettings();

  const stats = getDashboardStats();

  // Chart data preparation
  const monthlyData = [
    { month: 'Feb', kwh: 12400, revenue: 2100, outstanding: 450 },
    { month: 'Mar', kwh: 13800, revenue: 2450, outstanding: 380 },
    { month: 'Apr', kwh: 15200, revenue: 2800, outstanding: 520 },
    { month: 'May', kwh: 14100, revenue: 2600, outstanding: 410 },
    { month: 'Jun', kwh: 16900, revenue: 3100, outstanding: 600 },
    { month: 'Jul', kwh: stats.totalKwhConsumed || 18200, revenue: stats.totalRevenue || 3450, outstanding: stats.outstandingPayments || 840 }
  ];

  return (
    <div className="space-y-6 pb-12">
      
      {/* Top Banner / Welcome */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-3xl bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 border border-slate-700/80 shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
        <div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-2">
            GridPower Command Dashboard <Zap className="w-6 h-6 text-cyan-400" />
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-xl">
            Real-time monitoring of electricity consumption, customer accounts, and billing revenue collections.
          </p>
        </div>

        {/* Quick Action Buttons */}
        <div className="flex flex-wrap items-center gap-2 z-10">
          {hasPermission(PERMISSIONS.ADD_CUSTOMER) && (
            <button
              onClick={() => onNavigate('customers')}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 font-bold text-white text-xs shadow-md shadow-cyan-500/20 hover:opacity-95 transition-all flex items-center gap-2 cursor-pointer"
            >
              <UserPlus className="w-4 h-4" /> Add Customer
            </button>
          )}

          <button
            onClick={() => onNavigate('billing-payments')}
            className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 font-semibold text-slate-200 text-xs transition-colors flex items-center gap-2 cursor-pointer"
          >
            <CreditCard className="w-4 h-4 text-emerald-400" /> {t('recordPayment')}
          </button>
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        
        {/* Metric 1: Total Customers */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all shadow-lg relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">{t('totalCustomers')}</span>
            <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Users className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-white tracking-tight">{stats.totalCustomers}</span>
            <span className="text-xs text-emerald-400 ml-2 font-semibold">Active Accounts</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500 flex justify-between">
            <span>Residential: {customers.filter(c => c.tariffType === 'Residential').length}</span>
            <span>Commercial: {customers.filter(c => c.tariffType === 'Commercial').length}</span>
          </div>
        </div>

        {/* Metric 2: Total Revenue */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all shadow-lg relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">{t('totalRevenue')}</span>
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <DollarSign className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-emerald-400 tracking-tight">{formatCurrency(stats.totalRevenue)}</span>
            <span className="text-xs text-emerald-400/80 ml-2 font-medium flex items-center inline-flex">
              <TrendingUp className="w-3 h-3 mr-0.5" /> +12.4%
            </span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500">
            Recorded Payments: {payments.length} Receipts
          </div>
        </div>

        {/* Metric 3: Outstanding Payments */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all shadow-lg relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">{t('outstandingPayments')}</span>
            <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
              <AlertCircle className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-amber-400 tracking-tight">{formatCurrency(stats.outstandingPayments)}</span>
            <span className="text-xs text-amber-400/80 ml-2 font-medium">Pending Bills</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500">
            Unpaid Invoices: {invoices.filter(i => i.status !== 'Paid').length}
          </div>
        </div>

        {/* Metric 4: Electricity Consumption */}
        <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 hover:border-slate-700 transition-all shadow-lg relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400">{t('electricityConsumption')}</span>
            <div className="p-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Zap className="w-5 h-5" />
            </div>
          </div>
          <div className="mt-3">
            <span className="text-2xl font-extrabold text-cyan-400 tracking-tight">{formatKwh(stats.totalKwhConsumed)}</span>
          </div>
          <div className="mt-2 text-[11px] text-slate-500">
            Network Meter Readings Logged
          </div>
        </div>

      </div>

      {/* Main Consumption Trend Chart */}
      <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-white">Monthly Electricity Consumption (kWh)</h3>
            <p className="text-xs text-slate-400">Grid network load trends over the past 6 months</p>
          </div>
          <span className="text-xs font-semibold text-cyan-400 bg-cyan-500/10 px-2.5 py-1 rounded-lg border border-cyan-500/20">
            kWh Load
          </span>
        </div>

        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={monthlyData}>
              <defs>
                <linearGradient id="kwhColor" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4}/>
                  <stop offset="95%" stopColor="#38bdf8" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="month" stroke="#64748b" tick={{ fontSize: 12 }} />
              <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px', fontSize: '12px' }}
                itemStyle={{ color: '#38bdf8' }}
              />
              <Area type="monotone" dataKey="kwh" stroke="#38bdf8" strokeWidth={3} fillOpacity={1} fill="url(#kwhColor)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent Activity Table Feed */}
      <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm text-white">Recent Invoices & Payment Activity</h3>
            <p className="text-xs text-slate-400">Live transaction stream</p>
          </div>
          <button
            onClick={() => onNavigate('billing-payments')}
            className="text-xs font-semibold text-cyan-400 hover:underline flex items-center gap-1 cursor-pointer"
          >
            View All Billing & Payments <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/60 text-slate-400 uppercase font-semibold text-[10px] tracking-wider">
              <tr>
                <th className="px-4 py-3 rounded-l-xl">Invoice No</th>
                <th className="px-4 py-3">Customer Account</th>
                <th className="px-4 py-3">Consumed (kWh)</th>
                <th className="px-4 py-3">Amount</th>
                <th className="px-4 py-3 rounded-r-xl">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {invoices.slice(0, 5).map((inv) => (
                <tr key={inv.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-mono text-cyan-400 font-semibold">{inv.invoiceNumber}</td>
                  <td className="px-4 py-3 font-medium text-slate-200">{inv.customerName}</td>
                  <td className="px-4 py-3 font-mono">{formatKwh(inv.kwhConsumed)}</td>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
