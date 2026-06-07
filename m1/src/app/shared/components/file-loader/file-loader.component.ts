import { Component, EventEmitter, Input, Output, ViewChild, ElementRef } from '@angular/core';
import {
  IonButton, IonIcon,
} from '@ionic/angular/standalone';
import { addIcons } from 'ionicons';
import { cloudUploadOutline, documentTextOutline, warningOutline, checkmarkCircleOutline } from 'ionicons/icons';

@Component({
  selector: 'app-file-loader',
  templateUrl: './file-loader.component.html',
  styleUrls: ['./file-loader.component.scss'],
  standalone: true,
  imports: [IonButton, IonIcon],
})
export class FileLoaderComponent {
  @Input() errors: string[] = [];
  @Input() loaded = false;
  @Output() fileSelected = new EventEmitter<Event>();

  @ViewChild('fileInput') fileInputRef!: ElementRef<HTMLInputElement>;

  fileName = '';

  constructor() {
    addIcons({ cloudUploadOutline, documentTextOutline, warningOutline, checkmarkCircleOutline });
  }

  openPicker(): void {
    this.fileInputRef?.nativeElement?.click();
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files?.length) {
      this.fileName = input.files[0].name;
    }
    this.fileSelected.emit(event);
  }
}
