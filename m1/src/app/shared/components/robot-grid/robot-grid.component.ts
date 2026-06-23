import { Component, Input, OnChanges, OnInit } from '@angular/core';
import {
  WsGrillaCell, WsRobotState, WsEstacion, WsConveyor, WsInterior,
} from '../../../core/models/state-bus-snapshot.model';
import { robotStateShort } from '../../../core/utils/robot-state.util';

interface HeatCell {
  key:       string;
  transito:  boolean;        // celda de tránsito (corredor, sin cajas)
  occ:       number;        // % ocupación de la columna (solo interior)
  color:     string;
  station:   string | null; // 'E' | 'O' (salida picking)
  conveyor:  boolean;       // conveyor de ingreso (Norte)
}

// Robot 1×2 dibujado como un rectángulo que ocupa sus dos celdas (cuerpo + punta).
interface RobotRect {
  id:       number;
  estado:   string;
  icon:     string;
  ori:      string;
  gridCol:  string;
  gridRow:  string;
  tipClass: string;
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
// Norte = arriba → la punta apunta a y menor.
const TIP_OFFSET: Record<string, [number, number]> = {
  N: [0, -1], E: [1, 0], O: [-1, 0],
};

@Component({
  selector: 'app-robot-grid',
  templateUrl: './robot-grid.component.html',
  styleUrls: ['./robot-grid.component.scss'],
  imports: [],
})
export class RobotGridComponent implements OnInit, OnChanges {
  @Input() gridZ   = 5;
  @Input() gridTotal: { x: number; y: number } | null = null;
  @Input() interior: WsInterior | null = null;
  @Input() grilla: WsGrillaCell[] = [];
  @Input() robots: WsRobotState[] = [];
  @Input() estaciones: WsEstacion[] = [];
  @Input() conveyorsNorte: WsConveyor[] = [];
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

  get cols(): number { return Math.min(this.gridTotal?.x ?? 14, 26); }
  get rows(): number { return Math.min(this.gridTotal?.y ?? 12, 24); }
  get colTemplate(): string { return `repeat(${this.cols}, 1fr)`; }
  get rowTemplate(): string { return `repeat(${this.rows}, 1fr)`; }

  ngOnInit(): void { this.rebuild(); }
  ngOnChanges(): void { this.rebuild(); }

  private esInterior(x: number, y: number): boolean {
    const i = this.interior;
    if (!i) return false;
    return x >= i.x0 && x <= i.x1 && y >= i.y0 && y <= i.y1;
  }

  private rebuild(): void {
    // ── Fondo: ocupación interior + estaciones + conveyors ──
    const boxCount = new Map<string, number>();
    for (const c of this.grilla) {
      const key = `${c.x}-${c.y}`;
      boxCount.set(key, (boxCount.get(key) ?? 0) + 1);
    }
    const estMap = new Map<string, string>();
    for (const e of this.estaciones) estMap.set(`${e.x}-${e.y}`, e.orientacion);
    const convSet = new Set<string>();
    for (const c of this.conveyorsNorte) convSet.add(`${c.x}-${c.y}`);

    const cells: HeatCell[] = [];
    for (let y = 0; y < this.rows; y++) {
      for (let x = 0; x < this.cols; x++) {
        const key = `${x}-${y}`;
        const interior = this.esInterior(x, y);
        const occ = interior ? ((boxCount.get(key) ?? 0) / this.gridZ) * 100 : 0;
        cells.push({
          key,
          transito: !interior,
          occ: Math.round(occ),
          color: occColor(occ),
          station: estMap.get(key) ?? null,
          conveyor: convSet.has(key),
        });
      }
    }
    this.cells = cells;

    // ── Robots: rectángulo 1×2 (cuerpo + punta) ──
    const rects: RobotRect[] = [];
    for (const r of this.robots) {
      const ori = r.orientacion ?? 'N';
      const off = TIP_OFFSET[ori] ?? [0, -1];
      const tx = r.x + off[0], ty = r.y + off[1];
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
