import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SimMode, PickingPolicy, SimStatus } from '../enums/sim.enums';
import { GridConfig, DEFAULT_GRID_CONFIG } from '../models/grid-config.model';
import { WsTickPayload, WsSystemErrorPayload } from '../models/state-bus-snapshot.model';
import { SimApiService } from './sim-api.service';
import { environment } from '../../../environments/environment';

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

const EMPTY_KPIS: KpisComputed = {
  TSP: 0, TPCP: 0, MTRP: 0, IOG: 0, TR: 0, TI: 0, TBR: 0,
  completados: 0, capacidad: 600, cajasPresentes: 0,
};

const INITIAL_STATE: BusState = {
  tick: 0, running: false, velocidad: 1,
  mode: SimMode.DIURNO, policy: PickingPolicy.FIFO,
  semilla: DEFAULT_GRID_CONFIG.semilla ?? 20260506,
  grid: { ...FORUS_DEFAULTS.grid },
  numRobots: FORUS_DEFAULTS.numRobots,
  ocupacionInicial: FORUS_DEFAULTS.ocupacionInicial,
  pedidosDemandados: FORUS_DEFAULTS.pedidosDemandados,
  nombreEjecucion: DEFAULT_GRID_CONFIG.sessionName ?? 'Ejec_FIFO_78pct',
  archivoOla: 'no_cargado', archivoReposicion: 'no_cargado',
  falloSistema: null, omniverse: 'headless',
  kpis: { ...EMPTY_KPIS }, status: SimStatus.IDLE,
};

@Injectable({ providedIn: 'root' })
export class BusClientService implements OnDestroy {
  private readonly _bus$ = new BehaviorSubject<BusState>({ ...INITIAL_STATE });
  private ws?: WebSocket;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private destroyed = false;

  readonly bus$ = this._bus$.asObservable();
  get state(): BusState { return this._bus$.value; }

