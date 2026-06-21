// Contrato real del bridge WebSocket (§3.1 handoff_integracion_m1.md)
// Cada mensaje en ws://localhost:8000/ws/state tiene este formato.

export interface WsRobotState {
  id:       number;
  x:        number;
  y:        number;
  z:        number;
  estado:   string;
  carga_id: string | null;
}

export interface WsKpis {
  // Claves en MAYÚSCULA (usadas por la UI: KpisComputed en bus-client.service.ts)
  TSP: number; TPCP: number; MTRP: number; IOG: number; TR: number; TI: number; TBR: number;
  // Claves en minúscula (alias enviados por el bridge)
  tsp: number; tpcp: number; mtrp: number; iog: number; tr: number; ti: number; tbr: number;
  completados:   number;
  capacidad:     number;
  cajasPresentes: number;
}

export interface WsTickPayload {
  type:      'tick';
  tick:      number;
  mode:      string;
  policy:    string;
  status:    string;
  velocidad: number;
  grid:      { x: number; y: number; z: number } | null;
  robots:    WsRobotState[];
  grilla:    unknown[];
  pedidos:   { cola: unknown[]; completados: unknown[] };
  kpis:      WsKpis;
}

export interface WsSystemErrorPayload {
  type:      'system_error';
  component: string;
  message:   string;
}

export type WsMessage = WsTickPayload | WsSystemErrorPayload;
