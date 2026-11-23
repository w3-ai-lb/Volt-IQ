import React from 'react';
import { useData } from '../../context/DataContext';
import { useAuth, PERMISSIONS } from '../../context/AuthContext';
import { useSettings } from '../../context/SettingsContext';
import { formatCurrency, formatKwh } from '../../utils/invoiceGenerator';
import {
  BarChart3,
  Download,
  Lock,
  Zap,
  Activity,
  MapPin,
  DollarSign
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';

export default function ReportsAnalyticsView() {
  const { getDashboardStats, invoices, recalculateOutstandingInvoices } = useData();
  const { hasPermission } = useAuth();
  const { kwhPrice, setKwhPrice, t } = useSettings();

  const canViewReports = hasPermission(PERMISSIONS.VIEW_REPORTS);

  if (!canViewReports) {
    return (
      <div className="p-8 text-center space-y-4 max-w-md mx-auto my-12 bg-slate-900 border border-slate-800 rounded-3xl">
        <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mx-auto">
          <Lock className="w-6 h-6" />
        </div>
        <h3 className="font-bold text-lg text-white">Administrator Access Required</h3>
        <p className="text-xs text-slate-400">
          Reports and system-wide grid analytics are restricted to Administrators and Managers. Switch role using the top navbar menu to view.
        </p>
      </div>
    );
  }

  const stats = getDashboardStats();
  const estimatedGridRevenueValuation = stats.totalKwhConsumed * kwhPrice;

  const handlePriceChange = (val) => {
    const rate = parseFloat(val) || 0.18;
    setKwhPrice(rate);
    recalculateOutstandingInvoices(rate);
  };

  const detailedZoneData = [
    { zone: 'North Metro District', activeMeters: 42, kwh: 24500, peakLoadMw: 4.8, efficiency: '98.5%' },
    { zone: 'Central Office Zone', activeMeters: 28, kwh: 18900, peakLoadMw: 3.2, efficiency: '99.1%' },
    { zone: 'East Industrial Park', activeMeters: 19, kwh: 76000, peakLoadMw: 14.5, efficiency: '96.8%' },
    { zone: 'South Suburbs Sector', activeMeters: 35, kwh: 14200, peakLoadMw: 2.9, efficiency: '98.9%' }
  ];

  const paymentMethodData = [
    { name: 'Credit Card', value: 45, color: '#38bdf8' },
    { name: 'Bank Transfer', value: 35, color: '#34d399' },
    { name: 'Cash', value: 12, color: '#fbbf24' },
    { name: 'Check', value: 5, color: '#f43f5e' },
    { name: 'Mobile Money', value: 3, color: '#a855f7' }
  ];

  const exportCsv = () => {
    const csvContent = "data:text/csv;charset=utf-8," 
      + "Invoice Number,Customer Name,Account No,kWh Consumed,Total Amount,Status\n"
      + invoices.map(i => `${i.invoiceNumber},"${i.customerName}",${i.accountNo},${i.kwhConsumed},${i.totalAmount},${i.status}`).join("\n");
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `gridpower_utility_report_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6 pb-12">
      
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            {t('reports')} <BarChart3 className="w-5 h-5 text-cyan-400" />
          </h2>
          <p className="text-xs text-slate-400">
            Technical load distribution reports, regional sector performance, and payment gateway metrics.
          </p>
        </div>

        <button
          onClick={exportCsv}
          className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 font-semibold text-slate-200 text-xs transition-colors flex items-center gap-2 cursor-pointer self-start sm:self-auto"
        >
          <Download className="w-4 h-4 text-cyan-400" /> Export CSV Report
        </button>
      </div>

      {/* kWh Price Rate Configuration & Valuation Card */}
      <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <DollarSign className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-white">Electricity Rate per kWh & Grid Valuation</h3>
              <p className="text-xs text-slate-400">
                Updating this rate dynamically recalculates all outstanding (unpaid/overdue) bills without changing historical paid invoices.
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-1">
          
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-300">Set Rate ($ / kWh):</label>
            <div className="relative">
              <DollarSign className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={kwhPrice}
                onChange={(e) => handlePriceChange(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-800 border border-slate-700 text-xs text-slate-100 font-mono focus:border-amber-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="p-3 rounded-2xl bg-slate-800/40 border border-slate-700/60 space-y-1">
            <span className="text-[11px] text-slate-400 block">Total Grid Consumption:</span>
            <span className="font-bold text-cyan-400 text-base font-mono">{formatKwh(stats.totalKwhConsumed)}</span>
          </div>

          <div className="p-3 rounded-2xl bg-slate-800/40 border border-slate-700/60 space-y-1">
            <span className="text-[11px] text-slate-400 block">Estimated Tariff Grid Value:</span>
            <span className="font-extrabold text-emerald-400 text-base font-mono">
              {formatCurrency(estimatedGridRevenueValuation)}
            </span>
          </div>

        </div>
      </div>

      {/* Grid Load Header Banner */}
      <div className="p-5 rounded-3xl bg-slate-900/90 border border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
            <Zap className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-400">Total System Energy Distributed</span>
            <div className="text-2xl font-black text-cyan-400 font-mono">{formatKwh(stats.totalKwhConsumed)}</div>
          </div>
        </div>

        <div className="text-right hidden sm:block">
          <span className="text-xs text-slate-400 block">Total Active Meter Accounts</span>
          <span className="font-bold text-slate-200 text-sm">{stats.totalCustomers} Connected Units</span>
        </div>
      </div>

      {/* Specific District Zone Consumption Analytics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        <div className="lg:col-span-2 p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <MapPin className="w-4 h-4 text-cyan-400" /> Specific District Zone Consumption (kWh Load)
              </h3>
              <p className="text-xs text-slate-400">Detailed energy consumption metrics per regional utility zone</p>
            </div>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={detailedZoneData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="zone" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px', fontSize: '12px' }}
                />
                <Bar dataKey="kwh" fill="#38bdf8" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
          <div>
            <h3 className="font-bold text-sm text-white">Payment Channel Breakdown</h3>
            <p className="text-xs text-slate-400">Transaction distribution across gateways</p>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={paymentMethodData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {paymentMethodData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '12px', fontSize: '12px' }}
                />
                <Legend formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

      <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
        <h3 className="font-bold text-sm text-white flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-400" /> Detailed Regional Zone Technical Specifications
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-800/80 text-slate-400 uppercase font-semibold text-[10px]">
              <tr>
                <th className="px-4 py-3 rounded-l-xl">District Operating Zone</th>
                <th className="px-4 py-3">Active Meters</th>
                <th className="px-4 py-3">Total kWh Consumed</th>
                <th className="px-4 py-3">Peak Demand Load (MW)</th>
                <th className="px-4 py-3 rounded-r-xl">Grid Efficiency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {detailedZoneData.map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30">
                  <td className="px-4 py-3 font-bold text-slate-100">{item.zone}</td>
                  <td className="px-4 py-3 font-mono text-cyan-400">{item.activeMeters} Meters</td>
                  <td className="px-4 py-3 font-mono font-bold text-slate-200">{formatKwh(item.kwh)}</td>
                  <td className="px-4 py-3 font-mono text-amber-400">{item.peakLoadMw} MW</td>
                  <td className="px-4 py-3 font-bold text-emerald-400">{item.efficiency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}
