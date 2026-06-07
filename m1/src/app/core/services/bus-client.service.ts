import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';
import { SimMode, PickingPolicy, SimStatus } from '../enums/sim.enums';
import { GridConfig } from '../models/grid-config.model';

export interface KpisComputed {
  TSP: number;
  TPCP: number;
  MTRP: number;
  IOG: number;
  TR: number;
  TI: number;
  TBR: number;
  completados: number;
  capacidad: number;
  cajasPresentes: number;
}

export interface BusState {
  tick: number;
  running: boolean;
  velocidad: 1 | 2 | 5;
  mode: SimMode;
  policy: PickingPolicy;
  semilla: number;
  grid: { x: number; y: number; z: number };
  numRobots: number;
  ocupacionInicial: number;
  pedidosDemandados: number;
  nombreEjecucion: string;
  archivoOla: 'valido' | 'errores' | 'no_cargado';
  archivoReposicion: 'valido' | 'errores' | 'no_cargado';
  falloSistema: 'motor' | 'omniverse' | null;
  omniverse: 'conectado' | 'headless';
  kpis: KpisComputed;
  status: SimStatus;
}

export const FORUS_DEFAULTS = {
  grid: { x: 12, y: 10, z: 5 },
  numRobots: 8,
  ocupacionInicial: 78,
  pedidosDemandados: 120,
};

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function computeKpis(tick: number, mode: SimMode, policy: PickingPolicy,
                     numRobots: number, ocupacionInicial: number,
                     grid: { x: number; y: number; z: number },
                     semilla: number, pedidosDemandados: number): KpisComputed {
  const modoEng = mode === SimMode.DIURNO ? 'PICKING' : 'REPOSICION';
  const polEng  = policy === PickingPolicy.FIFO ? 'FIFO' : 'POSICION';
  const r = mulberry32(semilla + tick);
  const jitter = (amp: number) => (r() - 0.5) * 2 * amp;
  const polFactor = polEng === 'POSICION' ? 0.74 : 1.0;
  const capacidad = grid.x * grid.y * grid.z;
  const prog = Math.min(1, tick / 480);
  const ritmo = (numRobots / 8) * (polEng === 'POSICION' ? 1.12 : 1.0);
  const completados = Math.min(pedidosDemandados, Math.floor(prog * pedidosDemandados * ritmo));
  const tsp = pedidosDemandados ? (completados / pedidosDemandados) * 100 : 0;
  const deltaOcc = modoEng === 'PICKING' ? -prog * 14 : prog * 16;
  const iog = Math.max(8, Math.min(98, ocupacionInicial + deltaOcc + jitter(0.6)));
  const rigidez = Math.max(0, (iog - 70) / 30);
  const tbr = Math.max(0.5, 4 + rigidez * 11 + jitter(0.8));
  const tpcp = modoEng === 'PICKING' ? Math.max(1.4, 4.2 * polFactor + rigidez * 1.6 + jitter(0.15)) : 0;
  const mtrp = modoEng === 'PICKING' ? Math.max(6, 18 * polFactor + rigidez * 4 + jitter(0.4)) : 0;
  const tr = modoEng === 'PICKING' ? Math.max(0, numRobots * 1.55 * (1 - rigidez * 0.35) * (polEng === 'POSICION' ? 1.15 : 1) + jitter(0.5)) : 0;
  const ti = modoEng === 'REPOSICION' ? Math.max(0, numRobots * 1.35 * (1 - rigidez * 0.25) + jitter(0.5)) : 0;
  const cajasPresentes = Math.round((iog / 100) * capacidad);
  return { TSP: tsp, TPCP: tpcp, MTRP: mtrp, IOG: iog, TR: tr, TI: ti, TBR: tbr, completados, capacidad, cajasPresentes };
}

const INITIAL_GRID = { ...FORUS_DEFAULTS.grid };
const INITIAL_KPIS = computeKpis(0, SimMode.DIURNO, PickingPolicy.FIFO, FORUS_DEFAULTS.numRobots, FORUS_DEFAULTS.ocupacionInicial, INITIAL_GRID, 20260506, FORUS_DEFAULTS.pedidosDemandados);

