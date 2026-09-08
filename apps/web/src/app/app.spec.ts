import { TestBed } from '@angular/core/testing';
import { Component, signal } from '@angular/core';
import { provideRouter, Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { AuthService } from './features/auth/auth.service';
import { NotificationService } from './features/notifications/notification.service';
import { App } from './app';

@Component({ selector: 'app-stub', template: '' })
class StubComponent {}

describe('App', () => {
  async function setup(): Promise<import('@angular/core/testing').ComponentFixture<App>> {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([
          { path: '', component: StubComponent },
          { path: 'groups/:groupId/admin', component: StubComponent, data: { navShell: false } },
          { path: 'groups', component: StubComponent },
        ]),
        provideTranslateService({}),
        { provide: AuthService, useValue: { loggedIn: () => false, logout: () => undefined } },
        {
          provide: NotificationService,
          useValue: { unreadCount: signal(0), init: () => undefined, reset: () => undefined },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    return fixture;
  }

  it('should create the app', async () => {
    const fixture = await setup();
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('shows the nav shell on a route without navShell: false', async () => {
    const fixture = await setup();
    const router = TestBed.inject(Router);

    await router.navigateByUrl('/groups');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-nav-shell')).not.toBeNull();
  });

  it('hides the nav shell on a route with data.navShell: false', async () => {
    const fixture = await setup();
    const router = TestBed.inject(Router);

    await router.navigateByUrl('/groups/g1/admin');
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-nav-shell')).toBeNull();
  });
});
