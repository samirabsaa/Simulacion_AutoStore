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
