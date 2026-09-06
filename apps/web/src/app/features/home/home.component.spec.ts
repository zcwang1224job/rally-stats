import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { AuthService } from '../auth/auth.service';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  function setup(loggedIn: boolean) {
    TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: AuthService, useValue: { loggedIn: signal(loggedIn) } },
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

  it('guest: shows browse groups, create group, login, and register entry points', () => {
    const fixture = setup(false);

    const links = hrefs(fixture);

    expect(links).toContain('/groups');
    expect(links).toContain('/groups/new');
    expect(links).toContain('/groups/reauth');
    expect(links).toContain('/auth/login');
    expect(links).toContain('/auth/register');
    expect(links).not.toContain('/member');
  });

  it('logged in: login/register entries are replaced by a single member-area entry', () => {
    const fixture = setup(true);

    const links = hrefs(fixture);

    expect(links).toContain('/groups');
    expect(links).toContain('/groups/new');
    expect(links).toContain('/groups/reauth');
    expect(links).toContain('/member');
    expect(links).not.toContain('/auth/login');
    expect(links).not.toContain('/auth/register');
  });
});
