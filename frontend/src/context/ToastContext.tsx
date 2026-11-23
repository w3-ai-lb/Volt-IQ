import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from 'lucide-react';
import { t } from '@/i18n/t';

type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, 'id'>) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const STYLES: Record<ToastType, string> = {
  success: 'text-emerald-500',
  error: 'text-error-500',
  info: 'text-primary-500',
  warning: 'text-warning-500',
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((next: Omit<Toast, 'id'>) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...next, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 4000);
  }, []);

  const remove = (id: string) => setToasts((prev) => prev.filter((x) => x.id !== id));

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed top-4 end-4 z-[100] flex flex-col gap-2 w-full max-w-sm pointer-events-none">
        <AnimatePresence>
          {/* Named `item`, not `t`: a parameter called t would shadow the
              translation function imported at the top of this file. */}
          {toasts.map((item) => {
            const Icon = ICONS[item.type];
            return (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: 40, scale: 0.95 }}
                animate={{ opacity: 1, x: 0, scale: 1 }}
                exit={{ opacity: 0, x: 40, scale: 0.95 }}
                transition={{ duration: 0.2 }}
                className="glass-strong shadow-card-hover rounded-xl p-4 flex items-start gap-3 pointer-events-auto"
              >
                <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${STYLES[item.type]}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.title}</p>
                  {item.message && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{item.message}</p>}
                </div>
                <button
                  onClick={() => remove(item.id)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition"
                  aria-label={t('Dismiss')}
                >
                  <X className="w-4 h-4" />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx.toast;
}
