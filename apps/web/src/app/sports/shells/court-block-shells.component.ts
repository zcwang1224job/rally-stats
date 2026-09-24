import { Component, TemplateRef, computed, inject, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { CourtControlService } from '../../core/api/court-control.service';
import { CourtLiveState } from '../../core/api/court-live-state.models';
import { waitingReasonKey } from '../../core/waiting-reason-label';
import { CourtScheduleStatus } from '../../features/group-admin/schedule-management/schedule.models';
import { ScheduleService } from '../../features/group-admin/schedule-management/schedule.service';
import { CourtScoringShellComponent, ScorePadContext } from './court-scoring-shell.component';
import { adminActions, allCourtsActions } from './scoring-actions';

/**
 * 043: one court on the all-courts page for a non-net-rally sport type.
 * Same inputs as net rally's `app-all-courts-court-block`; the page keeps
 * the state fresh and reloads on `changed`.
 */
@Component({
  selector: 'app-all-courts-block-shell',
  imports: [TranslatePipe, CourtScoringShellComponent],
  template: `
    <section class="court-block card">
      <h2>{{ name() }}</h2>
      @if (state(); as s) {
        @if (s.current_match; as match) {
          <app-court-scoring-shell
            [match]="match"
            [actions]="actions()"
            [pad]="pad()"
            (changed)="changed.emit()"
          />
        } @else if (s.waiting_reason === 'manual_assignment') {
          <p class="waiting-message">{{ 'scheduleManagement.waitingManualAssignment' | translate }}</p>
        } @else {
          <p class="waiting-message">{{ waitingReasonKey(s.waiting_reason) | translate }}</p>
        }
      }
    </section>
  `,
})
export class AllCourtsBlockShellComponent {
  readonly waitingReasonKey = waitingReasonKey;
  private readonly service = inject(CourtControlService);

  readonly token = input.required<string>();
  readonly courtId = input.required<string>();
  readonly name = input.required<string>();
  readonly state = input.required<CourtLiveState | null>();
  readonly pad = input<TemplateRef<ScorePadContext> | null>(null);
  readonly changed = output<void>();

  readonly actions = computed(() => allCourtsActions(this.service, this.token(), this.courtId()));
}

/**
 * 043: the admin page's control of one court with a match on it, for a
 * non-net-rally sport type. Same inputs as net rally's `app-court-control`.
 */
@Component({
  selector: 'app-admin-court-shell',
  imports: [CourtScoringShellComponent],
  template: `
    @if (court().current_match; as match) {
      <app-court-scoring-shell
        [match]="match"
        [actions]="actions()"
        [pad]="pad()"
        (changed)="changed.emit()"
      />
    }
  `,
})
export class AdminCourtShellComponent {
  private readonly service = inject(ScheduleService);

  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly pad = input<TemplateRef<ScorePadContext> | null>(null);
  readonly changed = output<void>();

  readonly actions = computed(() =>
    adminActions(this.service, this.groupId(), this.court().court_id),
  );
}
