import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../group-join.service';
import { JoinFlowComponent } from './join-flow.component';

function setup(options: {
  hasPassword: boolean;
  isLoggedIn: boolean;
  nickname?: string | null;
  existingGuestToken?: string | null;
  alreadyJoined?: boolean;
  joinError?: ApiError;
  navigate?: (...args: unknown[]) => Promise<boolean>;
  activeGuestGroupId?: string | null;
}) {
  TestBed.configureTestingModule({
    imports: [JoinFlowComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ groupId: 'g1' }) } },
      },
      {
        provide: ApiClient,
        useValue: {
          get: () =>
            of({ has_password: options.hasPassword, already_joined: options.alreadyJoined ?? null }),
        },
      },
      {
        provide: AuthService,
        useValue: {
          isLoggedIn: () => options.isLoggedIn,
          getMe: () => of({ nickname: options.nickname ?? '會員' }),
          getAccessToken: () => (options.isLoggedIn ? 'fake-token' : null),
        },
      },
      {
        provide: GroupJoinService,
        useValue: {
          getGuestSessionToken: () => options.existingGuestToken ?? null,
          getActiveGuestGroupId: () => options.activeGuestGroupId ?? null,
          resolveGuestSession: () => of({ nickname: '訪客' }),
          clearGuestSessionToken: () => undefined,
          verifyPassword: () => of({ correct: true }),
          join: () =>
            options.joinError
              ? throwError(() => options.joinError)
              : of({ roster_entry_id: 'r1', nickname: '訪客' }),
        },
      },
      ...(options.navigate
        ? [{ provide: Router, useValue: { navigate: options.navigate } }]
        : []),
    ],
  });
  const fixture = TestBed.createComponent(JoinFlowComponent);
  fixture.detectChanges();
  return fixture;
}

describe('JoinFlowComponent (US5 modal presentation)', () => {
  it('renders every step inside a centered <dialog>', () => {
    const fixture = setup({ hasPassword: false, isLoggedIn: false });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog).not.toBeNull();
    expect(dialog.querySelector('input[formcontrolname="nickname"]')).not.toBeNull();
  });

  it('guest, password-protected group: shows the password step inside the dialog', () => {
    const fixture = setup({ hasPassword: true, isLoggedIn: false });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="password"]')).not.toBeNull();
  });

  it('logged-in member with a nickname skips the nickname step, going straight to confirm', () => {
    const fixture = setup({ hasPassword: false, isLoggedIn: true, nickname: '小明' });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="nickname"]')).toBeNull();
    expect(dialog.querySelector('button')).not.toBeNull();
  });

  it('logged-in member who already joined a password-protected group skips straight to done, no password prompt', () => {
    const fixture = setup({
      hasPassword: true,
      isLoggedIn: true,
      nickname: '小明',
      alreadyJoined: true,
    });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="password"]')).toBeNull();
    expect(dialog.textContent).toContain('groupJoin.successTitle');
  });
});

/** Retrying the join button can't ever succeed for this specific error —
 * the member has to leave their other group first, not resubmit the same
 * request — so the confirm step swaps the join button for a way back to
 * the list instead of leaving a dead-end retry button up. */
describe('JoinFlowComponent: ALREADY_ACTIVE_IN_ANOTHER_GROUP on the confirm step', () => {
  it('replaces the join button with a "back to list" button, and clicking it navigates to /groups', () => {
    const navigateCalls: unknown[][] = [];
    const fixture = setup({
      hasPassword: false,
      isLoggedIn: true,
      nickname: '小明',
      joinError: {
        errorCode: 'ALREADY_ACTIVE_IN_ANOTHER_GROUP',
        i18nKey: 'errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP',
        detail: null,
        status: 409,
      },
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    fixture.componentInstance.confirmMemberJoin();
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    const buttonText = (dialog.querySelector('button') as HTMLButtonElement).textContent ?? '';
    expect(buttonText).toContain('groupJoin.backToList');
    expect(buttonText).not.toContain('groupJoin.joinSubmit');

    (dialog.querySelector('button') as HTMLButtonElement).click();

    expect(navigateCalls).toEqual([[['/groups']]]);
  });

  it('a different join error leaves the normal join (retry) button in place', () => {
    const fixture = setup({
      hasPassword: false,
      isLoggedIn: true,
      nickname: '小明',
      joinError: { errorCode: 'GROUP_FULL', i18nKey: 'errors.GROUP_FULL', detail: null, status: 409 },
    });

    fixture.componentInstance.confirmMemberJoin();
    fixture.detectChanges();

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    const buttonText = (dialog.querySelector('button') as HTMLButtonElement).textContent ?? '';
    expect(buttonText).toContain('groupJoin.joinSubmit');
  });
});

/** Same-browser-only Guest nicety (research: one-active-group-per-Member
 * follow-up) — there's no cross-group identity to check server-side for a
 * Guest, so this is enforced entirely client-side via a localStorage
 * marker (group-join.service.ts's setActiveGuestGroupId()). Blocks before
 * the Guest even fills in a nickname, since submitting would just fail
 * anyway once it reached the backend (nothing there would reject it any
 * earlier for a Guest). */
describe('JoinFlowComponent: Guest already active in a different group (same browser)', () => {
  it('shows the error step with a back-to-list button, skipping the nickname form entirely', () => {
    const navigateCalls: unknown[][] = [];
    const fixture = setup({
      hasPassword: false,
      isLoggedIn: false,
      activeGuestGroupId: 'some-other-group',
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="nickname"]')).toBeNull();
    expect(dialog.textContent).toContain('errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP');

    (dialog.querySelector('button') as HTMLButtonElement).click();
    expect(navigateCalls).toEqual([[['/groups']]]);
  });

  it('does not block a Guest whose tracked active group IS this one', () => {
    const fixture = setup({
      hasPassword: false,
      isLoggedIn: false,
      activeGuestGroupId: 'g1',
    });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="nickname"]')).not.toBeNull();
  });

  it('does not block a Guest with no tracked active group', () => {
    const fixture = setup({
      hasPassword: false,
      isLoggedIn: false,
      activeGuestGroupId: null,
    });

    const dialog = fixture.nativeElement.querySelector('dialog.join-dialog');
    expect(dialog.querySelector('input[formcontrolname="nickname"]')).not.toBeNull();
  });
});
