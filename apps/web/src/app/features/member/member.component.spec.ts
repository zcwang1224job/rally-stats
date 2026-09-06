import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { MemberComponent } from './member.component';

const member = {
  member_id: 'm1',
  email: 'a@example.com',
  nickname: '小明',
  user_number: 'U1',
  verification_status: 'verified' as const,
};

describe('MemberComponent', () => {
  let logoutCalls = 0;

  function setup() {
    logoutCalls = 0;
    TestBed.configureTestingModule({
      imports: [MemberComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => true,
            getMe: () => of(member),
            clearTokens: () => undefined,
            logout: () => {
              logoutCalls += 1;
            },
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(MemberComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('renders all 5 menu rows: match history, friends, my groups, settings, logout', () => {
    const fixture = setup();

    const hrefs = Array.from<HTMLAnchorElement>(
      fixture.nativeElement.querySelectorAll('.member-links a[href]'),
    ).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/member/match-history');
    expect(hrefs).toContain('/friends');
    expect(hrefs).toContain('/member/my-groups');
    expect(hrefs).toContain('/member/settings');
    expect(fixture.nativeElement.querySelector('.logout-action')).not.toBeNull();
  });

  it('clicking logout calls AuthService.logout() and navigates home', async () => {
    const fixture = setup();
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl');

    const logoutButton = fixture.nativeElement.querySelector('.logout-action') as HTMLButtonElement | null;
    logoutButton?.click();

    expect(logoutCalls).toBe(1);
    expect(navigateSpy).toHaveBeenCalledWith('/');
  });
});
