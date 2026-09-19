import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import en from '../../../assets/i18n/en.json';
import zhTW from '../../../assets/i18n/zh-TW.json';
import { RestToggleButtonComponent } from './rest-toggle-button.component';

// No translations are loaded, so every string renders as its own i18n key.

function setup(inputs: Record<string, unknown>): ComponentFixture<RestToggleButtonComponent> {
  TestBed.configureTestingModule({
    imports: [RestToggleButtonComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(RestToggleButtonComponent);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function button(fixture: ComponentFixture<RestToggleButtonComponent>): HTMLButtonElement {
  return fixture.nativeElement.querySelector('button');
}

function lookup(bundle: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      bundle,
    );
}

/** Every i18n key 037 adds. Later 037 tasks append theirs here. */
const REST_TOGGLE_I18N_KEYS = [
  'restToggle.rest',
  'restToggle.ready',
  'restToggle.afterThisMatch',
  'restToggle.adminRest',
  'restToggle.adminReady',
  'restToggle.adminAriaLabel',
  'restToggle.adminReadyAriaLabel',
  'restToggle.substitutionNote',
  'restToggle.partnerResting',
  'restToggle.effectHeld',
  'restToggle.effectSubstitute',
  'restToggle.heldNote',
  'restToggle.endsRound.title',
  'restToggle.endsRound.body',
  'restToggle.endsRound.adminBody',
  'restToggle.endsRound.confirm',
  'scheduleManagement.restingBadge',
  'scheduleManagement.restingSuffix',
  'scheduleManagement.waitingHeldForRest',
  'scheduleManagement.waitingNotEnoughReady',
  'scheduleManagement.waitingOnRest',
  'scheduleManagement.waitingOnRestHint',
  'errors.REST_ENDS_ROUND',
];

describe('RestToggleButtonComponent', () => {
  it('offers a break to a ready player', () => {
    const fixture = setup({ resting: false });
    expect(button(fixture).textContent).toContain('restToggle.rest');
    expect(button(fixture).getAttribute('aria-pressed')).toBe('false');
  });

  it('offers "ready" to a resting player', () => {
    const fixture = setup({ resting: true });
    expect(button(fixture).textContent).toContain('restToggle.ready');
    expect(button(fixture).getAttribute('aria-pressed')).toBe('true');
  });

  it('emits the target state, not a toggle', () => {
    const fixture = setup({ resting: false });
    const emitted: boolean[] = [];
    fixture.componentInstance.toggled.subscribe((value) => emitted.push(value));

    button(fixture).click();
    fixture.componentRef.setInput('resting', true);
    fixture.detectChanges();
    button(fixture).click();

    expect(emitted).toEqual([true, false]);
  });

  it('is disabled while a request is in flight', () => {
    const fixture = setup({ resting: false, pending: true });
    expect(button(fixture).disabled).toBe(true);
  });

  it('says the break starts after this match only when resting on court', () => {
    const note = (inputs: Record<string, unknown>) =>
      setup(inputs).nativeElement.querySelector('.rest-toggle__note');

    expect(note({ resting: true, currentlyPlaying: true })?.textContent).toContain(
      'restToggle.afterThisMatch',
    );
    TestBed.resetTestingModule();
    expect(note({ resting: true, currentlyPlaying: false })).toBeNull();
    TestBed.resetTestingModule();
    expect(note({ resting: false, currentlyPlaying: true })).toBeNull();
  });

  it('uses the short label and names the player for admin rows', () => {
    const fixture = setup({ resting: false, compact: true, nickname: '小美' });
    expect(button(fixture).textContent).toContain('restToggle.adminRest');
    expect(button(fixture).getAttribute('aria-label')).toBe('restToggle.adminAriaLabel');
  });

  it('needs no aria-label on the full-size button, whose text says it all', () => {
    const fixture = setup({ resting: false });
    expect(button(fixture).hasAttribute('aria-label')).toBe(false);
  });

  it('has every 037 string in both languages', () => {
    for (const key of REST_TOGGLE_I18N_KEYS) {
      expect(typeof lookup(zhTW, key), `zh-TW ${key}`).toBe('string');
      expect(typeof lookup(en, key), `en ${key}`).toBe('string');
    }
  });
});
