import { SimMode, PickingPolicy, RobotState } from '../enums/sim.enums';
import { KpiSnapshot } from './kpi-snapshot.model';

export interface Robot {
  robot_id:         number;
  x:                number;
  y:                number;
  state:            RobotState;
  assigned_task_id: string | null;
}

export interface StateBusSnapshot {
  tick:              number;
  mode:              SimMode;
  policy:            PickingPolicy;
  kpis:              KpiSnapshot;
  robots:            Robot[];
  pending_orders:    unknown[];
  completed_orders:  unknown[];
}

export interface WsTickMessage {
  type:    'tick';
  payload: StateBusSnapshot;
}

export interface WsSystemErrorMessage {
  type:    'system_error';
  payload: { component: string; message: string };
}

export type WsMessage = WsTickMessage | WsSystemErrorMessage;
