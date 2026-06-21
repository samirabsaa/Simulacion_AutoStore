import { Component, Input, OnChanges, OnInit } from '@angular/core';
import { WsGrillaCell, WsRobotState } from '../../../core/models/state-bus-snapshot.model';
import { robotStateShort } from '../../../core/utils/robot-state.util';

interface HeatCell {
  key:         string;
  occ:         number;
  hasRobot:    boolean;
  robotId:     number;
  robotEstado: string;
  robotIcon:   string;
  color:       string;
}

function occColor(o: number): string {
  if (o < 20) return 'var(--occ-1)';
  if (o < 40) return 'var(--occ-2)';
  if (o < 60) return 'var(--occ-3)';
  if (o < 80) return 'var(--occ-4)';
  return 'var(--occ-5)';
}

function estadoIcon(estado: string): string {
  return robotStateShort(estado);
}

@Component({
  selector: 'app-robot-grid',
  templateUrl: './robot-grid.component.html',
  styleUrls: ['./robot-grid.component.scss'],
  imports: [],
})
export class RobotGridComponent implements OnInit, OnChanges {
  @Input() gridX   = 12;
  @Input() gridY   = 10;
  @Input() gridZ   = 5;
  @Input() grilla: WsGrillaCell[] = [];
  @Input() robots: WsRobotState[] = [];
  @Input() tick    = 0;

  cells: HeatCell[] = [];

  readonly ramp = [
    { label: '0–20%',   cssVar: '--occ-1' },
    { label: '20–40%',  cssVar: '--occ-2' },
    { label: '40–60%',  cssVar: '--occ-3' },
    { label: '60–80%',  cssVar: '--occ-4' },
    { label: '80–100%', cssVar: '--occ-5' },
  ];

  get cols(): number { return Math.min(this.gridX, 14); }
  get rows(): number { return Math.min(this.gridY, 12); }
  get colTemplate(): string { return `repeat(${this.cols}, 1fr)`; }

  readonly stateLegend = [
    { mod: 'idle',       label: 'Inactivo' },
    { mod: 'moving',     label: 'Moviendo' },
    { mod: 'picking',    label: 'Excavando' },
    { mod: 'blocked',    label: 'Bloqueado' },
    { mod: 'depositing', label: 'Entregando' },
  ];

  ngOnInit(): void {
    this.rebuildCells();
  }

  ngOnChanges(): void {
    this.rebuildCells();
  }

  private rebuildCells(): void {
    const gx = this.cols;
    const gy = this.rows;

    const boxCount = new Map<string, number>();
    for (const c of this.grilla) {
      const key = `${c.x}-${c.y}`;
      boxCount.set(key, (boxCount.get(key) ?? 0) + 1);
    }

    const robotMap = new Map<string, { id: number; estado: string }>();
    for (const r of this.robots) {
      robotMap.set(`${r.x}-${r.y}`, { id: r.id, estado: r.estado });
    }

    const result: HeatCell[] = [];
    for (let y = 0; y < gy; y++) {
      for (let x = 0; x < gx; x++) {
        const key = `${x}-${y}`;
        const occ = ((boxCount.get(key) ?? 0) / this.gridZ) * 100;
        const rob = robotMap.get(key);
        result.push({
          key,
          occ: Math.round(occ),
          hasRobot: !!rob,
          robotId: rob?.id ?? 0,
          robotEstado: rob?.estado ?? '',
          robotIcon: estadoIcon(rob?.estado ?? ''),
          color: occColor(occ),
        });
      }
    }
    this.cells = result;
  }
}
