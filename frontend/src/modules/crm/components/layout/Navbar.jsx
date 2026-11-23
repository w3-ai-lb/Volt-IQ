import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth, ROLES } from '../../context/AuthContext';
import { useData } from '../../context/DataContext';
import { useSettings } from '../../context/SettingsContext';
import {
  Zap,
  Bell,
  ChevronDown,
  LogOut,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  CheckCheck
} from 'lucide-react';

export default function Navbar() {
  const { currentUser, activeRole, logout } = useAuth();
  const { notifications, hasUnreadNotifications, markNotificationsAsRead } = useData();
  const { t } = useSettings();

  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);

  const handleToggleNotifications = () => {
    setShowNotifications(!showNotifications);
  };

  const getRoleBadgeColor = (role) => {
    switch (role) {
      case ROLES.ADMIN:
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case ROLES.MANAGER:
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case ROLES.OFFICE_EMPLOYEE:
        return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30';
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
    }
  };

  return (
    <header className="sticky top-0 z-30 bg-slate-900/80 backdrop-blur-md border-b border-slate-800 px-4 lg:px-8 py-3">
      <div className="flex items-center justify-between gap-4">
        
        {/* Brand & Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center shadow-lg shadow-cyan-500/25">
            <Zap className="w-6 h-6 text-white animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-lg tracking-tight text-white">VoltIQ</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-semibold">
                CRM
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">Customers, staff, billing and payments</p>
          </div>
        </div>

        {/* Right Section: Role Switcher, Notifications & Logout */}
        <div className="flex items-center gap-3">
          
          {/* Notifications Dropdown */}
          <div className="relative">
            <button
              onClick={handleToggleNotifications}
              className={`p-2.5 rounded-xl border transition-all relative cursor-pointer ${
                hasUnreadNotifications
                  ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-300 shadow-md shadow-cyan-500/20'
                  : 'bg-slate-800/80 border-slate-700 text-slate-300 hover:text-white hover:border-slate-600'
              }`}
              title={t('notifications')}
            >
              <Bell className={`w-5 h-5 ${hasUnreadNotifications ? 'text-cyan-400 animate-pulse' : ''}`} />
              
              {/* Flickering Ping Indicator Dot */}
              {hasUnreadNotifications && (
                <>
                  <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
                  <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 rounded-full bg-cyan-400" />
                </>
              )}
            </button>

            {showNotifications && (
              <div className="absolute right-0 mt-2 w-80 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-4 z-50 animate-in fade-in slide-in-from-top-2">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                  <h4 className="font-bold text-sm text-white flex items-center gap-2">
                    <Bell className="w-4 h-4 text-cyan-400" /> {t('notifications')}
                  </h4>
                  
                  {/* Mark All as Read Option Button */}
                  {hasUnreadNotifications && (
                    <button
                      onClick={markNotificationsAsRead}
                      className="text-[11px] font-bold text-cyan-400 hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <CheckCheck className="w-3.5 h-3.5" /> {t('markAllRead')}
                    </button>
                  )}
                </div>

                <div className="max-h-64 overflow-y-auto mt-2 space-y-2">
                  {notifications.length > 0 ? (
                    notifications.map(item => (
                      <div key={item.id} className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/50 text-xs">
                        <div className="flex items-start gap-2">
                          {item.type === 'warning' ? (
                            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                          ) : (
                            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                          )}
                          <div>
                            <p className="text-slate-200">{item.text}</p>
                            <span className="text-[10px] text-slate-500 mt-1 block">{item.time}</span>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-500 text-center py-4">{t('noNotifications')}</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Role Switcher */}
          <div className="relative">
            <button
              onClick={() => setShowRoleDropdown(!showRoleDropdown)}
              className="flex items-center gap-3 p-1.5 pr-3 rounded-2xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/80 transition-all cursor-pointer"
            >
              <img
                src={currentUser?.avatar}
                alt={currentUser?.name}
                className="w-9 h-9 rounded-xl object-cover border border-slate-600"
              />
              <div className="text-left hidden sm:block">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold text-slate-200">{currentUser?.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.2 rounded border font-semibold ${getRoleBadgeColor(activeRole)}`}>
                    {activeRole === ROLES.ADMIN ? 'Admin' : activeRole === ROLES.MANAGER ? 'Manager' : 'Employee'}
                  </span>
                </div>
                <span className="text-[11px] text-slate-400 block truncate max-w-[130px]">
                  {currentUser?.roleTitle}
                </span>
              </div>
              <ChevronDown className="w-4 h-4 text-slate-400" />
            </button>

            {/* Account menu */}
            {showRoleDropdown && (
              <div className="absolute right-0 mt-2 w-64 bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-3 z-50 text-xs">
                <div className="px-2 py-1.5 border-b border-slate-800 mb-2">
                  <span className="text-[11px] font-semibold text-cyan-400 uppercase tracking-wider flex items-center gap-1">
                    <Sliders className="w-3 h-3" /> Signed in
                  </span>
                  <span className="block text-slate-400 truncate mt-1">{currentUser?.email}</span>
                </div>
                {currentUser?.accountRole === 'admin' && (
                  <Link
                    to="/admin/dashboard"
                    className="block w-full p-2 rounded-xl text-left text-slate-200 hover:bg-slate-800"
                    onClick={() => setShowRoleDropdown(false)}
                  >
                    Open Energy Analytics
                  </Link>
                )}
                <button
                  onClick={logout}
                  className="block w-full p-2 rounded-xl text-left text-red-400 hover:bg-slate-800 cursor-pointer"
                >
                  {t('signOut')}
                </button>
              </div>
            )}
          </div>

          {/* Logout Button */}
          <button
            onClick={logout}
            className="p-2.5 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-400 hover:text-red-400 hover:border-red-500/30 transition-colors cursor-pointer"
            title={t('signOut')}
          >
            <LogOut className="w-5 h-5" />
          </button>

        </div>
      </div>
    </header>
  );
}
