import { useState } from 'react';
import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LayoutDashboard, Zap, FileText, CreditCard, Lightbulb, Bell, MessageSquare,
  User, Settings, LogOut, Menu, X, Moon, Sun, ChevronDown, Banknote, BarChart3, TrendingDown,
  ClipboardList, Users,
  Zap as LogoMark,
} from 'lucide-react';
import { useTheme } from '@/context/ThemeContext';
import { useAuth } from '@/context/AuthContext';
import { GlobalSearch } from '@/components/ui/GlobalSearch';
import { classNames } from '@/utils/helpers';
import { slideFrom, t } from '@/i18n/t';

/**
 * `label` is stored in English and translated where it is rendered, not here.
 * These arrays are module-level constants, evaluated once when the module is
 * first imported, so calling t() inside them would freeze whatever language
 * happened to be active at that moment and never change again.
 */
interface NavItem {
  label: string;
  to: string;
  icon: typeof LayoutDashboard;
}

const customerNav: NavItem[] = [
  { label: 'Dashboard', to: '/app/dashboard', icon: LayoutDashboard },
  { label: 'Consumption', to: '/app/consumption', icon: Zap },
  { label: 'Bills', to: '/app/bills', icon: FileText },
  { label: 'Payments', to: '/app/payments', icon: CreditCard },
  { label: 'Recommendations', to: '/app/recommendations', icon: Lightbulb },
  { label: 'Alerts', to: '/app/alerts', icon: Bell },
  { label: 'Chatbot', to: '/app/chatbot', icon: MessageSquare },
  { label: 'Profile', to: '/app/profile', icon: User },
  { label: 'Settings', to: '/app/settings', icon: Settings },
];

const adminNav: NavItem[] = [
  { label: 'Dashboard', to: '/admin/dashboard', icon: LayoutDashboard },
  { label: 'Energy Loss', to: '/admin/loss', icon: TrendingDown },
  { label: 'Accounts to visit', to: '/admin/visits', icon: ClipboardList },
  // The CRM module (customers, staff, billing, payments), see src/modules/crm.
  { label: 'Utility CRM', to: '/crm', icon: Users },
  { label: 'Customers', to: '/admin/customers', icon: User },
  { label: 'Analytics', to: '/admin/analytics', icon: BarChart3 },
  { label: 'Revenue', to: '/admin/revenue', icon: Banknote },
  { label: 'Forecast', to: '/admin/forecast', icon: Zap },
  { label: 'Segmentation', to: '/admin/segmentation', icon: User },
  { label: 'Anomalies', to: '/admin/anomalies', icon: Bell },
  { label: 'Reports', to: '/admin/reports', icon: FileText },
  { label: 'Profile', to: '/admin/profile', icon: User },
  { label: 'Settings', to: '/admin/settings', icon: Settings },
];

