import { type ReactNode, useState } from 'react';
import { classNames } from '@/utils/helpers';

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({ tabs, defaultTab }: { tabs: Tab[]; defaultTab?: string }) {
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id);
  const current = tabs.find((t) => t.id === active);
  return (
    <div>
      <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl w-fit">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActive(t.id)}
            className={classNames(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              active === t.id
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">{current?.content}</div>
    </div>
  );
}
