import { classNames } from '@/utils/helpers';

export function Skeleton({ className }: { className?: string }) {
  return <div className={classNames('animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800', className)} />;
}

export function SkeletonCard() {
  return (
    <div className="card-surface shadow-card rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="h-10 w-10 rounded-xl" />
        <Skeleton className="h-4 w-16" />
      </div>
      <Skeleton className="h-8 w-32" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

export function SkeletonRow({ cols = 5 }: { cols?: number }) {
  return (
    <div className="flex gap-4 px-4 py-3.5">
      {Array.from({ length: cols }).map((_, i) => (
        <Skeleton key={i} className="h-4 flex-1" />
      ))}
    </div>
  );
}
