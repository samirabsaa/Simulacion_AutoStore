import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { delay } from 'rxjs/operators';
import { BusClientService } from './bus-client.service';
import { GridConfig } from '../models/grid-config.model';
import { ValidationResultDTO } from '../models/csv-validation-error.model';
import { SimMode, PickingPolicy, SimSpeed, SimStatus } from '../enums/sim.enums';

export interface ControlCommandDTO {
  kind:    'SET_MODE' | 'SET_POLICY' | 'SET_SPEED' | 'SET_STATUS' | 'RESET';
  payload: string | number | null;
}

@Injectable({ providedIn: 'root' })
export class SimApiService {
  // Mock implementation: uses BusClientService to control state.
  // Real implementation replaces this with HttpClient calls to FastAPI.
  constructor(private bus: BusClientService) {}

  sendConfig(cfg: GridConfig): Observable<{ ok: boolean }> {
    this.bus.applyConfig(cfg);
    return of({ ok: true }).pipe(delay(400));
  }

  sendControl(cmd: ControlCommandDTO): Observable<{ ok: boolean }> {
    switch (cmd.kind) {
      case 'SET_STATUS':
        this.bus.setRunning(cmd.payload === SimStatus.RUNNING);
        break;
      case 'SET_MODE':
        this.bus.setMode(cmd.payload as SimMode);
        break;
      case 'SET_POLICY':
        this.bus.setPolicy(cmd.payload as PickingPolicy);
        break;
      case 'SET_SPEED':
        this.bus.setSpeed(Number(cmd.payload));
        break;
      case 'RESET':
        this.bus.reset();
        break;
    }
    return of({ ok: true });
  }

  play(): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'SET_STATUS', payload: SimStatus.RUNNING });
  }

  pause(): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'SET_STATUS', payload: SimStatus.PAUSED });
  }

  reset(cfg: GridConfig): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'RESET', payload: null });
  }

  setMode(mode: SimMode): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'SET_MODE', payload: mode });
  }

  setPolicy(p: PickingPolicy): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'SET_POLICY', payload: p });
  }

  setSpeed(s: SimSpeed): Observable<{ ok: boolean }> {
    return this.sendControl({ kind: 'SET_SPEED', payload: s.toString() });
  }

  uploadCsv(file: File, tipo: 'ola' | 'reposicion'): Observable<ValidationResultDTO> {
    if (!file || file.size === 0) {
      return of({
        valid: false,
        errors: [{ row: 0, column: 'archivo', value: '', reason: 'El archivo está vacío' }],
      }).pipe(delay(300));
    }
    return of({ valid: true, errors: [] }).pipe(delay(600));
  }
}
