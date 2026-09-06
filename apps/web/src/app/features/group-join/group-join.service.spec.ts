import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of, throwError } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import { AuthService } from '../auth/auth.service';
import { GroupJoinService } from './group-join.service';

const ACTIVE_GUEST_GROUP_KEY = 'rally-stats:guest-active-group-id';
const GUEST_TOKEN_KEY_PREFIX = 'rally-stats:guest-session-token:';

describe('GroupJoinService: verifyActiveGuestGroupId', () => {
  afterEach(() => {
    localStorage.clear();
  });

  function setup(apiGet: (path: string) => unknown) {
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: { get: apiGet } },
        { provide: AuthService, useValue: { getAccessToken: () => null } },
      ],
    });
    return TestBed.inject(GroupJoinService);
  }

  it('returns null immediately, with no API call, when no group is tracked', async () => {
    const getSpy = vi.fn();
    const service = setup(getSpy);

    const result = await firstValueFrom(service.verifyActiveGuestGroupId());

    expect(result).toBeNull();
    expect(getSpy).not.toHaveBeenCalled();
  });

  describe('no guest_session_token on file for the tracked group (e.g. stale data)', () => {
    it('returns the group id when the group is still active', async () => {
      localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, 'g1');
      const service = setup(() => of({ status: 'active' }));

      const result = await firstValueFrom(service.verifyActiveGuestGroupId());

      expect(result).toBe('g1');
    });

    it('clears the marker and returns null when the group has disbanded', async () => {
      localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, 'g1');
      const service = setup(() => of({ status: 'disbanded' }));

      const result = await firstValueFrom(service.verifyActiveGuestGroupId());

      expect(result).toBeNull();
      expect(localStorage.getItem(ACTIVE_GUEST_GROUP_KEY)).toBeNull();
    });

    it('clears the marker and returns null when the group no longer exists', async () => {
      localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, 'g1');
      const service = setup(() => throwError(() => new Error('404')));

      const result = await firstValueFrom(service.verifyActiveGuestGroupId());

      expect(result).toBeNull();
      expect(localStorage.getItem(ACTIVE_GUEST_GROUP_KEY)).toBeNull();
    });
  });

  describe('a guest_session_token is on file for the tracked group', () => {
    it('returns the group id when resolveGuestSession succeeds (Guest still active there)', async () => {
      localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, 'g1');
      localStorage.setItem(GUEST_TOKEN_KEY_PREFIX + 'g1', 'tok-1');
      const getSpy = vi.fn(() =>
        of({ roster_entry_id: 'r1', group_id: 'g1', nickname: '訪客' }),
      );
      const service = setup(getSpy);

      const result = await firstValueFrom(service.verifyActiveGuestGroupId());

      expect(result).toBe('g1');
      expect(getSpy).toHaveBeenCalledWith('/groups/by-guest-token/tok-1');
      expect(localStorage.getItem(GUEST_TOKEN_KEY_PREFIX + 'g1')).toBe('tok-1');
    });

    /** Regression: this is the case the plain group-status check (used
     * above when no token is on file) cannot detect — the group itself
     * stays active (other members remain), only this Guest's own
     * RosterEntry stopped being active. resolveGuestSession() checks that,
     * a plain GET /groups/{id} does not. */
    it('clears both the marker and the token, and returns null, when this Guest was kicked (group still active)', async () => {
      localStorage.setItem(ACTIVE_GUEST_GROUP_KEY, 'g1');
      localStorage.setItem(GUEST_TOKEN_KEY_PREFIX + 'g1', 'tok-1');
      const service = setup(() => throwError(() => new Error('404 LINK_NOT_FOUND')));

      const result = await firstValueFrom(service.verifyActiveGuestGroupId());

      expect(result).toBeNull();
      expect(localStorage.getItem(ACTIVE_GUEST_GROUP_KEY)).toBeNull();
      expect(localStorage.getItem(GUEST_TOKEN_KEY_PREFIX + 'g1')).toBeNull();
    });
  });
});
