import { Component, effect, inject, input, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { CourtManagementService } from './court-management.service';
import { Court } from './court-management.models';
import { CourtLinkCardComponent } from './court-link-card.component';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';

/** 場地設定區塊：新增表單 + 即時場地數量標題 + 每個場地的連結卡片 (T012)
 * + 刪除按鈕與二次確認（T019）。 */
@Component({
  selector: 'app-court-list',
  imports: [ReactiveFormsModule, TranslatePipe, CourtLinkCardComponent, ConfirmDialogComponent],
  templateUrl: './court-list.component.html',
  styleUrl: './court-list.component.scss',
})
export class CourtListComponent {
  readonly groupId = input.required<string>();

  private readonly translate = inject(TranslateService);
  private readonly courtPendingDelete = signal<Court | null>(null);
  readonly deleteDialog = viewChild.required<ConfirmDialogComponent>('deleteDialog');

  private readonly fb = inject(FormBuilder);
  private readonly courtService = inject(CourtManagementService);

  readonly courts = signal<Court[]>([]);
  readonly activeCourtCount = signal(0);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(20)]],
  });

  readonly renamingCourtId = signal<string | null>(null);
  readonly renameForm = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(20)]],
  });

  constructor() {
    effect(() => {
      const id = this.groupId();
      if (id) {
        this.load(id);
      }
    });
  }

  load(groupId: string): void {
    this.loading.set(true);
    this.courtService.listCourts(groupId).subscribe({
      next: (res) => {
        this.courts.set(res.courts);
        this.activeCourtCount.set(res.active_court_count);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  addCourt(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { name } = this.form.getRawValue();
    this.errorKey.set(null);
    this.courtService.createCourt(this.groupId(), name).subscribe({
      next: () => {
        this.form.reset();
        this.load(this.groupId());
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  startRename(court: Court): void {
    this.errorKey.set(null);
    this.renameForm.reset({ name: court.name });
    this.renamingCourtId.set(court.court_id);
  }

  cancelRename(): void {
    this.renamingCourtId.set(null);
  }

  renameCourt(court: Court): void {
    if (this.renameForm.invalid) {
      this.renameForm.markAllAsTouched();
      return;
    }
    const { name } = this.renameForm.getRawValue();
    this.errorKey.set(null);
    this.courtService.renameCourt(this.groupId(), court.court_id, name).subscribe({
      next: () => {
        this.renamingCourtId.set(null);
        this.load(this.groupId());
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  openDeleteDialog(court: Court): void {
    this.courtPendingDelete.set(court);
    this.deleteDialog().open();
  }

  deleteDialogTitle(): string {
    const court = this.courtPendingDelete();
    if (!court) {
      return '';
    }
    return this.translate.instant('courtManagement.deleteConfirmTitle', { name: court.name });
  }

  deleteDialogBody(): string {
    const parts = [this.translate.instant('courtManagement.deleteConfirmBody')];
    if (this.activeCourtCount() === 1) {
      parts.push(this.translate.instant('courtManagement.deleteConfirmLastCourt'));
    }
    return parts.join(' ');
  }

  confirmDelete(): void {
    const court = this.courtPendingDelete();
    if (!court) {
      return;
    }
    this.errorKey.set(null);
    this.courtService.deleteCourt(this.groupId(), court.court_id).subscribe({
      next: () => {
        this.courtPendingDelete.set(null);
        this.load(this.groupId());
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
