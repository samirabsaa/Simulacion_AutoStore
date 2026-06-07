import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { BusClientService, BusState, FORUS_DEFAULTS } from '../../core/services/bus-client.service';
import { SimMode, PickingPolicy } from '../../core/enums/sim.enums';

const SKUS    = ['SKU-4821','SKU-1107','SKU-9043','SKU-3390','SKU-7756','SKU-2204'];
const PUERTOS = ['puerto_1','puerto_2','puerto_3','puerto_4'];

interface CsvRow { n: number; cells: string[]; issues: { tipo: string; msg: string }[]; ok: boolean; }

interface CsvResult { cargado: boolean; filas: CsvRow[]; total: number; validas: number; errores: number; }

function validarFila(tipo: 'ola'|'reposicion', cells: string[]) {
  const issues: { tipo: string; msg: string }[] = [];
  const [id, sku, cantidadRaw] = cells;
  if (!id?.trim()) issues.push({ tipo:'formato', msg:'Identificador vacío' });
  if (!sku?.trim()) issues.push({ tipo:'formato', msg:'SKU vacío' });
  else if (!SKUS.includes(sku)) issues.push({ tipo:'sku', msg:`SKU inexistente: ${sku}` });
  const cant = Number(cantidadRaw);
  if (cantidadRaw == null || cantidadRaw.trim() === '') issues.push({ tipo:'formato', msg:'Cantidad vacía' });
  else if (!Number.isFinite(cant)) issues.push({ tipo:'formato', msg:`Cantidad no numérica: "${cantidadRaw}"` });
  else if (cant <= 0) issues.push({ tipo:'vacio', msg:'Pedido sin unidades (cantidad 0)' });
  if (tipo === 'ola') {
    const dest = cells[3];
    if (!dest?.trim()) issues.push({ tipo:'formato', msg:'Destino vacío' });
    else if (!PUERTOS.includes(dest)) issues.push({ tipo:'puerto', msg:`Destino inexistente: ${dest}` });
  }
  return issues;
}

const DATASETS: Record<string, Record<string, string[][]>> = {
  ola: {
    valido: [
      ['P-0001','SKU-4821','2','puerto_1'],['P-0002','SKU-1107','1','puerto_2'],
      ['P-0003','SKU-9043','3','puerto_1'],['P-0004','SKU-3390','1','puerto_3'],
      ['P-0005','SKU-7756','2','puerto_4'],['P-0006','SKU-2204','1','puerto_2'],
    ],
    errores: [
      ['P-0001','SKU-4821','2','puerto_1'],['P-0002','SKU-1107','0','puerto_2'],
      ['P-0003','SKU-0000','3','puerto_1'],['P-0004','SKU-3390','dos','puerto_3'],
      ['P-0005','SKU-7756','2',''],        ['P-0006','SKU-2204','1','puerto_9'],
    ],
  },
  reposicion: {
    valido: [
      ['CJ-2001','SKU-4821','1'],['CJ-2002','SKU-3390','1'],
      ['CJ-2003','SKU-7756','2'],['CJ-2004','SKU-2204','1'],
    ],
    errores: [
      ['CJ-2001','SKU-4821','1'],['CJ-2002','SKU-0000','1'],
      ['CJ-2003','SKU-7756','0'],['CJ-2004','SKU-2204',''],
    ],
  },
};

const ISSUE_LABEL: Record<string, string> = { formato:'Formato', sku:'SKU', vacio:'Pedido vacío', puerto:'Destino' };

@Component({
  selector: 'app-config',
  templateUrl: './config.page.html',
  styleUrls: ['./config.page.scss'],
  imports: [],
})
export class ConfigPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  readonly SimMode       = SimMode;
  readonly PickingPolicy = PickingPolicy;
  readonly issueLabel    = ISSUE_LABEL;

  constructor(private busService: BusClientService, private router: Router) {}

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

  // ── CSV state simulator ─────────────────────────────────────────────────
  setCsvEstado(campo: 'archivoOla'|'archivoReposicion', val: 'valido'|'errores'|'no_cargado') {
    this.busService.setField({ [campo]: val } as any);
  }

  get csvTipo(): 'ola'|'reposicion' {
    return this.bus?.mode === SimMode.DIURNO ? 'ola' : 'reposicion';
  }

  get csvCampo(): 'archivoOla'|'archivoReposicion' {
    return this.bus?.mode === SimMode.DIURNO ? 'archivoOla' : 'archivoReposicion';
  }

  get csvEstado(): 'valido'|'errores'|'no_cargado' {
    return (this.bus?.[this.csvCampo] as any) ?? 'no_cargado';
  }

  get csvResult(): CsvResult {
    const tipo = this.csvTipo;
    const estado = this.csvEstado;
    if (estado === 'no_cargado') return { cargado: false, filas: [], total: 0, validas: 0, errores: 0 };
    const raw = DATASETS[tipo][estado] ?? DATASETS[tipo]['valido'];
    const filas: CsvRow[] = raw.map((cells, i) => {
      const issues = validarFila(tipo, cells);
      return { n: i+1, cells, issues, ok: issues.length === 0 };
    });
    const errores = filas.filter(f => !f.ok).length;
    return { cargado: true, filas, total: filas.length, validas: filas.length - errores, errores };
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
    return this.csvResult.cargado && this.csvResult.errores === 0;
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
