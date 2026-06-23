import { SimMode, PickingPolicy } from '../enums/sim.enums';

export interface GridConfig {
  x:                number;
  y:                number;
  z:                number;
  numRobots:        number;
  occupancyPct:     number;
  mode:             SimMode;
  policy:           string;
  sessionName?:     string;
  semilla?:         number;
  pedidosDemandados?: number;
  // Robots 1×2 con orientación fija: conteo por orientación.
  robotsNorte?:     number;
  robotsEste?:      number;
  robotsOeste?:     number;
}

export interface GridConfigDTO {
  x:             number;
  y:             number;
  z:             number;
  num_robots:    number;
  occupancy_pct: number;
  mode:          string;
  policy:        string;
  session_name?: string;
  semilla?:      number;
  pedidos_demandados?: number;
  robots_norte?: number;
  robots_este?:  number;
  robots_oeste?: number;
}

export const DEFAULT_GRID_CONFIG: GridConfig = {
  x:                12,
  y:                10,
  z:                5,
  numRobots:        8,
  occupancyPct:     78,
  mode:             SimMode.DIURNO,
  policy:           PickingPolicy.FIFO,
  sessionName:      'Ejec_FIFO_78pct',
  semilla:          20260506,
  pedidosDemandados: 120,
  robotsNorte:      2,
  robotsEste:       3,
  robotsOeste:      3,
};

export function toDTO(cfg: GridConfig): GridConfigDTO {
  return {
    x:             cfg.x,
    y:             cfg.y,
    z:             cfg.z,
    num_robots:    cfg.numRobots,
    occupancy_pct: cfg.occupancyPct,
    mode:          cfg.mode,
    policy:        cfg.policy,
    session_name:  cfg.sessionName,
    semilla:       cfg.semilla,
    pedidos_demandados: cfg.pedidosDemandados,
    robots_norte:  cfg.robotsNorte,
    robots_este:   cfg.robotsEste,
    robots_oeste:  cfg.robotsOeste,
  };
}
