import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import {
  IonCard, IonCardHeader, IonCardTitle, IonCardContent,
  IonItem, IonLabel, IonRadioGroup, IonRadio,
} from '@ionic/angular/standalone';
import { SimMode } from '../../../core/enums/sim.enums';

@Component({
  selector: 'app-mode-selector',
  templateUrl: './mode-selector.component.html',
  styleUrls: ['./mode-selector.component.scss'],
  standalone: true,
  imports: [
    IonCard, IonCardHeader, IonCardTitle, IonCardContent,
    IonItem, IonLabel, IonRadioGroup, IonRadio,
  ],
})
export class ModeSelectorComponent implements OnChanges {
  @Input() currentMode: SimMode = SimMode.DIURNO;
  @Output() modeChange = new EventEmitter<SimMode>();

  SimMode = SimMode;
  selected = SimMode.DIURNO;

  ngOnChanges(): void {
    this.selected = this.currentMode;
  }

  onChange(event: CustomEvent): void {
    const val = event.detail.value as SimMode;
    this.selected = val;
    this.modeChange.emit(val);
  }
}
