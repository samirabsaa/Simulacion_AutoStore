import { Component, OnDestroy, OnInit } from '@angular/core';
import { Subscription } from 'rxjs';
import { BusClientService, BusState } from '../../core/services/bus-client.service';
import { SimApiService } from '../../core/services/sim-api.service';
import { BusStripComponent } from '../../shared/components/bus-strip/bus-strip.component';

@Component({
  selector: 'app-reportes',
  templateUrl: './reportes.page.html',
  imports: [BusStripComponent],
})
export class ReportesPage implements OnInit, OnDestroy {
  bus: BusState | null = null;
  private sub!: Subscription;

  constructor(
    private busService: BusClientService,
    private simApi: SimApiService,
  ) {}

  ngOnInit(): void { this.sub = this.busService.bus$.subscribe(s => (this.bus = s)); }
  ngOnDestroy(): void { this.sub?.unsubscribe(); }

  downloadComparativo(): void {
    this.simApi.downloadComparativo();
  }

  exportSesion(): void {
    this.simApi.exportSesion();
  }
}
