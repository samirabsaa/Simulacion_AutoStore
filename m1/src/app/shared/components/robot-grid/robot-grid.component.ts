import { Component, Input, OnChanges, OnInit } from '@angular/core';
import { WsGrillaCell, WsRobotState, WsEstacion } from '../../../core/models/state-bus-snapshot.model';
import { robotStateShort } from '../../../core/utils/robot-state.util';

interface HeatCell {
  key:     string;
  ring:    boolean;        // celda del anillo de tránsito (sin cajas)
  occ:     number;        // % ocupación de la columna (solo interior)
  color:   string;
  station: string | null; // 'E' | 'O' si hay estación de despacho
}

// Robot 1×2 dibujado como un rectángulo que ocupa sus dos celdas (cuerpo + punta).
interface RobotRect {
  id:        number;
  estado:    string;
  icon:      string;
  ori:       string;
  gridCol:   string;       // CSS grid-column (con span si es horizontal)
  gridRow:   string;       // CSS grid-row (con span si es vertical)
  tipClass:  string;       // dirección de la punta para el indicador
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
  robotRects: RobotRect[] = [];

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
  get rowTemplate(): string { return `repeat(${this.rows}, 1fr)`; }

  ngOnInit(): void { this.rebuild(); }
  ngOnChanges(): void { this.rebuild(); }

  private rebuild(): void {
    const gx = this.gridX, gy = this.gridY;

    // ── Fondo: ocupación por columna interior + estaciones ──
    const boxCount = new Map<string, number>();
    for (const c of this.grilla) {
      const key = `${c.x}-${c.y}`;
      boxCount.set(key, (boxCount.get(key) ?? 0) + 1);
    }
    const estMap = new Map<string, string>();
    for (const e of this.estaciones) estMap.set(`${e.x}-${e.y}`, e.orientacion);

    const cells: HeatCell[] = [];
    for (let y = 0; y <= gy + 1; y++) {
      for (let x = 0; x <= gx + 1; x++) {
        if (x >= this.cols || y >= this.rows) continue;
        const key = `${x}-${y}`;
        const interior = x >= 1 && x <= gx && y >= 1 && y <= gy;
        const occ = interior ? ((boxCount.get(key) ?? 0) / this.gridZ) * 100 : 0;
        cells.push({
          key,
          ring: !interior,
          occ: Math.round(occ),
          color: occColor(occ),
          station: estMap.get(key) ?? null,
        });
      }
    }
    this.cells = cells;

    // ── Robots: un rectángulo 1×2 por robot (cuerpo + punta) ──
    // Líneas de CSS grid son 1-based: la celda en coord c ocupa las líneas c+1..c+2.
    const rects: RobotRect[] = [];
    for (const r of this.robots) {
      const ori = r.orientacion ?? 'N';
      const off = TIP_OFFSET[ori] ?? [0, 1];
      const tx = r.x + off[0], ty = r.y + off[1];
      // Celda superior-izquierda del par (cuerpo, punta).
      const minX = Math.min(r.x, tx), minY = Math.min(r.y, ty);
      const horizontal = off[1] === 0; // E/O ocupan 2 columnas; N ocupa 2 filas
      rects.push({
        id: r.id,
        estado: r.estado,
        icon: robotStateShort(r.estado),
        ori,
        gridCol: horizontal ? `${minX + 1} / span 2` : `${minX + 1}`,
        gridRow: horizontal ? `${minY + 1}` : `${minY + 1} / span 2`,
        tipClass: `occ-heatmap__robot--tip-${ori.toLowerCase()}`,
      });
    }
    this.robotRects = rects;
  }
}
