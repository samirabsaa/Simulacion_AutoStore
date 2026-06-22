import { Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { IonApp, IonIcon } from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { gridOutline, easelOutline, barChartOutline, settingsOutline } from 'ionicons/icons';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from './core/services/bus-client.service';

interface NavItem {
  key: string;
  path: string;
  icon: string;     // ionicon name
  label: string;
}

@Component({
  selector: 'app-root',
  templateUrl: 'app.component.html',
  styleUrls: ['app.component.scss'],
  imports: [IonApp, IonIcon, RouterOutlet, RouterLink, RouterLinkActive],
})
export class AppComponent implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  readonly nav: NavItem[] = [
    { key: 'panel',    path: '/panel',    icon: 'grid-outline',        label: 'Panel de Estados'              },
    { key: 'monitor',  path: '/monitor',  icon: 'easel-outline',       label: 'Monitor Simulación (2D/3D)'   },
    { key: 'reportes', path: '/reportes', icon: 'bar-chart-outline',   label: 'Datos Estadísticos'          },
    { key: 'config',   path: '/config',   icon: 'settings-outline',    label: 'Configuración'               },
  ];

  constructor(private busService: BusClientService) {
    addIcons({ gridOutline, easelOutline, barChartOutline, settingsOutline });
  }

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => (this.bus = s));
  }

  get isOmni(): boolean {
    return this.bus?.omniverse === 'conectado';
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}
