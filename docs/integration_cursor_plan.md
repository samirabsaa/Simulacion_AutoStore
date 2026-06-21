# Plan de Integración M2 → M1 — Implementación en Cursor

## Contexto

M2 (motor) serializa datos de simulación completos por tick vía WebSocket y REST
(`api/server.py`). M1 recibe estos datos pero descarta la mayoría:

| Dato que M2 envía | Lo que M1 hace | Gap |
|---|---|---|
| `grilla[]` (cajas por celda) | `unknown[]` — se ignora | No se muestra ocupación real por columna |
| `robots[]` (id, x, y, z, estado, carga_id) | Solo se usa `robots.length` | Posiciones/estados reales no se renderizan |
| `status: "FINISHED"` | Se lee pero no se distingue visualmente | Sin notificación de ola completa |
| `output/reporte_comp.csv` | No hay endpoint ni handler | Botones de descarga muertos |
| `BusState` actual | No hay forma de descargar config | Botón "Guardar config.json" muerto |

Archivos de referencia para entender el código actual:
- `m1/src/app/core/models/state-bus-snapshot.model.ts` — tipos del payload WS
- `m1/src/app/core/services/bus-client.service.ts` — store reactivo, `applyTick()`
- `m1/src/app/shared/components/robot-grid/robot-grid.component.ts` — heatmap (hoy fake)
- `m1/src/app/pages/dashboard/dashboard.page.ts` + `.html` — panel principal
- `m1/src/app/pages/grilla/grilla.page.ts` + `.html` — monitor de grilla
- `m1/src/app/pages/reportes/reportes.page.ts` + `.html` — página de reportes
- `m1/src/app/core/services/sim-api.service.ts` — llamadas HTTP al backend
- `api/server.py` — endpoints REST + WS
- `api/serializers.py` — mapeo M2→M1 de los datos que sí llegan

---

## Gap 1+2 — Ocupación real + posiciones reales de robots

### Archivos a modificar

| # | Archivo | Cambio |
|---|---|---|
| 1 | `state-bus-snapshot.model.ts` | Tipar `grilla` como `WsGrillaCell[]`, agregar interfaz |
| 2 | `bus-client.service.ts` | Agregar `robots`/`grilla` a `BusState`, propagar desde WS |
| 3 | `robot-grid.component.ts` | Nuevos inputs `gridZ`, `grilla`, `robots`; reemplazar fórmula fake |
| 4 | `robot-grid.component.html` | Agregar clase CSS según estado del robot |
| 5 | `robot-grid.component.scss` | Variantes de color por estado |
| 6 | `dashboard.page.html` | Actualizar bindings de `<app-robot-grid>` |
| 7 | `grilla.page.html` | Actualizar bindings de `<app-robot-grid>` |

### 1. `state-bus-snapshot.model.ts`

Agregar interfaz y retipar campo existente:

```typescript
export interface WsGrillaCell {
  id_caja:  string;
  id_sku:   string;
  cantidad: number;
  x:        number;
  y:        number;
  z:        number;
}
```

En `WsTickPayload`, cambiar:
```typescript
grilla:    WsGrillaCell[];       // antes: unknown[]
pedidos:   { cola: PedidoItem[]; completados: PedidoItem[] };
```

`WsRobotState` ya está correctamente tipado — no tocar.

### 2. `bus-client.service.ts`

Agregar `robots` y `grilla` a la interfaz `BusState`:

```typescript
import { WsRobotState, WsGrillaCell } from '../models/state-bus-snapshot.model';

export interface BusState {
  // ... existentes ...
  robots: WsRobotState[];
  grilla: WsGrillaCell[];
}
```

En `INITIAL_STATE`, agregar campos vacíos:
```typescript
robots: [],
grilla: [],
```

En `applyTick()`, propagar desde el mensaje:
```typescript
robots: msg.robots ?? s.robots,
grilla: msg.grilla ?? s.grilla,
```

### 3. `robot-grid.component.ts`

Cambiar inputs:
```typescript
@Input() gridX   = 12;
@Input() gridY   = 10;
@Input() gridZ   = 5;
@Input() grilla: WsGrillaCell[] = [];
@Input() robots: WsRobotState[] = [];
@Input() tick    = 0;
```

Importar `WsGrillaCell` y `WsRobotState`.

Eliminar `localTick`, `animId`, `ngOnInit` (el `setInterval`) y `ngOnDestroy` (el `clearInterval`).

Nueva `rebuildCells()`:

