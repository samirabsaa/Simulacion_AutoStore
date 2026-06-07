import { Component, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { SimMode, PickingPolicy } from '../../core/enums/sim.enums';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';
import { KpiPanelComponent, KpiDef } from '../../shared/components/kpi-panel/kpi-panel.component';
import { ControlBarComponent } from '../../shared/components/control-bar/control-bar.component';
import { RobotGridComponent } from '../../shared/components/robot-grid/robot-grid.component';

const KPI_DEFS: KpiDef[] = [
  { id: 'TSP',  code: 'KPI-01', name: 'Tasa de Satisfacción de Pedidos',      unit: '%',       meta: '≥ 95%',        better: 'higher', threshold: 95, modes: [SimMode.DIURNO] },
  { id: 'TPCP', code: 'KPI-02', name: 'Tiempo Promedio de Ciclo por Pedido',  unit: 'min',     meta: 'Minimizar',    better: 'lower',  modes: [SimMode.DIURNO] },
  { id: 'MTRP', code: 'KPI-03', name: 'Movimientos Totales de Robots/Pedido', unit: '',        meta: 'Minimizar vs base', better: 'lower', modes: [SimMode.DIURNO] },
  { id: 'IOG',  code: 'KPI-04', name: 'Índice de Ocupación de la Grilla',     unit: '%',       meta: 'Rango 60–90%', better: 'range',  range: [60,90], modes: [SimMode.DIURNO, SimMode.NOCTURNO] },
  { id: 'TR',   code: 'KPI-05', name: 'Throughput de Recuperación',           unit: 'cajas/min', meta: 'Maximizar',  better: 'higher', modes: [SimMode.DIURNO] },
  { id: 'TI',   code: 'KPI-06', name: 'Throughput de Ingreso',                unit: 'cajas/min', meta: 'Maximizar',  better: 'higher', modes: [SimMode.NOCTURNO] },
  { id: 'TBR',  code: 'KPI-07', name: 'Tiempo de Bloqueo de Robots',          unit: '%',       meta: '≤ 10%',        better: 'lower',  threshold: 10, modes: [SimMode.DIURNO, SimMode.NOCTURNO] },
];

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.page.html',
  styleUrls: ['./dashboard.page.scss'],
  imports: [BusStripComponent, KpiPanelComponent, ControlBarComponent, RobotGridComponent],
})
export class DashboardPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  readonly kpiDefs = KPI_DEFS;
  readonly SimMode = SimMode;

  constructor(private busService: BusClientService) {}

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => (this.bus = s));
    if (!this.busService.state.running && this.busService.state.tick === 0) {
      this.busService.startSimulation();
    }
  }

  get kpiValues(): Record<string, number> {
    const k = this.bus?.kpis;
    return k ? { TSP: k.TSP, TPCP: k.TPCP, MTRP: k.MTRP, IOG: k.IOG, TR: k.TR, TI: k.TI, TBR: k.TBR } : {};
  }

  isKpiActive(def: KpiDef): boolean {
    return !this.bus || def.modes.includes(this.bus.mode);
  }

  get completados(): number { return this.bus?.kpis.completados ?? 0; }
  get pedidos(): number     { return this.bus?.pedidosDemandados ?? 0; }
  get cajasPresentes(): number { return this.bus?.kpis.cajasPresentes ?? 0; }
  get capacidad(): number   { return this.bus?.kpis.capacidad ?? 0; }

  get scenarioLabel(): string {
    if (!this.bus) return '—';
    const pol = this.bus.policy === PickingPolicy.FIFO ? 'FIFO' : 'Prioridad Posición';
    const modo = this.bus.mode === SimMode.DIURNO ? 'Diurno' : 'Nocturno';
    return `${pol} · ${modo}`;
  }

  onPlay():                       void { this.busService.setRunning(true); }
  onPause():                      void { this.busService.setRunning(false); }
  onReset():                      void { this.busService.reset(); }
  onSpeedChange(s: 1|2|5):       void { this.busService.setSpeed(s); }

  onModeChange(m: SimMode): void   { this.busService.setMode(m); }
  onPolicyChange(p: string): void { this.busService.setPolicy(p as PickingPolicy); }

  readonly FIFO = PickingPolicy.FIFO;
  readonly PRIORIDAD = PickingPolicy.PRIORITY_POSITION;

  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
