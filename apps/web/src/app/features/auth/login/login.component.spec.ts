import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { AuthService } from '../auth.service';
import { LanguageService } from '../../../core/language/language.service';
import { LoginComponent } from './login.component';

const REMEMBERED_EMAIL_KEY = 'rally-stats:remembered-login-email';

@Component({ selector: 'app-stub-member', template: '' })
class StubMemberComponent {}

const defaultLoginResponse = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  member: { language_preference: 'zh-TW' },
};

const defaultAuth: Partial<AuthService> = {
  login: () => of(defaultLoginResponse) as never,
  startOAuthFlow: () => of({ authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' }) as never,
};

describe('LoginComponent', () => {
  function setup(auth: Partial<AuthService> = defaultAuth) {
    TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([{ path: 'member', component: StubMemberComponent }]),
        provideTranslateService({}),
        { provide: AuthService, useValue: auth },
      ],
    });
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => {
    localStorage.clear();
  });

  it('no remembered email: the form starts blank with the checkbox unchecked, and focus is left alone', () => {
    const fixture = setup();

    expect(fixture.componentInstance.form.controls.email.value).toBe('');
    expect(fixture.componentInstance.form.controls.rememberEmail.value).toBe(false);
    expect(document.activeElement?.getAttribute('formcontrolname')).not.toBe('password');
  });

  it('a remembered email: prefills the field, checks the box, and moves focus straight to the password field', () => {
    localStorage.setItem(REMEMBERED_EMAIL_KEY, 'a@example.com');

    const fixture = setup();

    expect(fixture.componentInstance.form.controls.email.value).toBe('a@example.com');
    expect(fixture.componentInstance.form.controls.rememberEmail.value).toBe(true);
    expect(document.activeElement).toBe(fixture.componentInstance.passwordInput()?.nativeElement);
  });

  it('submitting with the box checked stores the email for next time', () => {
    const fixture = setup();
    fixture.componentInstance.form.setValue({
      email: 'b@example.com',
      password: 'abc12345',
      rememberEmail: true,
    });

    fixture.componentInstance.submit();

    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBe('b@example.com');
  });

  it('submitting with the box unchecked clears any previously remembered email', () => {
    localStorage.setItem(REMEMBERED_EMAIL_KEY, 'old@example.com');
    const fixture = setup();
    fixture.componentInstance.form.setValue({
      email: 'old@example.com',
      password: 'abc12345',
      rememberEmail: false,
    });

    fixture.componentInstance.submit();

    expect(localStorage.getItem(REMEMBERED_EMAIL_KEY)).toBeNull();
  });

  // 024-add-english-language FR-003b/US2#3
  it('applies the account\'s language_preference on successful login, overriding any prior local value', () => {
    localStorage.setItem('rally-stats:language', 'en');
    const fixture = setup({
      login: () =>
        of({
          access_token: 'a',
          refresh_token: 'r',
          member: { language_preference: 'zh-TW' },
        }) as never,
    });
    fixture.componentInstance.form.setValue({
      email: 'c@example.com',
      password: 'abc12345',
      rememberEmail: false,
    });

    fixture.componentInstance.submit();

    const languageService = TestBed.inject(LanguageService);
    expect(languageService.current()).toBe('zh-TW');
    expect(localStorage.getItem('rally-stats:language')).toBe('zh-TW');
  });

  // 027-google-line-oauth-login US1/US2
  it('renders both OAuth continue buttons', () => {
    const fixture = setup();
    const buttons = fixture.nativeElement.querySelectorAll('.oauth-buttons button');
    expect(buttons.length).toBe(2);
  });

  it('clicking "使用 Google 繼續" fetches the authorize_url with intent=login and navigates there', () => {
    const startOAuthFlow = vi.fn(
      () => of({ authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' }) as never,
    );
    const fixture = setup({ ...defaultAuth, startOAuthFlow });
    const navigateSpy = vi.spyOn(
      fixture.componentInstance as unknown as { navigateToAuthorizeUrl: (url: string) => void },
      'navigateToAuthorizeUrl',
    );

    fixture.componentInstance.continueWithOAuth('google');

    expect(startOAuthFlow).toHaveBeenCalledWith('google', 'login');
    expect(navigateSpy).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1');
  });

  it('clicking "使用 LINE 繼續" fetches the authorize_url with intent=login', () => {
    const startOAuthFlow = vi.fn(
      () => of({ authorize_url: 'https://access.line.me/oauth2/v2.1/authorize?x=1' }) as never,
    );
    const fixture = setup({ ...defaultAuth, startOAuthFlow });
    vi.spyOn(
      fixture.componentInstance as unknown as { navigateToAuthorizeUrl: (url: string) => void },
      'navigateToAuthorizeUrl',
    );

    fixture.componentInstance.continueWithOAuth('line');

    expect(startOAuthFlow).toHaveBeenCalledWith('line', 'login');
  });

  it('shows an error message when starting the OAuth flow fails', () => {
    const startOAuthFlow = vi.fn(
      () => throwError(() => ({ i18nKey: 'errors.OAUTH_PROVIDER_ERROR' })) as never,
    );
    const fixture = setup({ ...defaultAuth, startOAuthFlow });

    fixture.componentInstance.continueWithOAuth('google');

    expect(fixture.componentInstance.errorKey()).toBe('errors.OAUTH_PROVIDER_ERROR');
  });
});