```typescript
private rebuildCells(): void {
  const gx = this.cols;
  const gy = this.rows;

  // Contar cajas por columna (x,y)
  const boxCount = new Map<string, number>();
  for (const c of this.grilla) {
    const key = `${c.x}-${c.y}`;
    boxCount.set(key, (boxCount.get(key) ?? 0) + 1);
  }

  // Índice de robots por celda (x,y)
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
```

Agregar función helper fuera del componente:
```typescript
function estadoIcon(estado: string): string {
  switch (estado) {
    case 'IDLE':       return '.';
    case 'MOVING':     return '>';
    case 'PICKING':    return 'E';
    case 'BLOCKED':    return '!';
    case 'DEPOSITING': return 'D';
    default:           return '?';
  }
}
```

Agregar `robotEstado` y `robotIcon` a la interfaz `HeatCell`:
```typescript
interface HeatCell {
  key:      string;
  occ:      number;
  hasRobot: boolean;
  robotId:  number;
  robotEstado: string;
  robotIcon:   string;
  color:    string;
}
```

Quitar imports de `OnInit` y `OnDestroy` ya no necesarios.

### 4. `robot-grid.component.html`

Agregar clase condicional al badge del robot:
```html
@if (cell.hasRobot) {
  <div class="occ-heatmap__robot"
       [class.occ-heatmap__robot--idle]="cell.robotEstado === 'IDLE'"
       [class.occ-heatmap__robot--moving]="cell.robotEstado === 'MOVING'"
       [class.occ-heatmap__robot--picking]="cell.robotEstado === 'PICKING'"
       [class.occ-heatmap__robot--blocked]="cell.robotEstado === 'BLOCKED'"
       [class.occ-heatmap__robot--depositing]="cell.robotEstado === 'DEPOSITING'">
    {{ cell.robotId }}{{ cell.robotIcon }}
  </div>
}
```

### 5. `robot-grid.component.scss`

Agregar variantes de color para el badge:
```scss
&__robot {
  // ... base existente ...
  &--blocked    { background: #ef4444; }
  &--moving     { background: #3b82f6; }
  &--picking    { background: #f59e0b; }
  &--depositing { background: #22c55e; }
  &--idle       { background: #6b7280; }
}
```

### 6. `dashboard.page.html`

Reemplazar bindings de `<app-robot-grid>`:
```html
<app-robot-grid
  [gridX]="bus.grid.x"
  [gridY]="bus.grid.y"
  [gridZ]="bus.grid.z"
  [grilla]="bus.grilla"
  [robots]="bus.robots"
  [tick]="bus.tick">
</app-robot-grid>
```

Quitar `[numRobots]` e `[iog]`.

### 7. `grilla.page.html`

Misma actualización que dashboard:
```html
<app-robot-grid
  [gridX]="bus.grid.x"
  [gridY]="bus.grid.y"
  [gridZ]="bus.grid.z"
  [grilla]="bus.grilla"
  [robots]="bus.robots"
  [tick]="bus.tick">
</app-robot-grid>
```

---

## Gap 3 — Toast de simulación completada (FINISHED)

### Archivos a modificar

| # | Archivo | Cambio |
|---|---|---|
| 8 | `dashboard.page.ts` | Detectar transición a `FINISHED`, mostrar toast dismissible |
| 9 | `dashboard.page.html` | Marup del toast |
| 10 | `dashboard.page.scss` | Estilos del toast |

### 8. `dashboard.page.ts`

Agregar imports:
```typescript
import { SimStatus } from '../../core/enums/sim.enums';
import { RouterLink } from '@angular/router';
```

Agregar campo y lógica:
```typescript
showFinishedToast = false;

ngOnInit(): void {
  this.sub = this.busService.bus$.subscribe(s => {
    if (s.status === SimStatus.FINISHED && (!this.bus || this.bus.status !== SimStatus.FINISHED)) {
      this.showFinishedToast = true;
    }
    this.bus = s;
  });
}

dismissToast(): void {
  this.showFinishedToast = false;
}
```

Agregar `RouterLink` al arreglo `imports` del `@Component`.

### 9. `dashboard.page.html`

Agregar antes del primer `@if (bus)`:
```html
@if (showFinishedToast) {
  <div class="panel__toast panel__toast--success">
    <div class="panel__toast-body">
      <strong>Ola completada</strong> — todos los pedidos entregados.
      <a routerLink="/reportes" class="panel__toast-link">Ver reporte</a>
    </div>
    <button class="panel__toast-close" (click)="dismissToast()">✕</button>
  </div>
}
```

### 10. `dashboard.page.scss`

