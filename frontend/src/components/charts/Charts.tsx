import { useTheme } from '@/context/ThemeContext';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartOptions,
  type ChartData,
} from 'chart.js';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import { type ReactNode } from 'react';
import { getDirection } from '@/i18n/t';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

const PRIMARY = '#2563eb';
const EMERALD = '#10b981';
const ACCENT = '#06b6d4';
const WARNING = '#f59e0b';
const PURPLE = '#8b5cf6';

function useChartTheme() {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  return {
    grid: isDark ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.18)',
    ticks: isDark ? '#94a3b8' : '#64748b',
    legend: isDark ? '#cbd5e1' : '#475569',
    // Axis and tooltip figures in the same style as every other number on the
    // page (Western digits, comma thousands: utils/helpers.ts). Left unset,
    // Chart.js formats them in the BROWSER's language, so a German browser
    // printed "1.234" on the axis beside "1,234" in the card above it.
    locale: 'en-US',
    // Legend and tooltip laid out right to left in Arabic. The time axis
    // still runs left to right, as charts conventionally do in Arabic too.
    rtl: getDirection() === 'rtl',
  };
}

interface BaseProps {
  title?: string;
  height?: number;
  className?: string;
  action?: ReactNode;
}

function ChartCard({ title, height = 280, className, action, children }: BaseProps & { children: ReactNode }) {
  return (
    <div className={`card-surface shadow-card p-5 ${className ?? ''}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
          {action}
        </div>
      )}
      <div style={{ height }} className="w-full">
        {children}
      </div>
    </div>
  );
}

interface LineChartProps extends BaseProps {
  labels: string[];
  datasets: Array<{ label: string; data: (number | null)[]; color?: string; fill?: boolean; dashed?: boolean }>;
}

export function LineChart({ labels, datasets, title, height, className, action }: LineChartProps) {
  const t = useChartTheme();
  const data: ChartData<'line'> = {
    labels,
    datasets: datasets.map((d) => ({
      label: d.label,
      data: d.data,
      borderColor: d.color ?? PRIMARY,
      backgroundColor: d.fill ? `${d.color ?? PRIMARY}22` : 'transparent',
      fill: d.fill,
      tension: 0.4,
      borderWidth: 2,
      borderDash: d.dashed ? [6, 6] : [],
      pointRadius: 3,
      pointHoverRadius: 5,
      pointBackgroundColor: d.color ?? PRIMARY,
    })),
  };
  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    locale: t.locale,
    plugins: {
      legend: { display: datasets.length > 1, rtl: t.rtl, labels: { color: t.legend, usePointStyle: true, boxWidth: 8, font: { size: 11 } } },
      tooltip: { mode: 'index', intersect: false, rtl: t.rtl },
    },
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.ticks, font: { size: 11 } } },
      y: { grid: { color: t.grid }, ticks: { color: t.ticks, font: { size: 11 } }, beginAtZero: true },
    },
  };
  return (
    <ChartCard title={title} height={height} className={className} action={action}>
      <Line data={data} options={options} />
    </ChartCard>
  );
}

interface BarChartProps extends BaseProps {
  labels: string[];
  datasets: Array<{ label: string; data: number[]; color?: string; horizontal?: boolean }>;
}

export function BarChart({ labels, datasets, title, height, className, action }: BarChartProps) {
  const t = useChartTheme();
  const data: ChartData<'bar'> = {
    labels,
    datasets: datasets.map((d) => ({
      label: d.label,
      data: d.data,
      backgroundColor: d.color ?? PRIMARY,
      borderRadius: 6,
      barThickness: 'flex',
      maxBarThickness: 36,
    })),
  };
  const options: ChartOptions<'bar'> = {
    responsive: true,
    maintainAspectRatio: false,
    locale: t.locale,
    plugins: {
      legend: { display: datasets.length > 1, rtl: t.rtl, labels: { color: t.legend, usePointStyle: true, boxWidth: 8, font: { size: 11 } } },
      tooltip: { rtl: t.rtl },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: t.ticks, font: { size: 11 } } },
      y: { grid: { color: t.grid }, ticks: { color: t.ticks, font: { size: 11 } }, beginAtZero: true },
    },
  };
  return (
    <ChartCard title={title} height={height} className={className} action={action}>
      <Bar data={data} options={options} />
    </ChartCard>
  );
}

interface DoughnutChartProps extends BaseProps {
  labels: string[];
  data: number[];
  colors?: string[];
}

export function DoughnutChart({ labels, data, colors, title, height = 280, className, action }: DoughnutChartProps) {
  const t = useChartTheme();
  const palette = colors ?? [PRIMARY, EMERALD, ACCENT, WARNING, PURPLE];
  const chartData: ChartData<'doughnut'> = {
    labels,
    datasets: [{ data, backgroundColor: palette, borderWidth: 0, hoverOffset: 6 }],
  };
  const options: ChartOptions<'doughnut'> = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    locale: t.locale,
    plugins: {
      legend: { position: 'bottom', rtl: t.rtl, labels: { color: t.legend, usePointStyle: true, boxWidth: 8, padding: 12, font: { size: 11 } } },
      tooltip: { rtl: t.rtl },
    },
  };
  return (
    <ChartCard title={title} height={height} className={className} action={action}>
      <Doughnut data={chartData} options={options} />
    </ChartCard>
  );
}

export function AreaChart(props: LineChartProps) {
  const filled = props.datasets.map((d) => ({ ...d, fill: true }));
  return <LineChart {...props} datasets={filled} />;
}

export { PRIMARY, EMERALD, ACCENT, WARNING, PURPLE };
