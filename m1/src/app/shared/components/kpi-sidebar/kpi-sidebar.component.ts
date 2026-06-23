import { Component, Input } from '@angular/core';
import { SimMode } from '../../../core/enums/sim.enums';
import { BusState } from '../../../core/services/bus-client.service';
import { KPI_DEFS, KpiDef, kpiStatus, fmtKpi } from '../kpi-panel/kpi-panel.component';

@Component({
  selector: 'app-kpi-sidebar',
  templateUrl: './kpi-sidebar.component.html',
  styleUrls: ['./kpi-sidebar.component.scss'],
  imports: [],
})
export class KpiSidebarComponent {
  @Input() bus!: BusState;

  readonly kpiDefs = KPI_DEFS;

  private get kpiValues(): Record<string, number> {
    const k = this.bus?.kpis;
    return k ? { TSP: k.TSP, TPCP: k.TPCP, MTRP: k.MTRP, IOG: k.IOG, TR: k.TR, TI: k.TI, TBR: k.TBR } : {};
  }

  isActive(def: KpiDef): boolean {
    return def.modes.includes(this.bus?.mode ?? SimMode.DIURNO);
  }

  private val(def: KpiDef): number {
    return this.kpiValues[def.id] ?? 0;
  }

  displayValue(def: KpiDef): string {
    return this.isActive(def) ? fmtKpi(def.id, this.val(def)) : '—';
  }

  status(def: KpiDef): 'ok' | 'warn' | 'bad' | 'info' {
    return kpiStatus(def, this.val(def), this.isActive(def));
  }

  statusColor(def: KpiDef): string {
    const s = this.status(def);
    if (s === 'ok') return 'var(--status-online)';
    if (s === 'warn') return 'var(--shift-day)';
    if (s === 'bad') return 'var(--brand)';
    return 'var(--text-faint)';
  }

  statusLabel(def: KpiDef): string {
    const s = this.status(def);
    if (s === 'ok') return 'Cumple meta';
    if (s === 'warn') return 'En observación';
    if (s === 'bad') return 'Fuera de meta';
    return 'Inactivo en este turno';
  }
}
