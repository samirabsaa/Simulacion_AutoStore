import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'app-control-bar',
  templateUrl: './control-bar.component.html',
  styleUrls: ['./control-bar.component.scss'],
  imports: [],
})
export class ControlBarComponent {
  @Input()  running = false;
  @Input()  speed: 1 | 2 | 5 = 1;
  @Output() play        = new EventEmitter<void>();
  @Output() pause       = new EventEmitter<void>();
  @Output() reset       = new EventEmitter<void>();
  @Output() speedChange = new EventEmitter<1 | 2 | 5>();

  readonly speeds: (1 | 2 | 5)[] = [1, 2, 5];

  onSpeed(s: 1 | 2 | 5): void { this.speedChange.emit(s); }
}
