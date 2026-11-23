import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Zap, TrendingUp, Brain, ShieldCheck } from 'lucide-react';
import { t } from '@/i18n/t';

export function AuthLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-white dark:bg-slate-950">
      {/* Left brand panel */}
      <div className="hidden lg:flex relative flex-col justify-between p-12 bg-gradient-primary overflow-hidden">
        <div className="absolute inset-0 bg-grid opacity-20" />
        <div className="absolute -top-20 -right-20 w-80 h-80 bg-white/10 rounded-full blur-3xl" />
        <div className="relative">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center"><Zap className="w-5 h-5 text-white" /></div>
            <span className="font-bold text-lg text-white">{t('VoltIQ')}</span>
          </Link>
        </div>
        <div className="relative space-y-8">
          <h2 className="text-3xl font-bold text-white leading-tight">{t('The intelligent way to manage energy.')}</h2>
          <div className="space-y-4">
            {[
              // The first two were invented percentages, and the admin dashboard
              // shows the forecast's own backtest (a diagnostic, not a validated
              // accuracy), so "94%" sat on the sign-in page contradicting the
              // screen behind it. The third claimed a compliance posture nobody
              // has audited. What is claimed now is what the code does.
              { icon: Brain, text: 'Forecasts checked against what actually happened' },
              { icon: TrendingUp, text: 'The busiest hour, measured at the generator' },
              { icon: ShieldCheck, text: 'Role-based access, passwords never stored in the clear' },
            ].map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.text} className="flex items-center gap-3 text-white/90">
                  <div className="w-10 h-10 rounded-xl bg-white/15 backdrop-blur flex items-center justify-center"><Icon className="w-5 h-5" /></div>
                  <p className="text-sm font-medium">{t(f.text)}</p>
                </div>
              );
            })}
          </div>
        </div>
        <p className="relative text-sm text-white/70">
          <span className="ltr-num">© {new Date().getFullYear()} VoltIQ.</span> {t('Powering smarter grids.')}
        </p>
      </div>

      {/* Right form panel */}
      <div className="flex flex-col justify-center px-6 sm:px-12 py-12">
        <div className="w-full max-w-sm mx-auto">
          <Link to="/" className="lg:hidden flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center"><Zap className="w-5 h-5 text-white" /></div>
            <span className="font-bold text-lg text-slate-900 dark:text-slate-100">{t('VoltIQ')}</span>
          </Link>
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{title}</h1>
            <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
            <div className="mt-8">{children}</div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
