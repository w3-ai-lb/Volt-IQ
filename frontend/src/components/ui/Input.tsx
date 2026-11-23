import { type InputHTMLAttributes, type ReactNode, useState } from 'react';
import { Eye, EyeOff, Search } from 'lucide-react';
import { t } from '@/i18n/t';
import { classNames } from '@/utils/helpers';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  hint?: string;
}

export function Input({ label, error, leftIcon, rightIcon, hint, className, id, type = 'text', ...rest }: InputProps) {
  const inputId = id || rest.name || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && <span className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-400">{leftIcon}</span>}
        <input
          id={inputId}
          type={type}
          className={classNames(
            'input-base',
            leftIcon && 'ps-10',
            rightIcon && 'pe-10',
            error && 'border-error-500 focus:ring-error-500/40 focus:border-error-500',
            className,
          )}
          {...rest}
        />
        {rightIcon && <span className="absolute end-3 top-1/2 -translate-y-1/2 text-slate-400">{rightIcon}</span>}
      </div>
      {error ? (
        <p className="mt-1 text-xs text-error-600 dark:text-error-400">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
}

export function PasswordInput(props: Omit<InputProps, 'type' | 'rightIcon'>) {
  const [show, setShow] = useState(false);
  return (
    <Input
      {...props}
      type={show ? 'text' : 'password'}
      rightIcon={
        <button type="button" onClick={() => setShow((s) => !s)} className="hover:text-slate-600 dark:hover:text-slate-200" aria-label={show ? t('Hide password') : t('Show password')}>
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      }
    />
  );
}

export function SearchInput({ value, onChange, placeholder = t('Search...') }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="relative w-full max-w-sm">
      <Search className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input-base ps-10 h-10"
      />
    </div>
  );
}
