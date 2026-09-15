import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { AuthService } from '../auth.service';
import { LanguageService } from '../../../core/language/language.service';
import { OauthCallbackComponent } from './oauth-callback.component';

@Component({ selector: 'app-stub-member', template: '' })
class StubMemberComponent {}

@Component({ selector: 'app-stub-login', template: '' })
class StubLoginComponent {}

@Component({ selector: 'app-stub-group-member-view', template: '' })
class StubGroupMemberViewComponent {}

describe('OauthCallbackComponent', () => {
  function setup(hash: string, auth: Partial<AuthService> = {}) {
    window.location.hash = hash;
    TestBed.configureTestingModule({
      imports: [OauthCallbackComponent],
      providers: [
        provideRouter([
          { path: 'member', component: StubMemberComponent },
          { path: 'auth/login', component: StubLoginComponent },
          { path: 'groups/:groupId/member-view', component: StubGroupMemberViewComponent },
        ]),
        provideTranslateService({}),
        {
          provide: AuthService,
          useValue: {
            setTokens: vi.fn(),
            getMe: () => of({ language_preference: 'zh-TW' }) as never,
            ...auth,
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(OauthCallbackComponent);
    fixture.detectChanges();
    return fixture;
  }

  afterEach(() => {
    window.location.hash = '';
  });

  it('status=success stores the tokens and navigates to /member', async () => {
    const setTokens = vi.fn();
    const fixture = setup('#status=success&access_token=a1&refresh_token=r1&is_new_member=true', {
      setTokens,
    });
    await fixture.whenStable();

    expect(setTokens).toHaveBeenCalledWith('a1', 'r1');
    const router = TestBed.inject(Router);
    expect(router.url).toBe('/member');
  });

  it('status=success applies the fetched language_preference before navigating', async () => {
    const fixture = setup('#status=success&access_token=a1&refresh_token=r1&is_new_member=false', {
      getMe: () => of({ language_preference: 'en' }) as never,
    });
    await fixture.whenStable();

    const languageService = TestBed.inject(LanguageService);
    expect(languageService.current()).toBe('en');
  });

  // --- 028-guest-stats-binding T018 -------------------------------------

  it('status=success with bound_group_id navigates to that group\'s member-view instead of /member', async () => {
    const fixture = setup(
      '#status=success&access_token=a1&refresh_token=r1&is_new_member=false&bound_group_id=g42',
    );
    await fixture.whenStable();

    const router = TestBed.inject(Router);
    expect(router.url).toBe('/groups/g42/member-view');
  });

  it('status=success without bound_group_id keeps the existing default /member destination (regression)', async () => {
    const fixture = setup('#status=success&access_token=a1&refresh_token=r1&is_new_member=false');
    await fixture.whenStable();

    const router = TestBed.inject(Router);
    expect(router.url).toBe('/member');
  });

  it('status=cancelled navigates back to the login page', async () => {
    const fixture = setup('#status=cancelled');
    await fixture.whenStable();

    const router = TestBed.inject(Router);
    expect(router.url).toBe('/auth/login');
  });

  it('status=error shows the translated error and offers a link back to login', () => {
    const fixture = setup('#status=error&code=OAUTH_EMAIL_ALREADY_REGISTERED');

    expect(fixture.componentInstance.errorKey).toBe('errors.OAUTH_EMAIL_ALREADY_REGISTERED');
  });

  it('clears the hash immediately so the token pair never lingers in history', () => {
    setup('#status=success&access_token=a1&refresh_token=r1');

    expect(window.location.hash).toBe('');
  });
});
