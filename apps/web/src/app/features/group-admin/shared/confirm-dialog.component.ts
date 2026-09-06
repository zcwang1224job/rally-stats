import { Component, ElementRef, input, output, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** Generic two-step confirmation dialog (constitution V — destructive actions
 * require confirmation) used by both the disband and regenerate-PIN flows. */
@Component({
  selector: 'app-confirm-dialog',
  imports: [TranslatePipe],
  template: `
    <dialog #dialog>
      <h2>{{ title() }}</h2>
      <p>{{ body() }}</p>
      <div class="actions">
        <button type="button" class="btn btn--secondary" (click)="cancel()">
          {{ 'common.cancel' | translate }}
        </button>
        <button type="button" class="btn btn--danger" (click)="confirm()">
          {{ 'common.confirm' | translate }}
        </button>
      </div>
    </dialog>
  `,
  styleUrl: './confirm-dialog.component.scss',
})
export class ConfirmDialogComponent {
  readonly title = input.required<string>();
  readonly body = input.required<string>();
  readonly confirmed = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  open(): void {
    // jsdom (unit tests) doesn't implement the <dialog> API at all — guard
    // rather than skip the call outright in real browsers. Callers that
    // never actually invoke open() in a test (most existing usages) never
    // hit this; it only matters once a test calls it directly, as US7's
    // friend-list/my-groups specs do.
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    }
  }

  cancel(): void {
    this.closeIfSupported();
  }

  confirm(): void {
    this.confirmed.emit();
    this.closeIfSupported();
  }

  private closeIfSupported(): void {
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.close === 'function') {
      nativeDialog.close();
    }
  }
}
