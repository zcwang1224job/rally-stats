import { Component, input, output } from '@angular/core';

import { CourtLiveState } from '../../../core/api/court-live-state.models';
import { CourtScheduleStatus } from '../../../features/group-admin/schedule-management/schedule.models';
import {
  AdminCourtShellComponent,
  AllCourtsBlockShellComponent,
} from '../../shells/court-block-shells.component';
import { CourtLinkPageComponent } from '../../shells/court-link-page.component';
import { FramesPadComponent } from './frames-pad.component';

/** `/scoreboard/:courtToken`: frames won in big numbers, the frame on. */
@Component({
  selector: 'app-frames-scoreboard',
  imports: [CourtLinkPageComponent, FramesPadComponent],
  template: `
  <ng-template
    #pad
    let-m
    let-actions="actions"
    let-run="run"
    let-busy="busy"
    let-connected="connected"
    let-readOnly="readOnly"
  >
    <app-frames-pad
      [match]="m"
      [actions]="actions"
      [run]="run"
      [busy]="busy"
      [connected]="connected"
      [readOnly]="readOnly"
    />
  </ng-template>
    <app-court-link-page mode="scoreboard" [pad]="pad" />`,
})
export class FramesScoreboardComponent {}

/** `/control/:courtToken`. */
@Component({
  selector: 'app-frames-control-panel',
  imports: [CourtLinkPageComponent, FramesPadComponent],
  template: `
  <ng-template
    #pad
    let-m
    let-actions="actions"
    let-run="run"
    let-busy="busy"
    let-connected="connected"
    let-readOnly="readOnly"
  >
    <app-frames-pad
      [match]="m"
      [actions]="actions"
      [run]="run"
      [busy]="busy"
      [connected]="connected"
      [readOnly]="readOnly"
    />
  </ng-template>
    <app-court-link-page mode="control" [pad]="pad" />`,
})
export class FramesControlPanelComponent {}

/** One court on the all-courts page. */
@Component({
  selector: 'app-frames-all-courts-block',
  imports: [AllCourtsBlockShellComponent, FramesPadComponent],
  template: `
  <ng-template
    #pad
    let-m
    let-actions="actions"
    let-run="run"
    let-busy="busy"
    let-connected="connected"
    let-readOnly="readOnly"
  >
    <app-frames-pad
      [match]="m"
      [actions]="actions"
      [run]="run"
      [busy]="busy"
      [connected]="connected"
      [readOnly]="readOnly"
    />
  </ng-template>
    <app-all-courts-block-shell
      [token]="token()"
      [courtId]="courtId()"
      [name]="name()"
      [state]="state()"
      [groupId]="groupId()"
      [pad]="pad"
      (changed)="changed.emit()"
    />`,
})
export class FramesAllCourtsBlockComponent {
  readonly token = input.required<string>();
  readonly courtId = input.required<string>();
  readonly name = input.required<string>();
  readonly state = input.required<CourtLiveState | null>();
  /** The group, for the court's realtime channel (see the block shell). */
  readonly groupId = input<string | null>(null);
  readonly changed = output<void>();
}

/** The admin page's control of one court. */
@Component({
  selector: 'app-frames-court-control',
  imports: [AdminCourtShellComponent, FramesPadComponent],
  template: `
  <ng-template
    #pad
    let-m
    let-actions="actions"
    let-run="run"
    let-busy="busy"
    let-connected="connected"
    let-readOnly="readOnly"
  >
    <app-frames-pad
      [match]="m"
      [actions]="actions"
      [run]="run"
      [busy]="busy"
      [connected]="connected"
      [readOnly]="readOnly"
    />
  </ng-template>
    <app-admin-court-shell
      [groupId]="groupId()"
      [court]="court()"
      [pad]="pad"
      (changed)="changed.emit()"
    />`,
})
export class FramesCourtControlComponent {
  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly changed = output<void>();
}
