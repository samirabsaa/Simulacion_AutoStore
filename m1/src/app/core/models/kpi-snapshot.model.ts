export interface KpiSnapshot {
  tick: number;
  tsp:  number;
  tpcp: number;
  mtrp: number;
  iog:  number;
  tr:   number;
  ti:   number;
  tbr:  number;
}

export const EMPTY_KPI: KpiSnapshot = {
  tick: 0, tsp: 0, tpcp: 0, mtrp: 0,
  iog: 0, tr: 0, ti: 0, tbr: 0,
};

export function kpiStatus(field: keyof KpiSnapshot, value: number): 'ok' | 'warn' | 'bad' {
  if (field === 'tsp') {
    if (value >= 95) return 'ok';
    if (value >= 80) return 'warn';
    return 'bad';
  }
  if (field === 'tbr') {
    if (value <= 10) return 'ok';
    if (value <= 20) return 'warn';
    return 'bad';
  }
  return 'ok';
}