  constructor(private simApi: SimApiService) {
    this.connect();
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────

  private connect(): void {
    if (this.destroyed) return;
    try {
      this.ws = new WebSocket(environment.wsUrl);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as WsTickPayload | WsSystemErrorPayload;
        if (msg.type === 'tick') this.applyTick(msg as WsTickPayload);
        else if (msg.type === 'system_error') this.patchLocal({ falloSistema: 'motor' });
      } catch { /* malformed frame — ignore */ }
    };

    this.ws.onclose = () => this.scheduleReconnect();
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect(): void {
    if (!this.destroyed) {
      this.reconnectTimer = setTimeout(() => this.connect(), 1000);
    }
  }

  // Aplica un mensaje tick del bridge al BusState, preservando los campos locales.
  private applyTick(msg: WsTickPayload): void {
    const s = this._bus$.value;
    const grid = msg.grid ?? s.grid;
    const kpis: KpisComputed = {
      TSP:           msg.kpis?.TSP           ?? 0,
      TPCP:          msg.kpis?.TPCP          ?? 0,
      MTRP:          msg.kpis?.MTRP          ?? 0,
      IOG:           msg.kpis?.IOG           ?? 0,
      TR:            msg.kpis?.TR            ?? 0,
      TI:            msg.kpis?.TI            ?? 0,
      TBR:           msg.kpis?.TBR           ?? 0,
      completados:   msg.kpis?.completados   ?? 0,
      capacidad:     msg.kpis?.capacidad     ?? (grid.x * grid.y * grid.z),
      cajasPresentes: msg.kpis?.cajasPresentes ?? 0,
    };
    this._bus$.next({
      // Campos locales que NO vienen por WS — se preservan tal cual
      ...s,
      // Campos que SÍ vienen del bridge
      tick:      msg.tick,
      running:   msg.status === SimStatus.RUNNING,
      status:    msg.status as SimStatus,
      velocidad: (msg.velocidad as 1 | 2 | 5) ?? s.velocidad,
      mode:      (msg.mode as SimMode)         ?? s.mode,
      policy:    (msg.policy as PickingPolicy) ?? s.policy,
      grid,
      numRobots: Array.isArray(msg.robots) ? msg.robots.length : s.numRobots,
      kpis,
    });
  }

  // Mutación local pura — no envía nada al backend.
  private patchLocal(partial: Partial<BusState>): void {
    this._bus$.next({ ...this._bus$.value, ...partial });
  }

  // ── API pública ───────────────────────────────────────────────────────────

  /** Actualiza campos puramente locales (UI-only): falloSistema, omniverse,
   *  archivoOla, archivoReposicion, semilla, nombreEjecucion, sliders de config. */
  setField(partial: Partial<BusState>): void {
    this.patchLocal(partial);
  }

  setRunning(running: boolean): void {
    if (running) this.simApi.play().subscribe({ error: () => {} });
    else this.simApi.pause().subscribe({ error: () => {} });
  }

  setMode(mode: SimMode): void {
    // El bridge no tiene endpoint separado para modo; se reenvía /config completo.
    this.patchLocal({ mode });
    this.simApi.sendConfig(this.buildConfig()).subscribe({ error: () => {} });
  }

  setPolicy(policy: PickingPolicy): void {
    this.patchLocal({ policy });
    this.simApi.setPolicy(policy).subscribe({ error: () => {} });
  }

  setSpeed(velocidad: 1 | 2 | 5): void {
    this.patchLocal({ velocidad });
    this.simApi.setSpeed(velocidad).subscribe({ error: () => {} });
  }

  /** Aplica una configuración completa: actualiza campos locales de sesión y
   *  envía POST /config al bridge. */
  applyConfig(cfg: GridConfig): void {
    this.patchLocal({
      grid:              { x: cfg.x, y: cfg.y, z: cfg.z },
      numRobots:         cfg.numRobots,
      ocupacionInicial:  cfg.occupancyPct,
      mode:              cfg.mode,
      policy:            cfg.policy,
      semilla:           cfg.semilla           ?? this.state.semilla,
      pedidosDemandados: cfg.pedidosDemandados ?? this.state.pedidosDemandados,
      nombreEjecucion:   cfg.sessionName       ?? this.state.nombreEjecucion,
    });
    this.simApi.sendConfig(cfg).subscribe({ error: () => {} });
  }

  /** Restaura los valores por defecto de Forus S.A. en la UI (no envía al backend). */
  restaurarForus(): void {
    this.patchLocal({
      grid:              { ...FORUS_DEFAULTS.grid },
      numRobots:         FORUS_DEFAULTS.numRobots,
      ocupacionInicial:  FORUS_DEFAULTS.ocupacionInicial,
      pedidosDemandados: FORUS_DEFAULTS.pedidosDemandados,
    });
  }

  /** Envía POST /control/reset. El estado real llega por WS. */
  reset(): void {
    // Actualización optimista para dar feedback inmediato al usuario
    this.patchLocal({ tick: 0, running: false, status: SimStatus.IDLE, kpis: { ...EMPTY_KPIS } });
    this.simApi.reset().subscribe({ error: () => {} });
  }

  /** Envía la configuración actual al backend y luego inicia la simulación. */
  startSimulation(): void {
    const cfg = this.buildConfig();
    this.simApi.sendConfig(cfg).subscribe({
      next: () => this.simApi.play().subscribe({ error: () => {} }),
      error: () => {},
    });
  }

  private buildConfig(): GridConfig {
    const s = this.state;
    return {
      x: s.grid.x, y: s.grid.y, z: s.grid.z,
      numRobots:         s.numRobots,
      occupancyPct:      s.ocupacionInicial,
      mode:              s.mode,
      policy:            s.policy,
      sessionName:       s.nombreEjecucion,
      semilla:           s.semilla,
      pedidosDemandados: s.pedidosDemandados,
    };
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
