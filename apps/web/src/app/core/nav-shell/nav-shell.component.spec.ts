import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { AuthService } from '../../features/auth/auth.service';
import { NotificationService } from '../../features/notifications/notification.service';
import { NavShellComponent } from './nav-shell.component';

describe('NavShellComponent', () => {
  let loggedIn: ReturnType<typeof signal<boolean>>;
  let logoutCalls: number;

  function setup() {
    loggedIn = signal(false);
    logoutCalls = 0;
    TestBed.configureTestingModule({
      imports: [NavShellComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        {
          provide: AuthService,
          useValue: {
            loggedIn,
            logout: () => {
              logoutCalls += 1;
              loggedIn.set(false);
            },
          },
        },
        {
          provide: NotificationService,
          useValue: { unreadCount: signal(0), init: () => undefined },
        },
      ],
    });
    const fixture = TestBed.createComponent(NavShellComponent);
    fixture.detectChanges();
    return fixture;
  }

  function hrefs(fixture: ReturnType<typeof setup>): string[] {
    return Array.from<HTMLAnchorElement>(
      fixture.nativeElement.querySelectorAll('a[href]'),
    ).map((a) => a.getAttribute('href') ?? '');
  }

  it('guest state shows home/groups/login/register only (contract row 1)', () => {
    const fixture = setup();

    const links = hrefs(fixture);

    expect(links).toContain('/');
    expect(links).toContain('/groups');
    expect(links).toContain('/auth/login');
    expect(links).toContain('/auth/register');
    expect(links).not.toContain('/member');
    expect(links).not.toContain('/member/settings');
    expect(links).not.toContain('/member/match-history');
    expect(fixture.nativeElement.querySelector('.nav-shell__logout')).toBeNull();
  });

  it('member state shows home/groups/member links + logout, no login/register (contract row 2)', () => {
    const fixture = setup();
    loggedIn.set(true);
    fixture.detectChanges();

    const links = hrefs(fixture);

    expect(links).toContain('/');
    expect(links).toContain('/groups');
    expect(links).toContain('/member');
    expect(links).toContain('/member/settings');
    expect(links).toContain('/member/match-history');
    expect(links).toContain('/friends');
    expect(links).not.toContain('/auth/login');
    expect(links).not.toContain('/auth/register');
    expect(fixture.nativeElement.querySelector('.nav-shell__logout')).not.toBeNull();
  });

  it('activating logout calls AuthService.logout() and the shell falls back to guest links (contract row 5)', () => {
    const fixture = setup();
    loggedIn.set(true);
    fixture.detectChanges();

    const logoutButton = fixture.nativeElement.querySelector(
      '.nav-shell__logout',
    ) as HTMLButtonElement | null;
    logoutButton?.click();
    fixture.detectChanges();

    expect(logoutCalls).toBe(1);
    const links = hrefs(fixture);
    expect(links).toContain('/auth/login');
    expect(links).toContain('/auth/register');
    expect(links).not.toContain('/member');
  });

  it('when logged in, all three member routes are reachable simultaneously, not nested behind which member page is active (US3, FR-007)', () => {
    const fixture = setup();
    loggedIn.set(true);
    fixture.detectChanges();

    const links = hrefs(fixture);

    expect(links).toEqual(
      expect.arrayContaining(['/member', '/member/settings', '/member/match-history']),
    );
  });

  it('logout is reachable regardless of which member route is conceptually active (US3 scenario 2)', () => {
    const fixture = setup();
    loggedIn.set(true);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.nav-shell__logout')).not.toBeNull();
  });
});
