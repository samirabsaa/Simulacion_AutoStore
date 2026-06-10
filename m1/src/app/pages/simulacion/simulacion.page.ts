import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';

@Component({
  selector: 'app-simulacion',
  templateUrl: './simulacion.page.html',
  imports: [BusStripComponent],
})
export class SimulacionPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  constructor(private busService: BusClientService) {}

  ngOnInit(): void { this.sub = this.busService.bus$.subscribe(s => (this.bus = s)); }
  ngOnDestroy(): void { this.sub?.unsubscribe(); }
}
