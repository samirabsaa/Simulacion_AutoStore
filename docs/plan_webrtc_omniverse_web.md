# Plan de Integración: M3 (Omniverse 3D) → M1 (Página Web)

> **Fecha:** 2026-06-10
> **Responsable:** Manuel Aguilera
> **Plazo estimado:** ~3.5 horas (A1 iframe) / ~5.5 horas (A2 WebRTC lib)

---

## 1. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                     APLICACIÓN WEB (M1)                         │
│                     localhost:8100                               │
│                                                                 │
│  ┌──────────────────┐      ┌─────────────────────────────────┐  │
│  │   Dashboard       │      │   Omniverse Viewport            │  │
│  │   - KPIs en vivo  │      │   - Stream WebRTC embebido      │  │
│  │   - Play/Pause    │      │   - Solo lectura                │  │
│  │   - Config        │      │   - iframe o lib @nvidia        │  │
│  └────────┬─────────┘      └──────────────┬──────────────────┘  │
└───────────┼───────────────────────────────┼─────────────────────┘
            │ WebSocket                     │ WebRTC
            │ ws://localhost:8000/ws/state   │ http://localhost:8200
            ▼                               ▼
┌───────────────────┐           ┌──────────────────────────────┐
│   FastAPI Bridge   │           │   USD Composer (M3)          │
│   localhost:8000   │           │   - Script Python en editor  │
│                   │           │   - Renderiza escena USD     │
│   Endpoints:      │           │   - Ext WebRTC sirve stream  │
│   - /ws/state     │           │   Puerto: 8200               │
│   - /config       │           └──────────────┬───────────────┘
│   - /control/*    │                          │
│   - /snapshot     │                          │ Lee del Bus
│   - /api/upload/* │                          │ (read_snapshot)
└────────┬──────────┘                          │
         │                                     │
         │  write_tick_delta (único escritor)  │
         ▼                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STATE BUS (Memoria)                           │
│                    threading.Lock por tick                       │
│                                                                 │
│   - Config: grilla (x,y,z), robots, ocupacion                  │
│   - Grilla: cajas con posición (x,y,z) y SKU                   │
│   - Robots: posición, estado, carga                             │
│   - Pedidos: cola + completados                                 │
│   - KPIs: TSP, MTRP, TBR, IOG, etc.                           │
│   - Modo: diurno / nocturno                                     │
│   - Política: fifo / prioridad_posicion                         │
└──────────┬──────────────────────────┬──────────────────────────┘
           │                          │
           │ Lee (reader)             │ Lee (reader)
           ▼                          ▼
┌─────────────────────┐    ┌─────────────────────────────────────┐
│   MOTOR (M2)         │    │   M3 — Visualización 3D             │
│   Python puro        │    │   Script en USD Composer             │
│                      │    │                                     │
│   Cada tick:         │    │   Cada frame:                       │
│   1. Lee snapshot    │    │   1. Lee snapshot                   │
│   2. Calcula lógica  │    │   2. Actualiza escena USD           │
│   3. Escribe delta   │    │   3. Renderiza viewport             │
│                      │    │                                     │
│   ÚNICO ESCRITOR     │    │   SOLO LECTOR                       │
└─────────────────────┘    └─────────────────────────────────────┘
```

**Regla crítica:** M2 y M3 **no se comunican directamente**. Están desacoplados por el Bus. Si M3 falla, M2 sigue operando.

---

## 2. Flujo de configuración

```
config.json (define grilla, robots, ocupación)
    │
    ▼
M1 (web) carga → POST /config → FastAPI → Bus
    │
    ▼
Bus almacena la config
    │
    ├──▶ M2 lee config → inicializa simulación
    │    (grilla de trabajo, robots, lógica)
    │
    └──▶ M3 lee config → crea escena USD
         (dimensiones, cantidad de robots, cajas iniciales)
```

| Campo config.json | Efecto en M2 | Efecto en M3 |
|-------------------|-------------|-------------|
| `x`, `y`, `z` | Dimensiones de grilla de simulación | Tamaño de escena USD |
| `robots` | Robots que controla el despachador | Esferas que renderiza |
| `ocupacion` | Cajas iniciales en la grilla | Cajas visibles en escena |

> Si en el futuro se necesitan configuraciones visuales exclusivas de M3 (colores, cámara, estilo), van en un archivo separado (`config_m3.json`), no en `config.json`.

---

## 3. Flujo de datos por tick

```
┌─────────────────────────────────────────────────────────────┐
│ TICK N                                                       │
│                                                              │
│  M2 (Motor):                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. snap = bus.read_snapshot()                       │    │
│  │ 2. Calcula movimientos, pedidos, colisiones, KPIs   │    │
│  │ 3. delta = TickDelta(grilla, robots, kpis, eventos) │    │
│  │ 4. bus.write_tick_delta("M2", delta)                │    │
│  │    → Lock → aplicar → actualizar snapshot → unlock  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  M3 (Omniverse):                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. snap = bus.read_snapshot()                       │    │
│  │ 2. Para cada caja: crear/mover cube USD en (x,y,z) │    │
│  │ 3. Para cada robot: mover esfera + color por estado │    │
│  │ 4. viewport.render()                                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  WebRTC:                                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. Captura frames del viewport de USD Composer      │    │
│  │ 2. Codifica y envía stream al navegador             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  M1 (Web):                                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. Recibe WebSocket {type: "tick", ...}             │    │
│  │ 2. Actualiza KPIs, estado robots, pedidos           │    │
│  │ 3. iframe muestra viewport 3D en tiempo real        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Prerrequisitos

| Componente | Versión mínima | Verificación |
|------------|---------------|--------------|
| USD Composer | 2023.1.x – 2024.x | `Help > About` |
| NVIDIA RTX GPU | Cualquier modelo RTX | `nvidia-smi` |
| Node.js | ≥ 20.18.1 | `node -v` |
| npm | ≥ 10.2.3 | `npm -v` |
| Python | 3.10+ | `python --version` |
| Chrome/Chromium | Última versión | `chrome://version` |

### Extensiones de Omniverse (habilitar en Extension Manager)

| Extensión | Función | Viene por defecto |
|-----------|---------|-------------------|
| `omni.kit.livestream.app` | Configuración de streaming | Sí |
| `omni.kit.livestream.webrtc` | Servidor WebRTC | Sí |
| `omni.services.livestream.webrtc` | Interfaz web + REST API | Sí |

---

## 5. FASE 1: Configurar streaming en USD Composer (~30 min)

### Paso 1.1 — Habilitar extensiones

1. Abrir USD Composer
2. **Window > Extensions**
3. Buscar `livestream` y verificar que estén habilitadas:
   - [x] `omni.kit.livestream.app`
   - [x] `omni.kit.livestream.webrtc`
   - [x] `omni.services.livestream.webrtc`

### Paso 1.2 — Configurar puerto

1. Extension Manager → `omni.services.transport.server.http`
2. Puerto por defecto: **8200**
3. Agregar `http://localhost:8100` a orígenes permitidos (CORS)

### Paso 1.3 — Probar streaming

1. Chrome → `http://localhost:8200`
2. Seleccionar "Primary App Stream" → **Connect**
3. Verificar: viewport 3D visible, cámara funciona

**Criterio de éxito:** Se ve el viewport de USD Composer en el navegador.

---

## 6. FASE 2: Componente Angular (~30 min – 3 horas)

### Opción A1 — iframe (recomendada, ~30 min)

#### Generar componente
```bash
cd m1
npx ng generate component shared/omniverse-viewport --standalone
```

#### Template (`omniverse-viewport.component.html`)
```html
<div class="viewport-wrapper">
  <div class="viewport-header">
    <span class="viewport-title">Omniverse 3D Viewport</span>
    <span class="viewport-status" [class.connected]="isConnected">
      {{ isConnected ? 'Conectado' : 'Desconectado' }}
    </span>
  </div>
  <div class="viewport-container">
    <iframe
      [src]="safeStreamUrl"
      frameborder="0"
      allow="fullscreen; autoplay"
      title="Omniverse 3D Viewport"
      (load)="onFrameLoad()"
      (error)="onFrameError()">
    </iframe>
    <div class="viewport-overlay" *ngIf="!isConnected">
      <p>Abrir <code>http://localhost:8200</code> para iniciar el stream</p>
    </div>
  </div>
</div>
```

#### Componente (`omniverse-viewport.component.ts`)
```typescript
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-omniverse-viewport',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './omniverse-viewport.component.html',
  styleUrls: ['./omniverse-viewport.component.scss']
})
export class OmniverseViewportComponent implements OnInit {
  safeStreamUrl!: SafeResourceUrl;
  isConnected = false;
  private streamUrl = environment.omniverseStreamUrl || 'http://localhost:8200';

  constructor(private sanitizer: DomSanitizer) {}

  ngOnInit(): void {
    this.safeStreamUrl = this.sanitizer.bypassSecurityTrustResourceUrl(this.streamUrl);
  }

  onFrameLoad(): void { this.isConnected = true; }
  onFrameError(): void { this.isConnected = false; }
}
```

#### Estilos (`omniverse-viewport.component.scss`)
```scss
.viewport-wrapper {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  border: 1px solid var(--ion-color-light);
  border-radius: 8px;
  overflow: hidden;
  background: #1a1a1a;
}

.viewport-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #2a2a2a;
  border-bottom: 1px solid #3a3a3a;
}

.viewport-title {
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.viewport-status {
  font-size: 11px;
  color: #ff4444;

  &.connected {
    color: #44ff44;
  }
}

.viewport-container {
  position: relative;
  flex: 1;
  min-height: 400px;

  iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
}

.viewport-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.8);
  color: #fff;
  text-align: center;

  code {
    background: #3a3a3a;
    padding: 2px 6px;
    border-radius: 4px;
  }
}
```

#### Variable de entorno (`environment.ts`)
```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
  wsUrl: 'ws://localhost:8000/ws/state',
  omniverseStreamUrl: 'http://localhost:8200'
};
```

#### Agregar al dashboard (`dashboard.page.html`)
```html
<div class="dashboard-grid">
  <div class="kpi-panel">
    <!-- KPIs y controles existentes -->
  </div>
  <div class="viewport-panel">
    <app-omniverse-viewport></app-omniverse-viewport>
  </div>
</div>
```

```scss
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 16px;
  height: 100%;
}

.viewport-panel {
  min-height: 500px;
}
```

---

### Opción A2 — WebRTC Library (completa, ~2-3 horas)

Para interactividad (controles de cámara, selección de objetos).

#### Configurar registry NVIDIA (`m1/.npmrc`)
```
@nvidia:registry=https://edge.urm.nvidia.com/artifactory/api/npm/omniverse-client-npm/
```

#### Instalar
```bash
cd m1
npm install @nvidia/ov-web-rtc
```

#### Servicio (`omniverse-stream.service.ts`)
```typescript
import { Injectable, OnDestroy } from '@angular/core';
import { AppStreamer, StreamType, LogLevel } from '@nvidia/ov-web-rtc';

@Injectable({ providedIn: 'root' })
export class OmniverseStreamService implements OnDestroy {
  private appStreamer: AppStreamer | null = null;
  private isConnected = false;

  connect(container: HTMLElement): void {
    if (this.isConnected) return;
    this.appStreamer = new AppStreamer();

    const streamConfig = {
      streamSource: StreamType.DIRECT,
      logLevel: LogLevel.INFO,
      streamConfig: {
        server: 'localhost',
        width: 1920,
        height: 1080,
        fps: 30,
        onStart: () => {
          console.log('[Omniverse] Stream started');
          this.isConnected = true;
        },
        onStop: () => {
          console.log('[Omniverse] Stream stopped');
          this.isConnected = false;
        },
        onError: (error: any) => {
          console.error('[Omniverse] Stream error:', error);
        }
      }
    };

    this.appStreamer.connect(
      streamConfig,
      container,
      this.handleCustomEvent.bind(this)
    );
  }

  disconnect(): void {
    if (this.appStreamer) {
      this.appStreamer.disconnect();
      this.appStreamer = null;
      this.isConnected = false;
    }
  }

  getConnectionStatus(): boolean {
    return this.isConnected;
  }

  private handleCustomEvent(event: any): void {
    if (!event) return;
    console.log('[Omniverse] Custom event:', event);
  }

  ngOnDestroy(): void {
    this.disconnect();
  }
}
```

#### Componente (`omniverse-viewport.component.ts`)
```typescript
import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewInit,
  OnDestroy
} from '@angular/core';
import { OmniverseStreamService } from '../../core/services/omniverse-stream.service';

@Component({
  selector: 'app-omniverse-viewport',
  template: `
    <div class="viewport-wrapper">
      <div class="viewport-header">
        <span>Omniverse 3D Viewport</span>
        <span [class.connected]="isConnected">
          {{ isConnected ? 'Conectado' : 'Desconectado' }}
        </span>
      </div>
      <div #viewportContainer
           class="viewport-container"
           tabindex="0">
      </div>
    </div>
  `,
  styleUrls: ['./omniverse-viewport.component.scss']
})
export class OmniverseViewportComponent implements AfterViewInit, OnDestroy {
  @ViewChild('viewportContainer') container!: ElementRef;
  isConnected = false;

  constructor(private streamService: OmniverseStreamService) {}

  ngAfterViewInit(): void {
    this.streamService.connect(this.container.nativeElement);
  }

  ngOnDestroy(): void {
    this.streamService.disconnect();
  }
}
```

> **Importante:** `tabIndex={0}` es **obligatorio** para que teclado y mouse funcionen en el viewport.

---

## 7. FASE 3: Script M3 para USD Composer (~2 horas)

Este script corre en el Script Editor de USD Composer. Lee el Bus y renderiza la escena 3D.

### Script completo

```python
# M3 — Script de visualización para USD Composer
# Ejecutar en: Window > Script Editor
#
# Este script lee el estado del Bus y renderiza la escena 3D.
# Debe ejecutarse DESPUÉS de que M2 haya inicializado la simulación.

from pxr import Usd, UsdGeom, Gf
import omni.usd
import omni.kit.viewport.utility as vp_util
import time

# Colores por estado de robot
COLORES_ROBOT = {
    "inactivo":       Gf.Vec3f(0.5, 0.5, 0.5),
    "desplazandose":  Gf.Vec3f(0.0, 1.0, 1.0),
    "excavando":      Gf.Vec3f(1.0, 1.0, 0.0),
    "recuperando":    Gf.Vec3f(0.0, 1.0, 0.0),
    "entregando":     Gf.Vec3f(1.0, 0.0, 1.0),
    "reponiendo":     Gf.Vec3f(0.0, 0.0, 1.0),
    "bloqueado":      Gf.Vec3f(1.0, 0.0, 0.0),
}

COLORES_CAJA = {
    "SKU-A": Gf.Vec3f(0.8, 0.2, 0.2),
    "SKU-B": Gf.Vec3f(0.2, 0.8, 0.2),
    "SKU-C": Gf.Vec3f(0.2, 0.2, 0.8),
}
COLOR_DEFAULT_CAJA = Gf.Vec3f(0.6, 0.6, 0.6)


def crear_escena_base(stage, config):
    world = UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Cube.Define(stage, "/World/_templates/Cube")
    UsdGeom.Sphere.Define(stage, "/World/_templates/Robot")
    dome = UsdGeom.DomeLight.Define(stage, "/World/DomeLight")
    dome.CreateIntensityAttr(1000)
    return world


def crear_robot(stage, robot_id, x, y, z, estado):
    path = f"/World/Robot_{robot_id}"
    prim = stage.GetPrimAtPath(path)
    color = COLORES_ROBOT.get(estado, Gf.Vec3f(0.5, 0.5, 0.5))

    if not prim.IsValid():
        sphere = UsdGeom.Sphere.Define(stage, path)
        sphere.CreateRadiusAttr(0.4)
        sphere.CreateDisplayColorAttr([color])
        prim = sphere.GetPrim()
    else:
        prim.GetAttribute("primvars:displayColor").Set([color])

    xformable = UsdGeom.Xformable(prim)
    xformable.AddTranslateOp().Set(Gf.Vec3d(float(x), float(y), float(z) + 0.5))
    return prim


def crear_caja(stage, caja_id, sku, x, y, z):
    path = f"/World/Caja_{caja_id}"
    prim = stage.GetPrimAtPath(path)
    color = COLORES_CAJA.get(sku, COLOR_DEFAULT_CAJA)

    if not prim.IsValid():
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(0.8)
        cube.CreateDisplayColorAttr([color])
        prim = cube.GetPrim()
    else:
        prim.GetAttribute("primvars:displayColor").Set([color])

    xformable = UsdGeom.Xformable(prim)
    xformable.AddTranslateOp().Set(Gf.Vec3d(float(x), float(y), float(z) + 0.5))
    return prim


class M3Renderer:
    def __init__(self, bus):
        self.bus = bus
        self.stage = omni.usd.get_context().get_stage()
        self.tick_anterior = -1
        self.cajas_activas = set()
        self.robots_activos = set()

    def inicializar(self):
        snap = self.bus.read_snapshot()
        config = {
            "x": snap.config.grilla.x if snap.config else 5,
            "y": snap.config.grilla.y if snap.config else 5,
        }
        crear_escena_base(self.stage, config)
        print(f"[M3] Escena inicializada: {config['x']}x{config['y']}")

    def actualizar(self):
        snap = self.bus.read_snapshot()
        if snap.tick == self.tick_anterior:
            return False
        self.tick_anterior = snap.tick

        cajas_nuevas = set()
        robots_nuevos = set()

        for caja in snap.grilla:
            path = f"/World/Caja_{caja.id_caja}"
            cajas_nuevas.add(path)
            crear_caja(self.stage, caja.id_caja, caja.id_sku, caja.x, caja.y, caja.z)

        for robot in snap.robots:
            path = f"/World/Robot_{robot.id}"
            robots_nuevos.add(path)
            crear_robot(self.stage, robot.id, robot.x, robot.y, robot.z, robot.estado.value)

        # Limpiar elementos que desaparecieron
        for path in self.cajas_activas - cajas_nuevas:
            self.stage.RemovePrim(path)
        for path in self.robots_activos - robots_nuevos:
            self.stage.RemovePrim(path)

        self.cajas_activas = cajas_nuevas
        self.robots_activos = robots_nuevos
        return True

    def ejecutar(self, intervalo=0.05):
        print("[M3] Iniciando loop de renderizado...")
        viewport = vp_util.get_viewport_from_window()
        try:
            while True:
                if self.actualizar():
                    viewport.render()
                time.sleep(intervalo)
        except KeyboardInterrupt:
            print("[M3] Detenido")


# Conectar al Bus y ejecutar
from bus_persistencia.bus.state_bus import StateBus
bus = StateBus()
renderer = M3Renderer(bus)
renderer.inicializar()
renderer.ejecutar()
```

### Ejecutar

1. USD Composer → **Window > Script Editor**
2. Pegar el script
3. Ejecutar (Ctrl+Enter)
4. La escena USD se crea y empieza a renderizar

---

## 8. FASE 4: Verificación end-to-end (~30 min)

### Checklist

| # | Paso | Esperado | Estado |
|---|------|----------|--------|
| 1 | FastAPI corriendo | `uvicorn api.server:app --reload --port 8000` | [ ] |
| 2 | Ionic corriendo | `cd m1 && ionic serve` → localhost:8100 | [ ] |
| 3 | USD Composer abierto | Ventana visible | [ ] |
| 4 | Extensiones habilitadas | `livestream.*` en Extension Manager | [ ] |
| 5 | Streaming funciona | `localhost:8200` muestra viewport en Chrome | [ ] |
| 6 | Script M3 ejecutando | Robots y cajas visibles en USD Composer | [ ] |
| 7 | Web muestra viewport | iframe/lib en la web muestra la escena | [ ] |
| 8 | Play funciona | Botón Play en web avanza la simulación | [ ] |
| 9 | Robots se mueven | Robots cambian de posición en USD Composer | [ ] |
| 10 | KPIs se actualizan | Dashboard muestra KPIs cambiando | [ ] |

### Prueba de estabilidad (5 minutos)

- [ ] Stream no se corta
- [ ] Cámara responde al mouse
- [ ] Sin errores en consola del navegador (F12)
- [ ] Sin errores en log de USD Composer
- [ ] Web funciona al cambiar de pestaña y volver

---

## 9. Plan B: Alternativa si WebRTC falla (~2 horas)

Si el streaming WebRTC no funciona por firewall, versiones incompatibles, etc.

### Endpoint de captura en FastAPI
```python
# Agregar en api/server.py

import subprocess
from pathlib import Path
from fastapi.responses import FileResponse

CAPTURE_DIR = Path("C:/temp/omniverse_captures")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/viewport")
async def get_viewport():
    """Retorna la última captura del viewport como imagen."""
    capture_path = CAPTURE_DIR / "viewport_capture.png"
    if capture_path.exists():
        return FileResponse(capture_path, media_type="image/png")
    return {"error": "No capture available"}
```

### Script de captura en USD Composer
```python
import omni.kit.viewport.utility as vp_util
import time

while True:
    viewport = vp_util.get_viewport_from_window()
    viewport.save("C:/temp/omniverse_captures/viewport_capture.png")
    time.sleep(0.5)
```

### Componente web
```typescript
@Component({
  template: `
    <img
      [src]="viewportUrl + '?t=' + timestamp"
      (load)="onLoad()"
      alt="Viewport"
      class="viewport-image"
    />
  `
})
export class OmniverseViewportComponent {
  viewportUrl = 'http://localhost:8000/api/viewport';
  timestamp = Date.now();

  ngOnInit() {
    setInterval(() => { this.timestamp = Date.now(); }, 500);
  }
}
```

**Resultado:** ~2-5 FPS, funcional pero no fluido.

---

## 10. Estimación de tiempos

| Fase | A1 (iframe) | A2 (WebRTC lib) | Plan B (captura) |
|------|-------------|-----------------|------------------|
| FASE 1: Omniverse | 30 min | 30 min | 30 min |
| FASE 2: Componente | 30 min | 2-3 horas | 1 hora |
| FASE 3: Script M3 | 2 horas | 2 horas | 1 hora |
| FASE 4: Verificación | 30 min | 30 min | 30 min |
| **Total** | **~3.5 horas** | **~5.5 horas** | **~3 horas** |

---

## 11. Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| `localhost:8200` no carga | Extensión no habilitada | Extension Manager → habilitar `livestream.*` |
| CORS error | Origen no permitido | Agregar `http://localhost:8100` en la extensión |
| Stream se corta | Firewall | Verificar puertos 49100-49200 |
| Robots no se mueven en USD | M3 no corriendo | Ejecutar script M3 en Script Editor |
| iframe en blanco | URL incorrecta | Probar `http://localhost:8200` directo en Chrome |
| WebRTC no conecta | Versión incompatible | Verificar USD Composer 2023.1.x–2024.x |

---

## 12. Referencias

- [omni.services.livestream.webrtc — Docs](https://docs.omniverse.nvidia.com/kit/docs/omni.services.livestream.webrtc/latest/Overview.html)
- [OV Web SDK — Streaming Library](https://docs.omniverse.nvidia.com/ov-web-sdk/latest/web-streaming-library/overview.html)
- [Create OV WebRTC App](https://docs.omniverse.nvidia.com/ov-web-sdk/latest/web-sample/overview.html)
- [NVIDIA web-viewer-sample](https://github.com/NVIDIA-Omniverse/web-viewer-sample)
- [NVIDIA Kit App Template](https://github.com/NVIDIA-Omniverse/kit-app-template)
- [Bus API](bus_api.md)
- [Integración M1/M2/M3/Bus](integracion_grupo12.md)
