import { Component, Input, OnDestroy, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import { Chart, registerables } from 'chart.js';
import { KpiHistoryEntry } from '../../../core/services/bus-client.service';

Chart.register(...registerables);

export type ChartKpiId = 'TSP' | 'TPCP' | 'MTRP' | 'IOG' | 'TR' | 'TI' | 'TBR';

const KPI_META: Record<ChartKpiId, { label: string; unit: string; color: string; threshold?: number }> = {
  TSP:  { label: 'Tasa de Satisfacción de Pedidos', unit: '%', color: '#06b6d4', threshold: 95 },
  TPCP: { label: 'Tiempo Promedio de Ciclo por Pedido', unit: 'min', color: '#a78bfa' },
  MTRP: { label: 'Movimientos Totales de Robots/Pedido', unit: '', color: '#f59e0b' },
  IOG:  { label: 'Índice de Ocupación de la Grilla', unit: '%', color: '#34d399', threshold: 90 },
  TR:   { label: 'Throughput de Recuperación', unit: 'cajas/min', color: '#f472b6' },
  TI:   { label: 'Throughput de Ingreso', unit: 'cajas/min', color: '#fb923c' },
  TBR:  { label: 'Tiempo de Bloqueo de Robots', unit: '%', color: '#ef4444', threshold: 10 },
};

@Component({
  selector: 'app-kpi-chart',
  templateUrl: './kpi-chart.component.html',
  styleUrls: ['./kpi-chart.component.scss'],
  imports: [],
})
export class KpiChartComponent implements AfterViewInit, OnDestroy {
  @Input() set kpiId(v: ChartKpiId | null) {
    this._kpiId = v;
    if (this._kpiId) this.rebuild();
  }
  get kpiId(): ChartKpiId | null { return this._kpiId; }
  private _kpiId: ChartKpiId | null = null;

  @Input() set history(v: KpiHistoryEntry[]) {
    this._history = v;
    if (this._kpiId) this.rebuild();
  }
  get history(): KpiHistoryEntry[] { return this._history; }
  private _history: KpiHistoryEntry[] = [];

  @ViewChild('canvas') canvas!: ElementRef<HTMLCanvasElement>;

  private chart?: Chart;

  get meta() { return this._kpiId ? KPI_META[this._kpiId] : null; }

  ngAfterViewInit(): void {
    if (this._kpiId) this.rebuild();
  }

  private rebuild(): void {
    this.chart?.destroy();
    if (!this._kpiId || !this.canvas) return;
    const id = this._kpiId;
    const m = KPI_META[id];
    const data = this._history.map(h => ({ tick: h.tick, value: h[id] }));
    if (data.length < 2) return;

    this.chart = new Chart(this.canvas.nativeElement, {
      type: 'line',
      data: {
        labels: data.map(d => d.tick),
        datasets: [
          {
            label: m.label,
            data: data.map(d => d.value),
            borderColor: m.color,
            backgroundColor: m.color + '22',
            borderWidth: 2,
            pointRadius: 0,
            pointHitRadius: 8,
            tension: 0.15,
            fill: true,
          },
          ...(m.threshold != null ? [{
            label: `Meta ${m.threshold}${m.unit}`,
            data: data.map(() => m.threshold!),
            borderColor: m.threshold != null && id === 'TBR' ? '#ef4444' : '#22c55e',
            borderWidth: 1,
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false,
          }] : []),
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        scales: {
          x: {
            title: { display: true, text: 'Tick', color: '#9ca3af' },
            grid: { color: '#ffffff0d' },
            ticks: { color: '#9ca3af', maxTicksLimit: 10 },
          },
          y: {
            title: { display: true, text: m.unit, color: '#9ca3af' },
            grid: { color: '#ffffff0d' },
            ticks: { color: '#9ca3af' },
            beginAtZero: true,
          },
        },
        plugins: {
          legend: { display: true, labels: { color: '#d1d5db' } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}${m.unit}`,
            },
          },
        },
      },
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
