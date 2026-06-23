import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';
import { ControlBarComponent } from '../../shared/components/control-bar/control-bar.component';
import { RobotGridComponent } from '../../shared/components/robot-grid/robot-grid.component';
import { KpiSidebarComponent } from '../../shared/components/kpi-sidebar/kpi-sidebar.component';

type Vista = '2d' | '3d';

@Component({
  selector: 'app-monitor',
  templateUrl: './monitor.page.html',
  styleUrls: ['./monitor.page.scss'],
  imports: [BusStripComponent, ControlBarComponent, RobotGridComponent, KpiSidebarComponent],
})
export class MonitorPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  vista: Vista = '2d';

  constructor(private busService: BusClientService) {}

  ngOnInit(): void {
    this.sub = this.busService.bus$.subscribe(s => (this.bus = s));
  }

  setVista(v: Vista): void {
    this.vista = v;
  }

  onPlay(): void  { this.busService.setRunning(true); }
  onPause(): void { this.busService.setRunning(false); }
  onReset(): void { this.busService.reset(); }
  onSpeedChange(s: 1|2|5): void { this.busService.setSpeed(s); }

  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
