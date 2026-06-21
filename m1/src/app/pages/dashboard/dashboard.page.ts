import { Component, OnInit, OnDestroy } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { SimMode, PickingPolicy, SimStatus } from '../../core/enums/sim.enums';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';
import { KpiPanelComponent, KpiDef } from '../../shared/components/kpi-panel/kpi-panel.component';
import { RobotStatusPanelComponent } from '../../shared/components/robot-status-panel/robot-status-panel.component';

const KPI_DEFS: KpiDef[] = [
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

@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.page.html',
  styleUrls: ['./dashboard.page.scss'],
  imports: [BusStripComponent, KpiPanelComponent, RobotStatusPanelComponent, RouterLink],
})
export class DashboardPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  showFinishedToast = false;
  private sub!: Subscription;

  readonly kpiDefs = KPI_DEFS;
  readonly SimMode = SimMode;
  readonly SimStatus = SimStatus;
  readonly PickingPolicy = PickingPolicy;

  constructor(private busService: BusClientService) {}

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
