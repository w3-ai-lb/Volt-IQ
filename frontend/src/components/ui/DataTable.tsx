import { type ReactNode } from 'react';
import { classNames } from '@/utils/helpers';

interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
  /**
   * Marks one row as the one the user was sent here to find, so arriving from
   * the header search lands on a highlighted row instead of an anonymous list.
   */
  highlightRow?: (row: T) => boolean;
}

export function DataTable<T>({ columns, data, rowKey, empty, onRowClick, highlightRow }: DataTableProps<T>) {
  if (data.length === 0 && empty) {
    return <div className="py-12">{empty}</div>;
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            {columns.map((c) => (
              <th
                key={c.key}
                className={classNames('text-start font-semibold text-slate-500 dark:text-slate-400 px-4 py-3 whitespace-nowrap', c.className)}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={() => onRowClick?.(row)}
              className={classNames(
                'border-b border-slate-100 dark:border-slate-800/60 transition-colors',
                onRowClick && 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40',
                highlightRow?.(row) && 'bg-primary-50 dark:bg-primary-500/10 ring-1 ring-inset ring-primary-500/40',
              )}
            >
              {columns.map((c) => (
                <td key={c.key} className={classNames('px-4 py-3.5 text-slate-700 dark:text-slate-300', c.className)}>
                  {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
