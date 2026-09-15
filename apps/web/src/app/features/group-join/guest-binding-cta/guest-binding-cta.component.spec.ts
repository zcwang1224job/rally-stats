import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../group-join.service';
import { GuestBindingCtaComponent } from './guest-binding-cta.component';

/** Deliberately never calls `fixture.detectChanges()` — the template embeds
 * the real `TurnstileWidgetComponent` (loads an external script), same
 * reasoning as register.component.spec.ts. Component-instance methods are
 * exercised directly instead. */
function setup(options: {
  loggedIn?: boolean;
  bindReturn?: () => unknown;
  startOAuthFlowReturn?: () => unknown;
}) {
  const bindGuestSessionCalls: unknown[] = [];
  const setTokens = vi.fn();
  const startOAuthFlowCalls: unknown[] = [];

  TestBed.configureTestingModule({
    imports: [GuestBindingCtaComponent],
    providers: [
      provideTranslateService({ lang: 'zh-TW' }),
      {
        provide: AuthService,
        useValue: {
          loggedIn: signal(options.loggedIn ?? false),
          setTokens,
          startOAuthFlow: (...args: unknown[]) => {
            startOAuthFlowCalls.push(args);
            return (options.startOAuthFlowReturn ?? (() => of({ authorize_url: 'https://x' })))();
          },
        },
      },
      {
        provide: GroupJoinService,
        useValue: {
          bindGuestSession: (...args: unknown[]) => {
            bindGuestSessionCalls.push(args);
            return (options.bindReturn ?? (() => of({ bound: true, group_id: 'g1' })))();
          },
        },
      },
    ],
  });

  const fixture = TestBed.createComponent(GuestBindingCtaComponent);
  fixture.componentRef.setInput('guestSessionToken', 'tok-123');
  const component = fixture.componentInstance;
  return { fixture, component, bindGuestSessionCalls, setTokens, startOAuthFlowCalls };
}

describe('GuestBindingCtaComponent', () => {
  // --- UI polish: collapsed-by-default banner ------------------------------
  // Safe to call detectChanges() only while collapsed — the expanded form
  // embeds the real TurnstileWidgetComponent (external script), same
  // reasoning as the file-level docstring above.

  it('not logged in, not yet expanded: renders the compact banner, not the sign-up form', () => {
    const { fixture, component } = setup({ loggedIn: false });
    fixture.detectChanges();

    expect(component.expanded()).toBe(false);
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('guestBinding.bannerText');
    expect(text).toContain('guestBinding.bannerAction');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    expect(fixture.nativeElement.querySelector('app-turnstile-widget')).toBeNull();
  });

  it('clicking the banner action expands to the full sign-up form', () => {
    const { fixture, component } = setup({ loggedIn: false });
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('.cta-banner button')
      ?.click();

    expect(component.expanded()).toBe(true);
  });

  it('collapse() resets to the banner and clears any error', () => {
    const { component } = setup({ loggedIn: false });
    component.expand();
    component.errorKey.set('errors.INVALID_CREDENTIALS');

    component.collapse();

    expect(component.expanded()).toBe(false);
    expect(component.errorKey()).toBeNull();
  });

  // --- T016: text/behavior switches on loggedIn() -------------------------

  it('not logged in: submit() with mode=register sends the register payload and stores returned tokens', () => {
    const { component, bindGuestSessionCalls, setTokens } = setup({
      loggedIn: false,
      bindReturn: () =>
        of({ bound: true, group_id: 'g1', access_token: 'a1', refresh_token: 'r1' }),
    });
    component.mode.set('register');
    component.form.setValue({ email: 'new@example.com', password: 'abc12345' });
    component.onTurnstileVerified('turnstile-token');

    let boundEmitted = false;
    component.bound.subscribe(() => (boundEmitted = true));
    component.submit();

    expect(bindGuestSessionCalls).toEqual([
      [
        'tok-123',
        {
          mode: 'register',
          email: 'new@example.com',
          password: 'abc12345',
          turnstile_token: 'turnstile-token',
        },
      ],
    ]);
    expect(setTokens).toHaveBeenCalledWith('a1', 'r1');
    expect(boundEmitted).toBe(true);
  });

  it('not logged in: submit() is a no-op without a Turnstile token in register mode', () => {
    const { component, bindGuestSessionCalls } = setup({ loggedIn: false });
    component.mode.set('register');
    component.form.setValue({ email: 'new@example.com', password: 'abc12345' });

    component.submit();

    expect(bindGuestSessionCalls).toEqual([]);
  });

  it('already logged in (FR-012): bindWithCurrentSession() sends an empty payload with optionalAuth=true and never stores new tokens', () => {
    const { component, bindGuestSessionCalls, setTokens } = setup({ loggedIn: true });

    let boundEmitted = false;
    component.bound.subscribe(() => (boundEmitted = true));
    component.bindWithCurrentSession();

    expect(bindGuestSessionCalls).toEqual([['tok-123', {}, true]]);
    expect(setTokens).not.toHaveBeenCalled();
    expect(boundEmitted).toBe(true);
  });

  it('OAuth buttons call startOAuthFlow(provider, "login", guestSessionToken) and navigate to the authorize_url', () => {
    const { component, startOAuthFlowCalls } = setup({ loggedIn: false });
    const navigateSpy = vi.spyOn(
      component as unknown as { navigateToAuthorizeUrl: (url: string) => void },
      'navigateToAuthorizeUrl',
    );

    component.continueWithOAuth('google');

    expect(startOAuthFlowCalls).toEqual([['google', 'login', 'tok-123']]);
    expect(navigateSpy).toHaveBeenCalledWith('https://x');
  });

  // --- T032 (US2): login-mode switch + email-collision auto-switch --------

  it('mode="login": submit() sends the login payload without a Turnstile token', () => {
    const { component, bindGuestSessionCalls } = setup({
      loggedIn: false,
      bindReturn: () =>
        of({ bound: true, group_id: 'g1', access_token: 'a1', refresh_token: 'r1' }),
    });
    component.switchMode('login');
    component.form.setValue({ email: 'existing@example.com', password: 's3cret' });

    component.submit();

    expect(bindGuestSessionCalls).toEqual([
      [
        'tok-123',
        {
          mode: 'login',
          email: 'existing@example.com',
          password: 's3cret',
          turnstile_token: null,
        },
      ],
    ]);
  });

  it('EMAIL_ALREADY_REGISTERED while in register mode auto-switches to login mode, keeping the typed email', () => {
    const apiError: ApiError = {
      errorCode: 'EMAIL_ALREADY_REGISTERED',
      i18nKey: 'errors.EMAIL_ALREADY_REGISTERED',
      detail: null,
      status: 409,
    };
    const { component } = setup({
      loggedIn: false,
      bindReturn: () => throwError(() => apiError),
    });
    component.mode.set('register');
    component.form.setValue({ email: 'taken@example.com', password: 'abc12345' });
    component.onTurnstileVerified('turnstile-token');

    component.submit();

    expect(component.mode()).toBe('login');
    expect(component.form.controls.email.value).toBe('taken@example.com');
    expect(component.form.controls.password.value).toBe('');
    expect(component.errorKey()).toBe('errors.EMAIL_ALREADY_REGISTERED');
  });
});
