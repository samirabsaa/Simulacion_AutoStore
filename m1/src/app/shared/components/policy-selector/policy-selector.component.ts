import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import {
  IonCard, IonCardHeader, IonCardTitle, IonCardContent,
  IonItem, IonLabel, IonRadioGroup, IonRadio,
} from '@ionic/angular/standalone';
import { PickingPolicy } from '../../../core/enums/sim.enums';

@Component({
  selector: 'app-policy-selector',
  templateUrl: './policy-selector.component.html',
  styleUrls: ['./policy-selector.component.scss'],
  standalone: true,
  imports: [
    IonCard, IonCardHeader, IonCardTitle, IonCardContent,
    IonItem, IonLabel, IonRadioGroup, IonRadio,
  ],
})
export class PolicySelectorComponent implements OnChanges {
  @Input() currentPolicy: PickingPolicy = PickingPolicy.FIFO;
  @Output() policyChange = new EventEmitter<PickingPolicy>();

  PickingPolicy = PickingPolicy;
  selected = PickingPolicy.FIFO;

  ngOnChanges(): void {
    this.selected = this.currentPolicy;
  }

  onChange(event: CustomEvent): void {
    const val = event.detail.value as PickingPolicy;
    this.selected = val;
    this.policyChange.emit(val);
  }
}
