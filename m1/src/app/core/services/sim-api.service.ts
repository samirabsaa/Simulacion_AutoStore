import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { GridConfig, toDTO } from '../models/grid-config.model';
import { ValidationResultDTO } from '../models/csv-validation-error.model';

import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class SimApiService {
  constructor(private http: HttpClient) {}

  sendConfig(cfg: GridConfig): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${environment.apiUrl}/config`, toDTO(cfg));
  }

  setPolicy(p: string): Observable<{ ok: boolean }> {
    return this.http.post<{ ok: boolean }>(`${environment.apiUrl}/policy`, { policy: p });
  }

  uploadPolicy(file: File): Observable<{ ok: boolean; policy_name: string; detail?: string }> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<{ ok: boolean; policy_name: string; detail?: string }>(
      `${environment.apiUrl}/api/upload/policy`, form,
    );
  }

  getPolicies(): Observable<{ policies: string[] }> {
    return this.http.get<{ policies: string[] }>(`${environment.apiUrl}/policies`);
  }

  play(): Observable<{ ok: boolean; status?: string }> {
    return this.http.post<{ ok: boolean; status?: string }>(`${environment.apiUrl}/control/play`, {});
  }

  pause(): Observable<{ ok: boolean; status?: string }> {
    return this.http.post<{ ok: boolean; status?: string }>(`${environment.apiUrl}/control/pause`, {});
  }

  reset(): Observable<{ ok: boolean; status?: string }> {
    return this.http.post<{ ok: boolean; status?: string }>(`${environment.apiUrl}/control/reset`, {});
  }

  setSpeed(s: number): Observable<{ ok: boolean; velocidad?: number }> {
    return this.http.post<{ ok: boolean; velocidad?: number }>(`${environment.apiUrl}/control/speed`, { velocidad: s });
  }

  loadDemoOla(name: string): Observable<ValidationResultDTO> {
    return this.http.post<ValidationResultDTO>(`${environment.apiUrl}/demo/load-ola`, null, { params: { name } });
  }

  uploadCsv(file: File, tipo: 'ola' | 'reposicion'): Observable<ValidationResultDTO> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<ValidationResultDTO>(`${environment.apiUrl}/api/upload/${tipo}`, form);
  }

  downloadComparativo(): void {
    window.open(`${environment.apiUrl}/report/comparativo`, '_blank');
  }

  exportSesion(): void {
    window.open(`${environment.apiUrl}/report/sesion`, '_blank');
  }
}
