import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { IonApp } from '@ionic/angular/standalone';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from './core/services/bus-client.service';
import { SimMode } from './core/enums/sim.enums';

interface NavItem {
  key: string;
  path: string;
  icon: string;
  label: string;
}

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
  imports: [IonApp, RouterOutlet, RouterLink, RouterLinkActive],
})
export class AppComponent implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  readonly SimMode = SimMode;

  readonly nav: NavItem[] = [
    { key: 'panel',      path: '/panel',      icon: '📊', label: 'Panel KPIs'           },
    { key: 'grilla',     path: '/grilla',     icon: '⊞',  label: 'Monitor de Grilla'    },
    { key: 'simulacion', path: '/simulacion', icon: '▣',  label: 'Vista 3D · Omniverse' },
    { key: 'reportes',   path: '/reportes',   icon: '🗄',  label: 'Datos y Reportes'     },
    { key: 'config',     path: '/config',     icon: '⊟',  label: 'Configuración'         },
  ];

  get time(): string {
    return new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  private _time = '';
  displayTime = '';
  private clockId?: ReturnType<typeof setInterval>;

  constructor(private busService: BusClientService, private router: Router) {}

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => (this.bus = s));
    this.clockId = setInterval(() => {
      this.displayTime = new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    }, 1000);
    this.displayTime = new Date().toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  isActive(path: string): boolean {
    return this.router.isActive(path, { paths: 'exact', queryParams: 'ignored', fragment: 'ignored', matrixParams: 'ignored' });
  }

  get isDiurno(): boolean {
    return !this.bus || this.bus.mode === SimMode.DIURNO;
  }

  get tickStr(): string {
    return String(this.bus?.tick ?? 0).padStart(5, '0');
  }

  get isOmni(): boolean {
    return this.bus?.omniverse === 'conectado';
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    if (this.clockId != null) clearInterval(this.clockId);
  }
}
