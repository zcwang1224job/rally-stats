import { Component, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** 037-rest-ready-toggle: the one rest/ready button, used by a player for
 * themself (member-schedule) and by an admin for any roster row (admin
 * page). Presentational only — the parent sends the request, so each page
 * keeps its own identity handling and REST_ENDS_ROUND prompt.
 *
 * Emits the *target* state, never "toggle": the API takes a target state
 * so a double tap can't flip it back. No confirmation here (FR-002) — the
 * one rest that needs one is decided by the backend, and the parent shows
 * that prompt. */
@Component({
  selector: 'app-rest-toggle-button',
  imports: [TranslatePipe],
  templateUrl: './rest-toggle-button.component.html',
  styleUrl: './rest-toggle-button.component.scss',
})
export class RestToggleButtonComponent {
  readonly resting = input.required<boolean>();
  /** With `resting`: on court now, so the rest starts after this match. */
  readonly currentlyPlaying = input<boolean>(false);
  /** A request is in flight — disables the button. */
  readonly pending = input<boolean>(false);
  /** Admin roster rows: shorter label, nickname in the aria-label. */
  readonly compact = input<boolean>(false);
  readonly nickname = input<string | null>(null);

  readonly toggled = output<boolean>();

  press(): void {
    this.toggled.emit(!this.resting());
  }
}
