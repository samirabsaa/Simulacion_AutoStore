import { Component, Input, OnChanges, OnInit } from '@angular/core';
import { WsGrillaCell, WsRobotState, WsEstacion } from '../../../core/models/state-bus-snapshot.model';
import { robotStateShort } from '../../../core/utils/robot-state.util';

interface HeatCell {
  key:         string;
  ring:        boolean;        // celda del anillo de tránsito (sin cajas)
  occ:         number;        // % ocupación de la columna (solo interior)
  color:       string;
  station:     string | null; // 'E' | 'O' si hay estación de despacho
  hasRobot:    boolean;
  robotId:     number;
  robotRole:   'body' | 'tip' | '';
  robotEstado: string;
  robotIcon:   string;
  robotOri:    string;
}

function occColor(o: number): string {
  if (o <= 0)  return 'transparent';
  if (o < 20) return 'var(--occ-1)';
  if (o < 40) return 'var(--occ-2)';
  if (o < 60) return 'var(--occ-3)';
  if (o < 80) return 'var(--occ-4)';
  return 'var(--occ-5)';
}

// Desplazamiento de la punta según orientación fija (igual que el motor).
const TIP_OFFSET: Record<string, [number, number]> = {
  N: [0, 1], E: [1, 0], O: [-1, 0],
};

@Component({
  selector: 'app-robot-grid',
  templateUrl: './robot-grid.component.html',
  styleUrls: ['./robot-grid.component.scss'],
  imports: [],
})
export class RobotGridComponent implements OnInit, OnChanges {
  @Input() gridX   = 12;   // interior (almacenable)
  @Input() gridY   = 10;
  @Input() gridZ   = 5;
  @Input() grilla: WsGrillaCell[] = [];
  @Input() robots: WsRobotState[] = [];
  @Input() estaciones: WsEstacion[] = [];
  @Input() tick    = 0;

  cells: HeatCell[] = [];

  readonly ramp = [
    { label: '0–20%',   cssVar: '--occ-1' },
    { label: '20–40%',  cssVar: '--occ-2' },
    { label: '40–60%',  cssVar: '--occ-3' },
    { label: '60–80%',  cssVar: '--occ-4' },
    { label: '80–100%', cssVar: '--occ-5' },
  ];

  readonly stateLegend = [
    { mod: 'idle',       label: 'Inactivo' },
    { mod: 'moving',     label: 'Moviendo' },
    { mod: 'picking',    label: 'Excavando' },
    { mod: 'blocked',    label: 'Bloqueado' },
    { mod: 'depositing', label: 'Entregando' },
  ];

  // Superficie total = interior + anillo de tránsito que lo envuelve.
  get cols(): number { return Math.min(this.gridX + 2, 24); }
  get rows(): number { return Math.min(this.gridY + 2, 22); }
  get colTemplate(): string { return `repeat(${this.cols}, 1fr)`; }

  ngOnInit(): void { this.rebuildCells(); }
  ngOnChanges(): void { this.rebuildCells(); }

  private rebuildCells(): void {
    const gx = this.gridX, gy = this.gridY;

    // Ocupación por columna interior (cajas vienen en coords [1..gx]×[1..gy]).
    const boxCount = new Map<string, number>();
    for (const c of this.grilla) {
      const key = `${c.x}-${c.y}`;
      boxCount.set(key, (boxCount.get(key) ?? 0) + 1);
    }

    // Estaciones por celda.
    const estMap = new Map<string, string>();
    for (const e of this.estaciones) estMap.set(`${e.x}-${e.y}`, e.orientacion);

    // Footprint de cada robot: cuerpo + punta (según orientación fija).
    const robotMap = new Map<string, { id: number; role: 'body' | 'tip'; estado: string; ori: string }>();
    for (const r of this.robots) {
      const ori = r.orientacion ?? 'N';
      robotMap.set(`${r.x}-${r.y}`, { id: r.id, role: 'body', estado: r.estado, ori });
      const off = TIP_OFFSET[ori] ?? [0, 1];
      robotMap.set(`${r.x + off[0]}-${r.y + off[1]}`, { id: r.id, role: 'tip', estado: r.estado, ori });
    }

    const result: HeatCell[] = [];
    // Recorre la superficie total [0..gx+1]×[0..gy+1].
    for (let y = 0; y <= gy + 1; y++) {
      for (let x = 0; x <= gx + 1; x++) {
        if (x >= this.cols || y >= this.rows) continue;
        const key = `${x}-${y}`;
        const interior = x >= 1 && x <= gx && y >= 1 && y <= gy;
        const occ = interior ? ((boxCount.get(key) ?? 0) / this.gridZ) * 100 : 0;
        const rob = robotMap.get(key);
        result.push({
          key,
          ring: !interior,
          occ: Math.round(occ),
          color: occColor(occ),
          station: estMap.get(key) ?? null,
          hasRobot: !!rob,
          robotId: rob?.id ?? 0,
          robotRole: rob?.role ?? '',
          robotEstado: rob?.estado ?? '',
          robotIcon: robotStateShort(rob?.estado ?? ''),
          robotOri: rob?.ori ?? '',
        });
      }
    }
    this.cells = result;
  }
}
