import { Component, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { CourtLiveState } from '../../../core/api/court-live-state.models';
import { CourtScheduleStatus } from '../../../features/group-admin/schedule-management/schedule.models';
import {
  AdminCourtShellComponent,
  AllCourtsBlockShellComponent,
} from '../../shells/court-block-shells.component';
import { CourtLinkPageComponent } from '../../shells/court-link-page.component';
import { SportTypeModule } from '../../sport-type-module';
import { GenericPadComponent } from './generic-pad.component';

@Component({
  selector: 'app-generic-scoreboard',
  imports: [CourtLinkPageComponent, GenericPadComponent],
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
    <app-generic-pad
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
export class GenericScoreboardComponent {}

@Component({
  selector: 'app-generic-control-panel',
  imports: [CourtLinkPageComponent, GenericPadComponent],
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
    <app-generic-pad
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
export class GenericControlPanelComponent {}

@Component({
  selector: 'app-generic-all-courts-block',
  imports: [AllCourtsBlockShellComponent, GenericPadComponent],
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
    <app-generic-pad
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
export class GenericAllCourtsBlockComponent {
  readonly token = input.required<string>();
  readonly courtId = input.required<string>();
  readonly name = input.required<string>();
  readonly state = input.required<CourtLiveState | null>();
  /** The group, for the court's realtime channel (see the block shell). */
  readonly groupId = input<string | null>(null);
  readonly changed = output<void>();
}

@Component({
  selector: 'app-generic-court-control',
  imports: [AdminCourtShellComponent, GenericPadComponent],
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
    <app-generic-pad
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
export class GenericCourtControlComponent {
  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly changed = output<void>();
}

/** The generic type has no parameters of its own this release. */
@Component({
  selector: 'app-generic-create-form-fields',
  imports: [TranslatePipe],
  template: `<p class="form-hint">{{ 'genericSport.formHint' | translate }}</p>`,
})
export class GenericCreateFormFieldsComponent {
  readonly form = input<unknown>(null);
  readonly defaults = input<unknown>(null);
}

/**
 * 043 US5: the generic sport type — only a score and a result, for any
 * activity the catalogue does not cover. Its pages use the generic section
 * kinds only. Loaded as its own chunk.
 */
export const GENERIC: SportTypeModule = {
  typeKey: 'generic',
  surfaces: {
    scoreboard: GenericScoreboardComponent,
    controlPanel: GenericControlPanelComponent,
    allCourtsBlock: GenericAllCourtsBlockComponent,
    courtControl: GenericCourtControlComponent,
    createFormFields: GenericCreateFormFieldsComponent,
  },
  sectionKinds: {},
};
