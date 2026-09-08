import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { GroupJoinService } from '../group-join.service';
import { GuestAccessComponent } from './guest-access.component';

function setup(options: {
  noToken?: boolean;
  resolveError?: ApiError;
  navigate?: (...args: unknown[]) => Promise<boolean>;
}) {
  const setGuestSessionToken = vi.fn();
  const setActiveGuestGroupId = vi.fn();
  TestBed.configureTestingModule({
    imports: [GuestAccessComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            paramMap: convertToParamMap(options.noToken ? {} : { token: 'tok-123' }),
          },
        },
      },
      {
        provide: GroupJoinService,
        useValue: {
          resolveGuestSession: () =>
            options.resolveError
              ? throwError(() => options.resolveError)
              : of({ roster_entry_id: 'r1', group_id: 'g1', nickname: '小明' }),
          setGuestSessionToken,
          setActiveGuestGroupId,
        },
      },
      ...(options.navigate
        ? [{ provide: Router, useValue: { navigate: options.navigate } }]
        : []),
    ],
  });
  const fixture = TestBed.createComponent(GuestAccessComponent);
  fixture.detectChanges();
  return { fixture, setGuestSessionToken, setActiveGuestGroupId };
}

describe('GuestAccessComponent', () => {
  it('resolves a valid token, seeds the guest session, and navigates to member-view', () => {
    const navigateCalls: unknown[][] = [];
    const { setGuestSessionToken, setActiveGuestGroupId } = setup({
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    expect(setGuestSessionToken).toHaveBeenCalledWith('g1', 'tok-123');
    expect(setActiveGuestGroupId).toHaveBeenCalledWith('g1');
    expect(navigateCalls).toEqual([[['/groups', 'g1', 'member-view']]]);
  });

  it('an invalid/expired token shows an error instead of navigating', () => {
    const navigateCalls: unknown[][] = [];
    const { fixture } = setup({
      resolveError: { errorCode: 'LINK_NOT_FOUND', i18nKey: 'errors.LINK_NOT_FOUND', detail: null, status: 404 },
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    expect(navigateCalls).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
  });

  it('a missing token param shows an error instead of calling the service', () => {
    const { fixture } = setup({ noToken: true });

    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
  });
});
