import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { AuthService } from '../../features/auth/auth.service';
import { NotificationService } from '../../features/notifications/notification.service';
import { NavShellComponent } from './nav-shell.component';

describe('NavShellComponent', () => {
  let loggedIn: ReturnType<typeof signal<boolean>>;
  let initCalls: number;
  let resetCalls: number;

  function setup() {
    loggedIn = signal(false);
    initCalls = 0;
    resetCalls = 0;
    TestBed.configureTestingModule({
      imports: [NavShellComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: AuthService, useValue: { loggedIn } },
        {
          provide: NotificationService,
          useValue: {
            unreadCount: signal(0),
            init: () => {
              initCalls += 1;
            },
            reset: () => {
              resetCalls += 1;
            },
          },
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
  });

  it('member state shows home/groups/member-home link only, no login/register — logout lives on the member hub page instead (contract row 2)', () => {
    const fixture = setup();
    loggedIn.set(true);
    fixture.detectChanges();

    const links = hrefs(fixture);

    expect(links).toContain('/');
    expect(links).toContain('/groups');
    expect(links).toContain('/member');
    expect(links).not.toContain('/auth/login');
    expect(links).not.toContain('/auth/register');
    expect(fixture.nativeElement.querySelector('.nav-shell__logout')).toBeNull();
  });

  it('resets NotificationService on logout so a different member logging in on the same tab starts clean', () => {
    const fixture = setup();
    // Guest state (setup()'s initial loggedIn=false) already ran the
    // effect's else-branch once.
    expect(resetCalls).toBe(1);
    expect(initCalls).toBe(0);

    loggedIn.set(true);
    fixture.detectChanges();
    expect(initCalls).toBe(1);
    expect(resetCalls).toBe(1);

    loggedIn.set(false);
    fixture.detectChanges();
    expect(resetCalls).toBe(2);

    loggedIn.set(true);
    fixture.detectChanges();
    expect(initCalls).toBe(2);
  });
});
