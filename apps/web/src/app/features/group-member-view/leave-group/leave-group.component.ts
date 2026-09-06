import { Component, DestroyRef, inject, input, output, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { ConfirmDialogComponent } from '../../group-admin/shared/confirm-dialog.component';
import { GroupJoinService } from '../../group-join/group-join.service';
import { GroupMemberViewService } from '../group-member-view.service';

/** US4 (FR-013~016): a general member's self-service exit. Reuses the
 * existing generic confirm dialog (constitution V) and `handle_member_left`
 * convergence rules via `leaveGroup()` — this component's only job is
 * resolving the caller's own `roster_entry_id` and surfacing errors. */
@Component({
  selector: 'app-leave-group',
  imports: [TranslatePipe, ConfirmDialogComponent],
  templateUrl: './leave-group.component.html',
  styleUrl: './leave-group.component.scss',
})
export class LeaveGroupComponent {
  readonly groupId = input.required<string>();
  readonly left = output<void>();

  private readonly memberView = inject(GroupMemberViewService);
  private readonly groupJoin = inject(GroupJoinService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly errorKey = signal<string | null>(null);
  private readonly dialog = viewChild.required<ConfirmDialogComponent>('dialog');

  openDialog(): void {
    this.errorKey.set(null);
    this.dialog().open();
  }

  confirmLeave(): void {
    this.memberView
      .resolveRosterEntryId(this.groupId())
      .subscribe({
        next: (rosterEntryId) => this.submitLeave(rosterEntryId),
        error: (error: ApiError) => this.errorKey.set(error.i18nKey),
      });
  }

  private submitLeave(rosterEntryId: string): void {
    this.memberView
      .leaveGroup(this.groupId(), rosterEntryId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          // Harmless no-op for a Member (never set in the first place) —
          // only meaningful for a Guest leaving their one tracked group.
          if (this.groupJoin.getActiveGuestGroupId() === this.groupId()) {
            this.groupJoin.clearActiveGuestGroupId();
          }
          this.left.emit();
          void this.router.navigate(['/groups']);
        },
        error: (error: ApiError) => this.errorKey.set(error.i18nKey),
      });
  }
}
