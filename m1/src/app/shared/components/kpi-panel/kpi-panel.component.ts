import { Component, EventEmitter, Input, Output } from '@angular/core';
import { SimMode } from '../../../core/enums/sim.enums';

export interface KpiDef {
  id:          'TSP' | 'TPCP' | 'MTRP' | 'IOG' | 'TR' | 'TI' | 'TBR';
  code:        string;
  name:        string;
  unit:        string;
  meta:        string;
  better:      'higher' | 'lower' | 'range';
  threshold?:   number;
  range?:      [number, number];
  modes:       SimMode[];
  description: string;
}

export const KPI_DEFS: KpiDef[] = [
  { id: 'TSP',  code: 'KPI-01', name: 'Tasa de Satisfacción de Pedidos',      unit: '%',       meta: '≥ 95%',        better: 'higher', threshold: 95, modes: [SimMode.DIURNO],
    description: 'Porcentaje de pedidos completados respecto del total demandado. Mide la capacidad del sistema para cumplir con la ola de pedidos.' },
  { id: 'TPCP', code: 'KPI-02', name: 'Tiempo Promedio de Ciclo por Pedido',  unit: 'min',     meta: 'Minimizar',    better: 'lower',  modes: [SimMode.DIURNO],
    description: 'Tiempo promedio desde que un pedido ingresa a la cola hasta que se entrega en el puerto. Incluye desplazamiento, excavación y bloqueos.' },
  { id: 'MTRP', code: 'KPI-03', name: 'Movimientos Totales de Robots/Pedido', unit: '',        meta: 'Minimizar vs base', better: 'lower', modes: [SimMode.DIURNO],
    description: 'Cantidad promedio de desplazamientos de robots (incluyendo excavación) por cada pedido completado. Refleja eficiencia operativa.' },
  { id: 'IOG',  code: 'KPI-04', name: 'Índice de Ocupación de la Grilla',     unit: '%',       meta: 'Rango 60–90%', better: 'range',  range: [60,90], modes: [SimMode.DIURNO, SimMode.NOCTURNO],
    description: 'Porcentaje de celdas ocupadas vs la capacidad total de la grilla. Bajo desaprovecha espacio, alto congestiona el sistema.' },
  { id: 'TR',   code: 'KPI-05', name: 'Throughput de Recuperación',           unit: 'cajas/min', meta: 'Maximizar',  better: 'higher', modes: [SimMode.DIURNO],
    description: 'Velocidad de extracción de cajas de la grilla durante el turno diurno. Mide el rendimiento de salida de producto.' },
  { id: 'TI',   code: 'KPI-06', name: 'Throughput de Ingreso',                unit: 'cajas/min', meta: 'Maximizar',  better: 'higher', modes: [SimMode.NOCTURNO],
    description: 'Velocidad de colocación de cajas en la grilla durante el turno nocturno. Mide la eficiencia del reabastecimiento.' },
  { id: 'TBR',  code: 'KPI-07', name: 'Tiempo de Bloqueo de Robots',          unit: '%',       meta: '≤ 10%',        better: 'lower',  threshold: 10, modes: [SimMode.DIURNO, SimMode.NOCTURNO],
    description: 'Porcentaje del tiempo total que los robots permanecen bloqueados esperando paso. Alto TBR indica congestión en la grilla.' },
];

export type KpiStatus = 'ok' | 'warn' | 'bad' | 'info';

export function kpiStatus(def: KpiDef, value: number, active: boolean): KpiStatus {
  if (!active) return 'info';
  if (def.better === 'higher' && def.threshold != null)
    return value >= def.threshold ? 'ok' : value >= def.threshold - 5 ? 'warn' : 'bad';
  if (def.better === 'lower' && def.threshold != null)
    return value <= def.threshold ? 'ok' : value <= def.threshold + 4 ? 'warn' : 'bad';
  if (def.better === 'range' && def.range)
    return value >= def.range[0] && value <= def.range[1] ? 'ok' : 'warn';
  return 'ok';
}

export function fmtKpi(id: string, value: number): string {
  if (id === 'MTRP' || id === 'TPCP' || id === 'TR' || id === 'TI') return value.toFixed(1);
  return Math.round(value).toString();
}

const STATUS_LABEL: Record<KpiStatus, string> = {
  ok:   'Cumple meta',
  warn: 'En observación',
  bad:  'Fuera de meta',
  info: 'Inactivo en este turno',
};

const STATUS_COLOR: Record<KpiStatus, string> = {
  ok:   'var(--status-online)',
  warn: 'var(--shift-day)',
  bad:  'var(--brand)',
  info: 'var(--text-faint)',
};

@Component({
  selector: 'app-kpi-panel',
  templateUrl: './kpi-panel.component.html',
  styleUrls: ['./kpi-panel.component.scss'],
  imports: [],
})
export class KpiPanelComponent {
  @Input() def!: KpiDef;
  @Input() value: number = 0;
  @Input() active: boolean = true;
  @Input() chartActive: boolean = false;
  @Output() chartToggle = new EventEmitter<void>();

  get status(): KpiStatus { return kpiStatus(this.def, this.value, this.active); }
  get statusLabel(): string { return STATUS_LABEL[this.status]; }
  get statusColor(): string { return STATUS_COLOR[this.status]; }
  get displayValue(): string { return this.active ? fmtKpi(this.def.id, this.value) : '—'; }
}
