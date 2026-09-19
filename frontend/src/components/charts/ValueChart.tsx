import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartOptions,
} from 'chart.js';
import { useMemo } from 'react';
import { Line } from 'react-chartjs-2';

import type { Snapshot } from '@/api/types';
import { EmptyState } from '@/components/ui/EmptyState';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

const MONTHS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
const LINE = '#ffcb05';
const GRID = 'rgba(255,255,255,0.05)';
const TICK = '#888';

const wholeEuros = (value: number) => `€${Math.round(value).toLocaleString('es-ES')}`;

/** `2026-09-19` → its parts, with the month as a Spanish abbreviation. */
function dateParts(isoDate: string) {
  const [year = '', month = '1', day = ''] = isoDate.split('-');
  return { year, month: MONTHS[Number(month) - 1] ?? '', day };
}

/** Collection value over time, one point per snapshot. */
export function ValueChart({ snapshots }: { snapshots: Snapshot[] }) {
  const data = useMemo(
    () => ({
      labels: snapshots.map((snapshot) => snapshot.captured_on),
      datasets: [
        {
          data: snapshots.map((snapshot) => snapshot.value_eur),
          borderColor: LINE,
          backgroundColor: 'rgba(255,203,5,0.15)',
          pointBackgroundColor: LINE,
          pointRadius: 3,
          tension: 0.3,
          fill: true,
        },
      ],
    }),
    [snapshots],
  );

  const options = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => {
              const { day, month } = dateParts(items[0]?.label ?? '');
              return `${day} ${month}`;
            },
            label: (item) => wholeEuros(item.parsed.y ?? 0),
          },
        },
      },
      scales: {
        x: {
          grid: { color: GRID },
          ticks: {
            color: TICK,
            callback: (_value, index) => {
              const { month, year } = dateParts(snapshots[index]?.captured_on ?? '');
              return `${month} ${year}`;
            },
          },
        },
        y: {
          grid: { color: GRID },
          ticks: { color: TICK, callback: (value) => wholeEuros(Number(value)) },
        },
      },
    }),
    [snapshots],
  );

  if (!snapshots.length) return <EmptyState>Sin histórico todavía.</EmptyState>;

  return (
    <div className="h-50">
      <Line data={data} options={options} />
    </div>
  );
}
