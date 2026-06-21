import { Component, Input } from '@angular/core';
import { WsRobotState } from '../../../core/models/state-bus-snapshot.model';
import { robotStateCssMod, robotStateLabel } from '../../../core/utils/robot-state.util';

@Component({
  selector: 'app-robot-status-panel',
  templateUrl: './robot-status-panel.component.html',
  styleUrls: ['./robot-status-panel.component.scss'],
  imports: [],
})
export class RobotStatusPanelComponent {
  @Input() robots: WsRobotState[] = [];
  @Input() tick = 0;

  readonly stateLegend = [
    { estado: 'IDLE',       label: 'Inactivo' },
    { estado: 'MOVING',     label: 'En movimiento' },
    { estado: 'PICKING',    label: 'Excavando' },
    { estado: 'BLOCKED',    label: 'Bloqueado' },
    { estado: 'DEPOSITING', label: 'Entregando' },
  ];

  label(estado: string): string {
    return robotStateLabel(estado);
  }

  cssMod(estado: string): string {
    return robotStateCssMod(estado);
  }
}
