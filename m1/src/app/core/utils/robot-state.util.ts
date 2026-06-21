export const ROBOT_STATE_LABELS: Record<string, string> = {
  IDLE:       'Inactivo',
  MOVING:     'En movimiento',
  PICKING:    'Excavando',
  BLOCKED:    'Bloqueado',
  DEPOSITING: 'Entregando',
};

export const ROBOT_STATE_SHORT: Record<string, string> = {
  IDLE:       'IDL',
  MOVING:     'MOV',
  PICKING:    'EXC',
  BLOCKED:    'BLK',
  DEPOSITING: 'ENT',
};

export function robotStateLabel(estado: string): string {
  return ROBOT_STATE_LABELS[estado] ?? estado;
}

export function robotStateShort(estado: string): string {
  return ROBOT_STATE_SHORT[estado] ?? '?';
}

export function robotStateCssMod(estado: string): string {
  switch (estado) {
    case 'IDLE':       return 'idle';
    case 'MOVING':     return 'moving';
    case 'PICKING':    return 'picking';
    case 'BLOCKED':    return 'blocked';
    case 'DEPOSITING': return 'depositing';
    default:           return 'unknown';
  }
}