const INITIAL_STATE: BusState = {
  tick: 0, running: false, velocidad: 1,
  mode: SimMode.DIURNO, policy: PickingPolicy.FIFO,
  semilla: 20260506, grid: INITIAL_GRID,
  numRobots: FORUS_DEFAULTS.numRobots,
  ocupacionInicial: FORUS_DEFAULTS.ocupacionInicial,
  pedidosDemandados: FORUS_DEFAULTS.pedidosDemandados,
  nombreEjecucion: 'Ejec_FIFO_78pct',
  archivoOla: 'valido', archivoReposicion: 'valido',
  falloSistema: null, omniverse: 'headless',
  kpis: INITIAL_KPIS, status: SimStatus.IDLE,
};

@Injectable({ providedIn: 'root' })
export class BusClientService implements OnDestroy {
  private readonly _bus$ = new BehaviorSubject<BusState>({ ...INITIAL_STATE });
  private intervalId?: ReturnType<typeof setInterval>;

  readonly bus$ = this._bus$.asObservable();

  get state(): BusState { return this._bus$.value; }

  setRunning(running: boolean): void {
    this.patch({ running, status: running ? SimStatus.RUNNING : SimStatus.PAUSED });
    if (running) this.startTick(); else this.stopTick();
  }

  setMode(mode: SimMode): void { this.patch({ mode }); }
  setPolicy(policy: PickingPolicy): void { this.patch({ policy }); }

  setSpeed(velocidad: 1 | 2 | 5): void {
    this.patch({ velocidad });
    if (this.state.running) { this.stopTick(); this.startTick(); }
  }

  setField(patch: Partial<BusState>): void { this.patch(patch); }

  applyConfig(cfg: GridConfig): void {
    const grid = { x: cfg.x, y: cfg.y, z: cfg.z };
    const numRobots = cfg.numRobots;
    const ocupacionInicial = cfg.occupancyPct;
    const mode = cfg.mode;
    const policy = cfg.policy;
    const semilla = cfg.semilla ?? this.state.semilla;
    const pedidosDemandados = cfg.pedidosDemandados ?? this.state.pedidosDemandados;
    const nombreEjecucion = cfg.sessionName ?? this.state.nombreEjecucion;
    this.patch({ grid, numRobots, ocupacionInicial, mode, policy, semilla, pedidosDemandados, nombreEjecucion });
  }

  restaurarForus(): void {
    this.patch({
      grid: { ...FORUS_DEFAULTS.grid },
      numRobots: FORUS_DEFAULTS.numRobots,
      ocupacionInicial: FORUS_DEFAULTS.ocupacionInicial,
      pedidosDemandados: FORUS_DEFAULTS.pedidosDemandados,
    });
  }

  reset(): void {
    this.stopTick();
    this._bus$.next({ ...INITIAL_STATE, kpis: computeKpis(0, INITIAL_STATE.mode, INITIAL_STATE.policy, INITIAL_STATE.numRobots, INITIAL_STATE.ocupacionInicial, INITIAL_STATE.grid, INITIAL_STATE.semilla, INITIAL_STATE.pedidosDemandados) });
  }

  startSimulation(): void {
    this.patch({ tick: 0, status: SimStatus.RUNNING, running: true });
    this.startTick();
  }

  private patch(partial: Partial<BusState>): void {
    const s = { ...this._bus$.value, ...partial };
    s.kpis = computeKpis(s.tick, s.mode, s.policy, s.numRobots, s.ocupacionInicial, s.grid, s.semilla, s.pedidosDemandados);
    this._bus$.next(s);
  }

  private startTick(): void {
    this.stopTick();
    const ms = Math.round(1000 / this.state.velocidad);
    this.intervalId = setInterval(() => {
      const s = this._bus$.value;
      if (!s.running) return;
      const tick = s.tick + 1;
      const kpis = computeKpis(tick, s.mode, s.policy, s.numRobots, s.ocupacionInicial, s.grid, s.semilla, s.pedidosDemandados);
      this._bus$.next({ ...s, tick, kpis });
    }, ms);
  }

  private stopTick(): void {
    if (this.intervalId != null) { clearInterval(this.intervalId); this.intervalId = undefined; }
  }

  ngOnDestroy(): void { this.stopTick(); }
}
