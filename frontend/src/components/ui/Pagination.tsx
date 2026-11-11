import { ChevronLeft, ChevronRight } from 'lucide-react';
import { classNames } from '@/utils/helpers';
import { t } from '@/i18n/t';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  const visible = pages.filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 1);

  return (
    <div className="flex items-center justify-between mt-4">
      <p className="text-xs text-slate-500 dark:text-slate-400">
        {t('Page {page} of {total}').replace('{page}', String(page)).replace('{total}', String(totalPages))}
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
          aria-label={t('Previous page')}
        >
          <ChevronLeft className="w-4 h-4 rtl:-scale-x-100" />
        </button>
        {visible.map((p, i) => {
          const prev = visible[i - 1];
          const showGap = prev && p - prev > 1;
          return (
            <span key={p} className="flex items-center">
              {showGap && <span className="px-1 text-slate-400">…</span>}
              <button
                onClick={() => onPageChange(p)}
                className={classNames(
                  'min-w-9 h-9 px-3 rounded-lg text-sm font-medium transition',
                  p === page
                    ? 'bg-primary-600 text-white'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800',
                )}
              >
                {p}
              </button>
            </span>
          );
        })}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
          className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition"
          aria-label={t('Next page')}
        >
          <ChevronRight className="w-4 h-4 rtl:-scale-x-100" />
        </button>
      </div>
    </div>
  );
}
