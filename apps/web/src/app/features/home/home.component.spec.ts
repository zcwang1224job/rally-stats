import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { AuthService } from '../auth/auth.service';
import { GroupAdminService } from '../group-admin/group-admin.service';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  function setup(loggedIn: boolean, lastCreatedGroupId: string | null = null) {
    TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: AuthService, useValue: { loggedIn: signal(loggedIn) } },
        {
          provide: GroupAdminService,
          useValue: { getLastCreatedGroupId: () => lastCreatedGroupId },
        },
      ],
    });
    const fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();
    return fixture;
  }

  function hrefs(fixture: ReturnType<typeof setup>): string[] {
    return Array.from<HTMLAnchorElement>(
      fixture.nativeElement.querySelectorAll('a[href]'),
    ).map((a) => a.getAttribute('href') ?? '');
  }

  it('guest, never created a group this session: shows browse groups, create group, login, and register entry points, no back-to-admin shortcut', () => {
    const fixture = setup(false);

    const links = hrefs(fixture);

    expect(links).toContain('/groups');
    expect(links).toContain('/groups/new');
    expect(links).toContain('/auth/login');
    expect(links).toContain('/auth/register');
    expect(links).not.toContain('/member');
    expect(links.some((href) => href.includes('/admin'))).toBe(false);
  });

  it('guest who created a group this session: shows a shortcut straight to that group\'s admin page', () => {
    const fixture = setup(false, 'g1');

    const links = hrefs(fixture);

    expect(links).toContain('/groups/g1/admin');
  });

  it('logged in: login/register entries are replaced by a single member-area entry, no back-to-admin shortcut even with a remembered group', () => {
    const fixture = setup(true, 'g1');

    const links = hrefs(fixture);

    expect(links).toContain('/groups');
    expect(links).toContain('/groups/new');
    expect(links).toContain('/member');
    expect(links).not.toContain('/auth/login');
    expect(links).not.toContain('/auth/register');
    expect(links.some((href) => href.includes('/admin'))).toBe(false);
  });
});
