import { Component, Input } from '@angular/core';
import { BusState } from '../../../core/services/bus-client.service';
import { SimMode, PickingPolicy } from '../../../core/enums/sim.enums';

@Component({
  selector: 'app-bus-strip',
  templateUrl: './bus-strip.component.html',
  styleUrls: ['./bus-strip.component.scss'],
  imports: [],
})
export class BusStripComponent {
  @Input() bus!: BusState;

  get tickStr(): string {
    return String(this.bus?.tick ?? 0).padStart(5, '0');
  }

  get modoLabel(): string {
    return this.bus?.mode === SimMode.DIURNO ? 'PICKING (Diurno)' : 'REPOSICIÓN (Nocturno)';
  }

  get politicaLabel(): string {
    switch (this.bus?.policy) {
      case PickingPolicy.FIFO: return 'FIFO';
      case PickingPolicy.PRIORITY_POSITION: return 'Prioridad Posición';
      default: return this.bus?.policy ?? '-';
    }
  }

  get grillaLabel(): string {
    const g = this.bus?.grid;
    return g ? `${g.x}×${g.y}×${g.z}` : '-';
  }

  get isDiurno(): boolean {
    return this.bus?.mode === SimMode.DIURNO;
  }

  get isOmni(): boolean {
    return this.bus?.omniverse === 'conectado';
  }
}
