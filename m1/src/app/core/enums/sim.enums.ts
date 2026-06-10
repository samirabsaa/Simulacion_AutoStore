export enum SimMode {
  DIURNO   = 'DIURNO',
  NOCTURNO = 'NOCTURNO',
}

export enum PickingPolicy {
  FIFO              = 'FIFO',
  PRIORITY_POSITION = 'PRIORIDAD_POSICION',
}

export enum RobotState {
  IDLE       = 'IDLE',
  MOVING     = 'MOVING',
  PICKING    = 'PICKING',
  DEPOSITING = 'DEPOSITING',
  BLOCKED    = 'BLOCKED',
}

export enum SimSpeed {
  X1 = 1,
  X2 = 2,
  X5 = 5,
}

export enum SimStatus {
  IDLE     = 'IDLE',
  RUNNING  = 'RUNNING',
  PAUSED   = 'PAUSED',
  FINISHED = 'FINISHED',
}
