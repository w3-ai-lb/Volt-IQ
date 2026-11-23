import React from 'react';
import { useAuth, PERMISSIONS } from '../../context/AuthContext';
import { useSettings } from '../../context/SettingsContext';
import {
  LayoutDashboard,
  Users,
  UserCheck,
  CreditCard,
  BarChart3,
  Sliders,
  Lock
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab }) {
  const { hasPermission } = useAuth();
  const { t } = useSettings();

  const navItems = [
    {
      id: 'dashboard',
      label: t('dashboard'),
      icon: LayoutDashboard,
      permission: PERMISSIONS.VIEW_DASHBOARD
    },
    {
      id: 'customers',
      label: t('customerManagement'),
      icon: Users,
      permission: PERMISSIONS.VIEW_CUSTOMERS
    },
    {
      id: 'employees',
      label: t('employeeManagement'),
      icon: UserCheck,
      permission: PERMISSIONS.MANAGE_EMPLOYEES
    },
    {
      id: 'billing-payments',
      label: t('billingPayments'),
      icon: CreditCard,
      permission: PERMISSIONS.MANAGE_BILLING_PAYMENTS
    },
    {
      id: 'reports',
      label: t('reports'),
      icon: BarChart3,
      permission: PERMISSIONS.VIEW_REPORTS
    },
    {
      id: 'settings',
      label: t('settings'),
      icon: Sliders,
      permission: PERMISSIONS.VIEW_DASHBOARD // Open for all users
    }
  ];

  return (
    <aside className="w-64 bg-slate-900/90 border-r border-slate-800 shrink-0 flex flex-col justify-between hidden md:flex h-[calc(100vh-61px)] sticky top-[61px]">
      <div className="p-4 space-y-4">
        
        {/* Main Navigation Menu */}
        <nav className="space-y-1.5">
          <div className="px-3 pb-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            Navigation Menu
          </div>
          {navItems.map((item) => {
            const allowed = hasPermission(item.permission);
            const isActive = activeTab === item.id;
            const Icon = item.icon;

            return (
              <button
                key={item.id}
                onClick={() => allowed && setActiveTab(item.id)}
                disabled={!allowed}
                className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl font-medium text-xs transition-all duration-150 text-left ${
                  isActive
                    ? 'bg-gradient-to-r from-cyan-500/20 to-blue-600/20 text-cyan-300 border border-cyan-500/40 font-semibold shadow-md shadow-cyan-950/40'
                    : allowed
                    ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    : 'text-slate-600 cursor-not-allowed opacity-60'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : allowed ? 'text-slate-400' : 'text-slate-600'}`} />
                <span className="flex-1 truncate">{item.label}</span>
                
                {!allowed && (
                  <span title="Administrator Permission Required" className="p-1 rounded bg-slate-800 text-slate-500">
                    <Lock className="w-3 h-3 text-amber-500/70" />
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
