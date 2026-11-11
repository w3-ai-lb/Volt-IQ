import { type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { t } from '@/i18n/t';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function Breadcrumb({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label={t('Breadcrumb')} className="flex items-center gap-1.5 text-sm">
      {items.map((item, i) => {
        const last = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {item.href && !last ? (
              <Link to={item.href} className="text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400 transition">
                {item.label}
              </Link>
            ) : (
              <span className="font-medium text-slate-900 dark:text-slate-100">{item.label}</span>
            )}
            {!last && <ChevronRight className="w-3.5 h-3.5 text-slate-400 rtl:-scale-x-100" />}
          </span>
        );
      })}
    </nav>
  );
}

export function PageHeader({ title, description, breadcrumb, action }: { title: string; description?: string; breadcrumb?: BreadcrumbItem[]; action?: ReactNode }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-6">
      <div>
        {breadcrumb && <div className="mb-2"><Breadcrumb items={breadcrumb} /></div>}
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{title}</h1>
        {description && <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{description}</p>}
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}
