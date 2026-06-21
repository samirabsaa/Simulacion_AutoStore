import { Component, Input, OnChanges, OnInit, OnDestroy } from '@angular/core';

interface HeatCell {
  key:      string;
  occ:      number;
  hasRobot: boolean;
  robotId:  number;
  color:    string;
}

function occColor(o: number): string {
  if (o < 20) return 'var(--occ-1)';
  if (o < 40) return 'var(--occ-2)';
  if (o < 60) return 'var(--occ-3)';
  if (o < 80) return 'var(--occ-4)';
  return 'var(--occ-5)';
}

@Component({
  selector: 'app-robot-grid',
  templateUrl: './robot-grid.component.html',
  styleUrls: ['./robot-grid.component.scss'],
  imports: [],
})
export class RobotGridComponent implements OnInit, OnChanges, OnDestroy {
  @Input() gridX    = 12;
  @Input() gridY    = 10;
  @Input() numRobots = 8;
  @Input() iog       = 78;
  @Input() tick      = 0;

  cells: HeatCell[] = [];
  // Contador local para animar cuando el backend no envía ticks.
  private localTick = 0;
  private animId?: ReturnType<typeof setInterval>;

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

  ngOnInit(): void {
    this.localTick = this.tick;
    // Anima localmente a 1 Hz. ngOnChanges sincroniza localTick cuando llega tick real.
    this.animId = setInterval(() => {
      this.localTick++;
      this.rebuildCells();
    }, 1000);
  }

  ngOnChanges(): void {
    // Cuando el WS envía un tick real, sincronizamos y reconstruimos de inmediato.
    this.localTick = this.tick;
    this.rebuildCells();
  }

  ngOnDestroy(): void {
    clearInterval(this.animId);
  }

  private rebuildCells(): void {
    const gx = this.cols;
    const gy = this.rows;
    const t  = this.localTick;
    const result: HeatCell[] = [];
    for (let y = 0; y < gy; y++) {
      for (let x = 0; x < gx; x++) {
        const base = ((x * 7 + y * 13 + (x ^ y) * 5) % 100);
        const occ  = Math.max(0, Math.min(100, base * 0.45 + this.iog * 0.55));
        const hasRobot = (x * 3 + y * 5 + t) % 19 === 0 && (x + y) % 2 === 0;
        const robotId  = ((x + y) % this.numRobots) + 1;
        result.push({ key: `${x}-${y}`, occ, hasRobot, robotId, color: occColor(occ) });
      }
    }
    this.cells = result;
  }
}