```scss
.panel__toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-radius: 10px;
  font-size: 14px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  max-width: 420px;

  &--success {
    background: #065f46;
    color: #fff;
    border: 1px solid #059669;
  }

  &-body {
    flex: 1;
  }

  &-link {
    color: #6ee7b7;
    text-decoration: underline;
    margin-left: 4px;
    font-weight: 600;
  }

  &-close {
    background: none;
    border: none;
    color: #fff;
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
    opacity: 0.7;
    &:hover { opacity: 1; }
  }
}
```

---

## Gap 4 — Descarga de reportes

### Archivos a modificar

| # | Archivo | Cambio |
|---|---|---|
| 11 | `api/server.py` | Agregar `GET /report/comparativo` y `GET /report/sesion` |
| 12 | `sim-api.service.ts` | Agregar métodos de descarga |
| 13 | `reportes.page.ts` | Agregar handlers |
| 14 | `reportes.page.html` | Wirear `(click)` en botones |

### 11. `api/server.py`

Agregar al inicio:
```python
from pathlib import Path
from fastapi.responses import FileResponse

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
```

Agregar endpoints:
```python
@app.get("/report/comparativo")
def get_report_comparativo():
    path = OUTPUT_DIR / "reporte_comp.csv"
    if not path.exists():
        raise HTTPException(404, "reporte_comp.csv no existe aún")
    return FileResponse(
        path,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reporte_comp.csv"},
    )


@app.get("/report/sesion")
def get_report_sesion():
    csvs = sorted(OUTPUT_DIR.glob("sesion_*.csv"), reverse=True)
    if not csvs:
        raise HTTPException(404, "No hay sesión guardada aún")
    path = csvs[0]
    return FileResponse(
        path,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={path.name}"},
    )
```

### 12. `sim-api.service.ts`

Agregar:
```typescript
downloadComparativo(): void {
  window.open(`${environment.apiUrl}/report/comparativo`, '_blank');
}

exportSesion(): void {
  window.open(`${environment.apiUrl}/report/sesion`, '_blank');
}
```

### 13. `reportes.page.ts`

```typescript
import { SimApiService } from '../../core/services/sim-api.service';

export class ReportesPage implements OnInit, OnDestroy {
  constructor(
    private busService: BusClientService,
    private simApi: SimApiService,
  ) {}

  downloadComparativo(): void {
    this.simApi.downloadComparativo();
  }

  exportSesion(): void {
    this.simApi.exportSesion();
  }
}
```

### 14. `reportes.page.html`

Agregar `(click)` handlers a ambos botones:
```html
<button (click)="downloadComparativo()" style="...">⬇ Descargar</button>
<!-- ... -->
<button (click)="exportSesion()" style="...">⬇ Exportar sesión</button>
```

---

## Gap 5 — Guardar config.json

### Archivos a modificar

| # | Archivo | Cambio |
|---|---|---|
| 15 | `config.page.ts` | Agregar método `guardarConfig()` |
| 16 | `config.page.html` | Cambiar `(click)="null"` |

### 15. `config.page.ts`

Agregar:
```typescript
guardarConfig(): void {
  const s = this.busService.state;
  const data = {
    x: s.grid.x,
    y: s.grid.y,
    z: s.grid.z,
    robots: s.numRobots,
    ocupacion: s.ocupacionInicial / 100,
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'config.json';
  a.click();
  URL.revokeObjectURL(url);
}
```

### 16. `config.page.html`

Buscar el botón con `(click)="null"` y reemplazar:
```html
<button (click)="guardarConfig()">Guardar config.json</button>
```

---

## Resumen de archivos a modificar (16 total)

| # | Archivo | Gap |
|---|---|---|
| 1 | `state-bus-snapshot.model.ts` | 1+2 |
| 2 | `bus-client.service.ts` | 1+2 |
| 3 | `robot-grid.component.ts` | 1+2 |
| 4 | `robot-grid.component.html` | 1+2 |
| 5 | `robot-grid.component.scss` | 1+2 |
| 6 | `dashboard.page.html` | 1+2, 3 |
| 7 | `grilla.page.html` | 1+2 |
| 8 | `dashboard.page.ts` | 3 |
| 9 | `dashboard.page.scss` | 3 |
| 10 | `api/server.py` | 4 |
| 11 | `sim-api.service.ts` | 4 |
| 12 | `reportes.page.ts` | 4 |
| 13 | `reportes.page.html` | 4 |
| 14 | `config.page.ts` | 5 |
| 15 | `config.page.html` | 5 |

Sin archivos nuevos, sin cambios a módulos Angular (todos standalone).
