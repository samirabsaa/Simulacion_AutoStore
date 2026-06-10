import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { BusClientService, BusState, FORUS_DEFAULTS } from '../../core/services/bus-client.service';
import { SimApiService } from '../../core/services/sim-api.service';
import { SimMode, PickingPolicy } from '../../core/enums/sim.enums';
import { FileLoaderComponent } from '../../shared/components/file-loader/file-loader.component';

@Component({
  selector: 'app-config',
  templateUrl: './config.page.html',
  styleUrls: ['./config.page.scss'],
  imports: [FileLoaderComponent],
})
export class ConfigPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  readonly SimMode       = SimMode;
  readonly PickingPolicy = PickingPolicy;

  private csvErrorsByField: Record<'archivoOla' | 'archivoReposicion', string[]> = {
    archivoOla: [],
    archivoReposicion: [],
  };

  constructor(
    private busService: BusClientService,
    private simApi: SimApiService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => (this.bus = s));
  }

  // ── Slider helpers ──────────────────────────────────────────────────────
  setX(e: Event)   { this.busService.setField({ grid: { ...this.busService.state.grid, x: +(<HTMLInputElement>e.target).value } }); }
  setY(e: Event)   { this.busService.setField({ grid: { ...this.busService.state.grid, y: +(<HTMLInputElement>e.target).value } }); }
  setZ(e: Event)   { this.busService.setField({ grid: { ...this.busService.state.grid, z: +(<HTMLInputElement>e.target).value } }); }
  setR(e: Event)   { this.busService.setField({ numRobots:        +(<HTMLInputElement>e.target).value }); }
  setOcc(e: Event) { this.busService.setField({ ocupacionInicial: +(<HTMLInputElement>e.target).value }); }
  setPed(e: Event) { this.busService.setField({ pedidosDemandados:+(<HTMLInputElement>e.target).value }); }

  setNombre(e: Event)  { this.busService.setField({ nombreEjecucion: (<HTMLInputElement>e.target).value }); }
  setSemilla(e: Event) { this.busService.setField({ semilla: +(<HTMLInputElement>e.target).value || 0 }); }
  randomSemilla()      { this.busService.setField({ semilla: Math.floor(Math.random() * 9e7) + 1e7 }); }

  setMode(m: SimMode)       { this.busService.setMode(m); }
  setPolicy(p: PickingPolicy){ this.busService.setPolicy(p); }
  setVelocidad(v: number)    { this.busService.setSpeed(v as 1|2|5); }
  readonly speedOptions = [1, 2, 5];
  restaurarForus()           { this.busService.restaurarForus(); }

  // ── Carga real de CSV (T-29) ────────────────────────────────────────────
  onCsvFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    const tipo = this.csvTipo;
    const campo = this.csvCampo;

    this.simApi.uploadCsv(file, tipo).subscribe({
      next: (res) => {
        this.csvErrorsByField[campo] = res.errors.map(e =>
          e.row > 0 ? `Fila ${e.row} · ${e.column}: ${e.reason}` : `${e.column}: ${e.reason}`
        );
        this.busService.setField({ [campo]: res.valid ? 'valido' : 'errores' } as Partial<BusState>);
      },
      error: () => {
        this.csvErrorsByField[campo] = ['No se pudo conectar con el backend para validar el archivo.'];
        this.busService.setField({ [campo]: 'errores' } as Partial<BusState>);
      },
    });
  }

  get csvErrors(): string[] {
    return this.csvErrorsByField[this.csvCampo];
  }

  get csvTipo(): 'ola'|'reposicion' {
    return this.bus?.mode === SimMode.DIURNO ? 'ola' : 'reposicion';
  }

  get csvCampo(): 'archivoOla'|'archivoReposicion' {
    return this.bus?.mode === SimMode.DIURNO ? 'archivoOla' : 'archivoReposicion';
  }

  get csvEstado(): 'valido'|'errores'|'no_cargado' {
    return (this.bus?.[this.csvCampo]) ?? 'no_cargado';
  }

  get csvCols(): string[] {
    return this.csvTipo === 'ola'
      ? ['id_pedido','id_sku','cantidad','destino']
      : ['id_caja','id_sku','cantidad'];
  }

  get csvArchivoNombre(): string {
    return this.csvTipo === 'ola' ? 'ola.csv' : 'reposicion.csv';
  }

  // ── Validation ──────────────────────────────────────────────────────────
  get capacidad(): number {
    const g = this.bus?.grid ?? { x:12, y:10, z:5 };
    return g.x * g.y * g.z;
  }

  get validaciones(): { sev: 'ok'|'warn'|'error'; msg: string }[] {
    const g = this.bus?.grid ?? { x:12, y:10, z:5 };
    const robots = this.bus?.numRobots ?? 8;
    const occ = this.bus?.ocupacionInicial ?? 78;
    const cap = g.x * g.y * g.z;
    const list: { sev: 'ok'|'warn'|'error'; msg: string }[] = [];
    if (cap > 8000) list.push({ sev:'error', msg:`Capacidad ${cap.toLocaleString('es-CL')} celdas supera el máximo académico de 8.000.` });
    else if (g.x > 20 || g.y > 20 || g.z > 5) list.push({ sev:'warn', msg:'Grilla sobre la referencia de rendimiento (20×20×5 con 10 robots). FPS puede degradarse.' });
    if (robots > 10) list.push({ sev:'warn', msg:`${robots} robots: sobre los 10 del hardware de referencia (RNF-01).` });
    if (occ < 60 || occ > 90) list.push({ sev:'warn', msg:'Ocupación fuera del rango analítico recomendado (60–90%).' });
    if (list.length === 0) list.push({ sev:'ok', msg:'Parámetros válidos. Coinciden con lo que se publicará al Bus.' });
    return list;
  }

  get paramError(): boolean { return this.capacidad > 8000; }

  get csvListo(): boolean {
    return this.csvEstado === 'valido';
  }

  get puedeIniciar(): boolean {
    return !this.paramError && this.csvListo && this.bus?.falloSistema !== 'motor';
  }

  get bloqueo(): string | null {
    if (this.paramError) return 'Capacidad de grilla fuera del máximo permitido.';
    if (!this.csvListo)  return `${this.csvArchivoNombre} no está cargado o contiene filas inválidas.`;
    if (this.bus?.falloSistema === 'motor') return 'El Motor de Simulación no responde.';
    return null;
  }

  get vramPct(): number {
    return Math.min(98, 38 + (this.capacidad / 8000) * 55);
  }

  get isForus(): boolean {
    const b = this.bus;
    if (!b) return false;
    return b.grid.x === FORUS_DEFAULTS.grid.x && b.grid.y === FORUS_DEFAULTS.grid.y &&
           b.grid.z === FORUS_DEFAULTS.grid.z && b.numRobots === FORUS_DEFAULTS.numRobots &&
           b.ocupacionInicial === FORUS_DEFAULTS.ocupacionInicial &&
           b.pedidosDemandados === FORUS_DEFAULTS.pedidosDemandados;
  }

  get configJson(): string {
    const b = this.bus;
    if (!b) return '{}';
    return JSON.stringify({
      nombre_ejecucion: b.nombreEjecucion,
      grilla: b.grid,
      robots_activos: b.numRobots,
      ocupacion_inicial_pct: b.ocupacionInicial,
      semilla: b.semilla,
      modo_turno: b.mode === SimMode.DIURNO ? 'diurno_picking' : 'nocturno_reposicion',
      archivo_datos: this.csvArchivoNombre,
      politica_picking: b.policy === PickingPolicy.FIFO ? 'fifo' : 'prioridad_posicion',
      velocidad: `${b.velocidad}x`,
      pedidos_demandados: b.pedidosDemandados,
    }, null, 2);
  }

  // ── Fallos sistema ──────────────────────────────────────────────────────
  setFallo(f: 'motor'|'omniverse'|null): void { this.busService.setField({ falloSistema: f }); }
  clearFallo(): void { this.busService.setField({ falloSistema: null }); }
  goHeadless(): void { this.busService.setField({ falloSistema: null, omniverse: 'headless' }); }

  // ── Start ────────────────────────────────────────────────────────────────
  iniciar(): void {
    if (!this.puedeIniciar) return;
    this.busService.startSimulation();
    this.router.navigate(['/panel']);
  }

  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
