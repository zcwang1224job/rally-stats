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
});
