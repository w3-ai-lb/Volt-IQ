import { type ReactNode } from 'react';
import { classNames } from '@/utils/helpers';

type Tone = 'primary' | 'success' | 'warning' | 'error' | 'info' | 'neutral';

const TONES: Record<Tone, string> = {
  primary: 'bg-primary-50 text-primary-700 dark:bg-primary-500/15 dark:text-primary-300',
  success: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  warning: 'bg-warning-50 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300',
  error: 'bg-error-50 text-error-700 dark:bg-error-500/15 dark:text-error-300',
  info: 'bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300',
  neutral: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
};

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={classNames(
        'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function statusTone(status: string): Tone {
  const s = status.toLowerCase();
  if (s === 'paid' || s === 'completed' || s === 'active') return 'success';
  if (s === 'pending' || s === 'partial') return 'warning';
  if (s === 'overdue' || s === 'suspended' || s === 'inactive') return 'error';
  return 'neutral';
}