function SidebarContent({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const { pathname } = useLocation();
  return (
    <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto scrollbar-thin">
      {items.map((item) => {
        const active = pathname === item.to || pathname.startsWith(item.to + '/');
        const Icon = item.icon;
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={classNames(
              'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all group',
              active
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800',
            )}
          >
            <Icon className={classNames('w-5 h-5 shrink-0', active ? 'text-white' : 'text-slate-400 group-hover:text-slate-600 dark:group-hover:text-slate-200')} />
            <span>{t(item.label)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function DashboardLayout({ role }: { role: 'customer' | 'admin' }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const nav = role === 'admin' ? adminNav : customerNav;
  const [profileOpen, setProfileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const homeLink = role === 'admin' ? '/admin/dashboard' : '/app/dashboard';

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 shrink-0 flex-col bg-white dark:bg-slate-900 border-e border-slate-200 dark:border-slate-800 sticky top-0 h-screen">
        <Link to={homeLink} className="flex items-center gap-2.5 px-5 h-16 border-b border-slate-200 dark:border-slate-800">
          <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow">
            <LogoMark className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-slate-900 dark:text-slate-100">{t('VoltIQ')}</span>
        </Link>
        <SidebarContent items={nav} />
        <div className="p-3 border-t border-slate-200 dark:border-slate-800">
          {/* The label is translated, so tests cannot find this button by its
              text once the interface is in another language. */}
          <button
            id="logout"
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-error-50 dark:hover:bg-error-500/10 hover:text-error-600 dark:hover:text-error-400 transition"
          >
            <LogOut className="w-5 h-5" />{t('Logout')}
          </button>
        </div>
      </aside>

      {/* Mobile sidebar */}
      <AnimatePresence>
        {mobileOpen && (
          <div className="lg:hidden fixed inset-0 z-50">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
            <motion.aside
              initial={{ x: slideFrom(-280) }}
              animate={{ x: 0 }}
              exit={{ x: slideFrom(-280) }}
              transition={{ type: 'spring', damping: 28, stiffness: 260 }}
              className="absolute start-0 top-0 bottom-0 w-64 bg-white dark:bg-slate-900 flex flex-col"
            >
              <div className="flex items-center justify-between px-5 h-16 border-b border-slate-200 dark:border-slate-800">
                <Link to={homeLink} className="flex items-center gap-2.5">
                  <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center">
                    <LogoMark className="w-5 h-5 text-white" />
                  </div>
                  <span className="font-bold text-slate-900 dark:text-slate-100">{t('VoltIQ')}</span>
                </Link>
                <button onClick={() => setMobileOpen(false)} className="text-slate-400" aria-label={t('Close menu')}><X className="w-5 h-5" /></button>
              </div>
              <SidebarContent items={nav} onNavigate={() => setMobileOpen(false)} />
              <div className="p-3 border-t border-slate-200 dark:border-slate-800">
                <button onClick={handleLogout} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-error-50 dark:hover:bg-error-500/10 transition">
                  <LogOut className="w-5 h-5" />{t('Logout')}
                </button>
              </div>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-b border-slate-200 dark:border-slate-800 sticky top-0 z-40 flex items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <button onClick={() => setMobileOpen(true)} className="lg:hidden text-slate-500" aria-label={t('Open menu')}><Menu className="w-5 h-5" /></button>
            <div className="hidden md:block">
              <GlobalSearch role={role} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={toggleTheme} className="p-2.5 rounded-xl text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition" aria-label={t('Toggle theme')}>
              {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>
            <div className="relative">
              <button onClick={() => setProfileOpen((o) => !o)} className="flex items-center gap-2 ps-2 pe-3 py-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition">
                <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center text-white text-xs font-bold">
                  {user?.name?.charAt(0) ?? 'U'}
                </div>
                <div className="hidden sm:block text-start">
                  <p className="text-xs font-semibold text-slate-900 dark:text-slate-100 leading-tight">{user?.name ?? t('User')}</p>
                  {/* The role is an enum with two values, so it is interface
                      text rather than data and is translated. A customer's own
                      name, on the line above, is not. */}
                  <p className="text-[10px] text-slate-400">{t(user?.role === 'admin' ? 'Administrator' : 'Customer')}</p>
                </div>
                <ChevronDown className="w-4 h-4 text-slate-400" />
              </button>
              <AnimatePresence>
                {profileOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setProfileOpen(false)} />
                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      className="absolute end-0 mt-2 w-56 glass-strong rounded-xl shadow-card-hover p-2 z-20"
                    >
                      <Link to={role === 'admin' ? '/admin/profile' : '/app/profile'} onClick={() => setProfileOpen(false)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
                        <User className="w-4 h-4" />{t('Profile')}
                      </Link>
                      <Link to={role === 'admin' ? '/admin/settings' : '/app/settings'} onClick={() => setProfileOpen(false)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition">
                        <Settings className="w-4 h-4" />{t('Settings')}
                      </Link>
                      <div className="h-px bg-slate-200 dark:bg-slate-700 my-1" />
                      <button onClick={handleLogout} className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-error-600 dark:text-error-400 hover:bg-error-50 dark:hover:bg-error-500/10 transition">
                        <LogOut className="w-4 h-4" />{t('Logout')}
                      </button>
                    </motion.div>
                  </>
                )}
              </AnimatePresence>
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
