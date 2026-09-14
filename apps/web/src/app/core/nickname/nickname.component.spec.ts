import { TestBed } from '@angular/core/testing';
import { NicknameComponent } from './nickname.component';

function setup(value: string | null) {
  TestBed.configureTestingModule({ imports: [NicknameComponent] });
  const fixture = TestBed.createComponent(NicknameComponent);
  fixture.componentRef.setInput('value', value);
  fixture.detectChanges();
  return fixture;
}

describe('NicknameComponent', () => {
  it('renders a real nickname without the deleted class', () => {
    const fixture = setup('小明');

    const span = fixture.nativeElement.querySelector('.nickname') as HTMLElement;
    expect(span.textContent).toContain('小明');
    expect(span.classList.contains('nickname--deleted')).toBe(false);
  });

  // 025-delete-account follow-up: deleted accounts shown with a color
  // representing "no longer exists" wherever match/roster history renders
  // participant names.
  it('renders the "Deleted User" placeholder with the deleted class', () => {
    const fixture = setup('Deleted User');

    const span = fixture.nativeElement.querySelector('.nickname') as HTMLElement;
    expect(span.textContent).toContain('Deleted User');
    expect(span.classList.contains('nickname--deleted')).toBe(true);
  });

  it('does not flag a real nickname that happens to contain the placeholder text as a substring', () => {
    const fixture = setup('Not Deleted User');

    const span = fixture.nativeElement.querySelector('.nickname') as HTMLElement;
    expect(span.classList.contains('nickname--deleted')).toBe(false);
  });
});
