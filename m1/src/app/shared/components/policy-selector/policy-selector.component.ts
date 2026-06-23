import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import {
  IonCard, IonCardHeader, IonCardTitle, IonCardContent,
  IonItem, IonLabel, IonRadioGroup, IonRadio, IonIcon,
} from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { addCircleOutline } from 'ionicons/icons';
import { PickingPolicy } from '../../../core/enums/sim.enums';

@Component({
  selector: 'app-policy-selector',
  templateUrl: './policy-selector.component.html',
  styleUrls: ['./policy-selector.component.scss'],
  standalone: true,
  imports: [
    IonCard, IonCardHeader, IonCardTitle, IonCardContent,
    IonItem, IonLabel, IonRadioGroup, IonRadio, IonIcon,
  ],
})
export class PolicySelectorComponent implements OnChanges {
  @Input() currentPolicy: string = PickingPolicy.FIFO;
  @Input() customPolicies: { name: string; label: string }[] = [];
  @Output() policyChange = new EventEmitter<string>();
  @Output() loadExternal = new EventEmitter<void>();

  PickingPolicy = PickingPolicy;
  selected: string = PickingPolicy.FIFO;

  private propagating = false;

  constructor() {
    addIcons({ addCircleOutline });
  }

  ngOnChanges(): void {
    this.selected = this.currentPolicy;
  }

  onChange(event: CustomEvent): void {
    const val = event.detail.value as string;
    if (val === this.selected || this.propagating) return;
    this.propagating = true;
    this.selected = val;
    this.policyChange.emit(val);
    setTimeout(() => (this.propagating = false));
  }

  onLoadClick(): void {
    this.loadExternal.emit();
  }
}
