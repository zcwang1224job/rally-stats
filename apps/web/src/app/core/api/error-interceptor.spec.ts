import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AuthService } from '../../features/auth/auth.service';
import { errorInterceptor } from './error-interceptor';

/** MEMBERSHIP_REQUIRED has exactly one source across the whole backend
 * (group/service.py resolve_active_roster_membership, gating every
 * group-member-view read endpoint) and always means the same thing: the
 * viewer's own RosterEntry stopped being active mid-session — left
 * elsewhere, or kicked. A global redirect here covers all three tabs
 * (schedule/standings/match-records), whichever is active when it
 * happens, without each duplicating its own redirect logic. */
describe('errorInterceptor: MEMBERSHIP_REQUIRED redirect', () => {
  function setup() {
    const navigateCalls: unknown[][] = [];
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: { getRefreshToken: () => null } },
        {
          provide: Router,
          useValue: {
            navigate: (...args: unknown[]) => {
              navigateCalls.push(args);
              return Promise.resolve(true);
            },
          },
        },
      ],
    });
    return {
      http: TestBed.inject(HttpClient),
      httpMock: TestBed.inject(HttpTestingController),
      navigateCalls,
    };
  }

  it('navigates to /groups when a request fails with MEMBERSHIP_REQUIRED', () => {
    const { http, httpMock, navigateCalls } = setup();

    let caughtError: { errorCode: string } | undefined;
    http.get('/api/groups/g1/standings').subscribe({
      error: (err: { errorCode: string }) => (caughtError = err),
    });

    httpMock
      .expectOne('/api/groups/g1/standings')
      .flush({ error_code: 'MEMBERSHIP_REQUIRED', detail: {} }, { status: 403, statusText: 'Forbidden' });

    expect(navigateCalls).toEqual([[['/groups']]]);
    expect(caughtError?.errorCode).toBe('MEMBERSHIP_REQUIRED');
  });

  it('does not navigate for an unrelated error code', () => {
    const { http, httpMock, navigateCalls } = setup();

    http.get('/api/groups/g1/standings').subscribe({ error: () => undefined });

    httpMock
      .expectOne('/api/groups/g1/standings')
      .flush({ error_code: 'GROUP_NOT_FOUND', detail: {} }, { status: 404, statusText: 'Not Found' });

    expect(navigateCalls).toEqual([]);
  });
});
