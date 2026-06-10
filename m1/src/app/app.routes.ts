import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'panel', pathMatch: 'full' },
  {
    path: 'panel',
    loadComponent: () => import('./pages/dashboard/dashboard.page').then(m => m.DashboardPage),
  },
  {
    path: 'grilla',
    loadComponent: () => import('./pages/grilla/grilla.page').then(m => m.GrillaPage),
  },
  {
    path: 'simulacion',
    loadComponent: () => import('./pages/simulacion/simulacion.page').then(m => m.SimulacionPage),
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
