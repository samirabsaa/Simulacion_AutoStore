import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';
import { RobotGridComponent } from '../../shared/components/robot-grid/robot-grid.component';

@Component({
  selector: 'app-grilla',
  templateUrl: './grilla.page.html',
  styleUrls: ['./grilla.page.scss'],
  imports: [BusStripComponent, RobotGridComponent],
})
export class GrillaPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  constructor(private busService: BusClientService) {}

  ngOnInit(): void { this.sub = this.busService.bus$.subscribe(s => (this.bus = s)); }
  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
