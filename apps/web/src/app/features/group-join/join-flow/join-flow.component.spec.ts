import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../group-join.service';
import { JoinFlowComponent } from './join-flow.component';

function setup(options: {
  hasPassword: boolean;
  isLoggedIn: boolean;
  nickname?: string | null;
  existingGuestToken?: string | null;
  alreadyJoined?: boolean;
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
          resolveGuestSession: () => of({ nickname: '訪客' }),
          clearGuestSessionToken: () => undefined,
          verifyPassword: () => of({ correct: true }),
          join: () => of({ roster_entry_id: 'r1', nickname: '訪客' }),
        },
      },
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
