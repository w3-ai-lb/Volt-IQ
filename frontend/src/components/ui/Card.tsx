import { type HTMLAttributes, type ReactNode } from 'react';
import { classNames } from '@/utils/helpers';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  glass?: boolean;
  hover?: boolean;
}

export function Card({ children, glass = false, hover = false, className, ...rest }: CardProps) {
  return (
    <div
      className={classNames(
        glass ? 'glass' : 'card-surface',
        'shadow-card rounded-2xl',
        hover && 'transition-all duration-300 hover:shadow-card-hover hover:-translate-y-0.5',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={classNames('p-5 border-b border-slate-100 dark:border-slate-800', className)}>{children}</div>;
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={classNames('p-5', className)}>{children}</div>;
}

export function CardTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={classNames('text-base font-semibold text-slate-900 dark:text-slate-100', className)}>{children}</h3>;
}
