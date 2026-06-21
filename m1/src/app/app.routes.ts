import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'panel', pathMatch: 'full' },
  { path: 'grilla', redirectTo: 'monitor', pathMatch: 'full' },
  { path: 'simulacion', redirectTo: 'monitor', pathMatch: 'full' },
  {
    path: 'panel',
    loadComponent: () => import('./pages/dashboard/dashboard.page').then(m => m.DashboardPage),
  },
  {
    path: 'monitor',
    loadComponent: () => import('./pages/monitor/monitor.page').then(m => m.MonitorPage),
  },
  {
    path: 'reportes',
    loadComponent: () => import('./pages/reportes/reportes.page').then(m => m.ReportesPage),
  },
  {
    path: 'config',
    loadComponent: () => import('./pages/config/config.page').then(m => m.ConfigPage),
  },
];
