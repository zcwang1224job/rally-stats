import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { ConfirmDialogComponent } from './confirm-dialog.component';

function setup(variant?: 'danger' | 'primary') {
  TestBed.configureTestingModule({
    imports: [ConfirmDialogComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(ConfirmDialogComponent);
  fixture.componentRef.setInput('title', 'Title');
  fixture.componentRef.setInput('body', 'Body');
  if (variant) {
    fixture.componentRef.setInput('variant', variant);
  }
  fixture.detectChanges();
  const buttons: HTMLButtonElement[] = Array.from(
    fixture.nativeElement.querySelectorAll('.actions button'),
  );
  return { fixture, cancelButton: buttons[0], confirmButton: buttons[1] };
}

describe('ConfirmDialogComponent', () => {
  it('uses the shared dialog shell', () => {
    const { fixture } = setup();
    expect(fixture.nativeElement.querySelector('dialog.dialog.dialog--sm')).not.toBeNull();
  });

  it('renders a danger confirm button by default', () => {
    const { confirmButton } = setup();
    expect(confirmButton.classList).toContain('btn--danger');
  });

  it('renders a primary confirm button for a non-destructive confirmation', () => {
    const { confirmButton } = setup('primary');
    expect(confirmButton.classList).toContain('btn');
    expect(confirmButton.classList).not.toContain('btn--danger');
  });

  it('emits confirmed only when confirm is clicked', () => {
    const { fixture, cancelButton, confirmButton } = setup();
    let count = 0;
    fixture.componentInstance.confirmed.subscribe(() => count++);
    cancelButton.click();
    expect(count).toBe(0);
    confirmButton.click();
    expect(count).toBe(1);
  });

  /** 039-match-point-confirm: `closed` hangs off the native `close` event,
   * not off cancel(), so that Esc — which closes a <dialog> without calling
   * any of this component's methods — is covered too. jsdom implements
   * neither showModal() nor close(), so the event is dispatched by hand
   * here; what's under test is that the binding exists and reaches the
   * output, which is the part the real browser would otherwise skip. */
  it('emits closed when the underlying dialog closes, whatever closed it', () => {
    const { fixture } = setup();
    let count = 0;
    fixture.componentInstance.closed.subscribe(() => count++);

    const dialog: HTMLElement = fixture.nativeElement.querySelector('dialog');
    dialog.dispatchEvent(new Event('close')); // what Esc does in a browser

    expect(count).toBe(1);
  });

  it('does not emit closed merely because confirm was clicked', () => {
    // confirmed fires first and independently; closed follows the actual
    // close. A caller reads its pending state in the confirmed handler and
    // clears it in the closed handler, so conflating the two would clear
    // the state before it could be read.
    const { fixture, confirmButton } = setup();
    const order: string[] = [];
    fixture.componentInstance.confirmed.subscribe(() => order.push('confirmed'));
    fixture.componentInstance.closed.subscribe(() => order.push('closed'));

    confirmButton.click();
    fixture.nativeElement.querySelector('dialog').dispatchEvent(new Event('close'));

    expect(order).toEqual(['confirmed', 'closed']);
  });
});
