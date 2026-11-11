import React from 'react';
import { useSettings } from '../../context/SettingsContext';
import { useData } from '../../context/DataContext';
import {
  Sliders,
  Sun,
  Moon,
  Globe,
  DollarSign,
  CheckCircle2
} from 'lucide-react';

export default function SettingsView() {
  const { theme, setTheme, language, setLanguage, kwhPrice, setKwhPrice, t } = useSettings();
  const { recalculateOutstandingInvoices } = useData();

  const handlePriceChange = (val) => {
    const rate = parseFloat(val) || 0.18;
    setKwhPrice(rate);
    recalculateOutstandingInvoices(rate);
  };

  return (
    <div className="space-y-6 pb-12">
      
      {/* Header */}
      <div>
        <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
          {t('settings')} <Sliders className="w-5 h-5 text-cyan-400" />
        </h2>
        <p className="text-xs text-slate-400">
          {t('systemSettings')}
        </p>
      </div>

      {/* Settings Grid Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Theme Settings Card */}
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <div className="p-2.5 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              {theme === 'dark' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
            </div>
            <div>
              <h3 className="font-bold text-sm text-white">{t('theme')}</h3>
              <p className="text-xs text-slate-400">Switch between dark glassmorphism and modern light UI</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={() => setTheme('dark')}
              className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between h-28 cursor-pointer ${
                theme === 'dark'
                  ? 'bg-cyan-500/15 border-cyan-500 text-cyan-300 ring-2 ring-cyan-500/30'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <Moon className="w-5 h-5" />
                {theme === 'dark' && <CheckCircle2 className="w-4 h-4 text-cyan-400" />}
              </div>
              <span className="font-bold text-xs">{t('darkMode')}</span>
            </button>

            <button
              onClick={() => setTheme('light')}
              className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between h-28 cursor-pointer ${
                theme === 'light'
                  ? 'bg-cyan-500/15 border-cyan-500 text-cyan-300 ring-2 ring-cyan-500/30'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <Sun className="w-5 h-5 text-amber-400" />
                {theme === 'light' && <CheckCircle2 className="w-4 h-4 text-cyan-400" />}
              </div>
              <span className="font-bold text-xs">{t('lightMode')}</span>
            </button>
          </div>
        </div>

        {/* Language Settings Card */}
        <div className="p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <div className="p-2.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Globe className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-white">{t('language')}</h3>
              <p className="text-xs text-slate-400">Select system interface language (English & Arabic RTL)</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={() => setLanguage('en')}
              className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between h-28 cursor-pointer ${
                language === 'en'
                  ? 'bg-emerald-500/15 border-emerald-500 text-emerald-300 ring-2 ring-emerald-500/30'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm">EN</span>
                {language === 'en' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
              </div>
              <span className="font-bold text-xs">{t('english')}</span>
            </button>

            <button
              onClick={() => setLanguage('ar')}
              className={`p-4 rounded-2xl border text-right transition-all flex flex-col justify-between h-28 cursor-pointer ${
                language === 'ar'
                  ? 'bg-emerald-500/15 border-emerald-500 text-emerald-300 ring-2 ring-emerald-500/30'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm">العربية</span>
                {language === 'ar' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
              </div>
              <span className="font-bold text-xs">{t('arabic')}</span>
            </button>
          </div>
        </div>

        {/* Global Tariff kWh Price Option Card */}
        <div className="md:col-span-2 p-6 rounded-3xl bg-slate-900/90 border border-slate-800 shadow-xl space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <div className="p-2.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
              <DollarSign className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-white">{t('pricePerKwh')}</h3>
              <p className="text-xs text-slate-400">
                Updating this rate dynamically recalculates all outstanding (unpaid/overdue) bills without changing historical paid invoices.
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-4 pt-2">
            <div className="relative flex-1 w-full">
              <DollarSign className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
              <input
                type="number"
                step="0.01"
                min="0.01"
                value={kwhPrice}
                onChange={(e) => handlePriceChange(e.target.value)}
                className="w-full pl-9 pr-12 py-3 rounded-2xl bg-slate-800/80 border border-slate-700 text-slate-100 font-mono text-sm focus:border-amber-500 focus:outline-none"
              />
              <span className="absolute right-3 top-3.5 text-xs text-slate-400 font-bold">/ kWh</span>
            </div>

            <div className="p-3 rounded-2xl bg-slate-800/50 border border-slate-700 text-xs text-slate-300 w-full sm:w-auto">
              <span className="text-slate-400 block text-[11px]">Active Tariff Rate:</span>
              <span className="font-bold text-amber-400 text-sm font-mono">${kwhPrice.toFixed(2)} USD per kWh</span>
            </div>
          </div>
        </div>

      </div>

    </div>
  );
}
