import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import { AuthService } from '../auth/auth.service';
import { GroupJoinService } from '../group-join/group-join.service';
import { GroupMemberViewService } from './group-member-view.service';

// 037-rest-ready-toggle: setOwnRestState() carries the same identity as
// leaveGroup() — a logged-in Member never sends a leftover Guest token,
// which the backend would trust over their login.
describe('GroupMemberViewService.setOwnRestState', () => {
  function setup(loggedIn: boolean) {
    const calls: { path: string; body: unknown; headers?: Record<string, string> }[] = [];
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ApiClient,
          useValue: {
            put: (path: string, body: unknown, headers?: Record<string, string>) => {
              calls.push({ path, body, headers });
              return of({});
            },
          },
        },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => loggedIn,
            getAccessToken: () => (loggedIn ? 'member-tok' : null),
          },
        },
        { provide: GroupJoinService, useValue: { getGuestSessionToken: () => 'guest-tok' } },
      ],
    });
    return { service: TestBed.inject(GroupMemberViewService), calls };
  }

  it('sends a Guest token for a Guest', () => {
    const { service, calls } = setup(false);

    service.setOwnRestState('g1', 'r1', true).subscribe();

    expect(calls).toEqual([
      {
        path: '/groups/g1/roster/r1/rest-state',
        body: { resting: true, confirm_round_end: false, guest_session_token: 'guest-tok' },
        headers: {},
      },
    ]);
  });

  it('sends only the login for a Member, never a leftover Guest token', () => {
    const { service, calls } = setup(true);

    service.setOwnRestState('g1', 'r1', false, true).subscribe();

    expect(calls[0].body).toEqual({
      resting: false,
      confirm_round_end: true,
      guest_session_token: null,
    });
    expect(calls[0].headers).toEqual({ Authorization: 'Bearer member-tok' });
  });
});
