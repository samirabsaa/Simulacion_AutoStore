import { Component, OnInit, OnDestroy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { SimMode, PickingPolicy, SimStatus } from '../../core/enums/sim.enums';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';
import { KpiPanelComponent, KpiDef, KPI_DEFS } from '../../shared/components/kpi-panel/kpi-panel.component';
import { RobotStatusPanelComponent } from '../../shared/components/robot-status-panel/robot-status-panel.component';
import { KpiChartComponent, ChartKpiId } from '../../shared/components/kpi-chart/kpi-chart.component';

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.page.html',
  styleUrls: ['./dashboard.page.scss'],
  imports: [BusStripComponent, KpiPanelComponent, RobotStatusPanelComponent, KpiChartComponent, RouterLink],
})
export class DashboardPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  showFinishedToast = false;
  private sub!: Subscription;

  readonly kpiDefs = KPI_DEFS;
  readonly SimMode = SimMode;
  readonly SimStatus = SimStatus;
  readonly PickingPolicy = PickingPolicy;

  selectedKpi: ChartKpiId | null = null;

  constructor(public busService: BusClientService) {}

  onChartToggle(id: ChartKpiId): void {
    this.selectedKpi = this.selectedKpi === id ? null : id;
  }

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => {
      if (s.status === SimStatus.FINISHED && (!this.bus || this.bus.status !== SimStatus.FINISHED)) {
        this.showFinishedToast = true;
      }
      this.bus = s;
    });
    // Auto-inicio eliminado: con backend real se requiere configurar y cargar CSVs
    // antes de iniciar. El usuario inicia desde /config.
  }

  dismissToast(): void {
    this.showFinishedToast = false;
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

  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
