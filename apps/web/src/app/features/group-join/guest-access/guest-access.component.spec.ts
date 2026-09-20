import { Component, input } from '@angular/core';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { BindingStatusResponse } from '../../../core/api/group-join.models';
import { GroupJoinService } from '../group-join.service';
import { GuestBindingCtaComponent } from '../guest-binding-cta/guest-binding-cta.component';
import { GuestAccessComponent } from './guest-access.component';

/** The real `GuestBindingCtaComponent` injects `AuthService` (-> HttpClient,
 * unprovided here) — this test suite is only concerned with
 * GuestAccessComponent's own three-way branching, already covered
 * separately in guest-binding-cta.component.spec.ts. */
@Component({ selector: 'app-guest-binding-cta', template: '' })
class StubGuestBindingCtaComponent {
  readonly guestSessionToken = input.required<string>();
}

const ACTIVE_STATUS: BindingStatusResponse = {
  already_bound: false,
  roster_entry_id: 'r1',
  group_id: 'g1',
  group_name: '測試團',
  nickname: '小明',
  group_status: 'active',
  roster_status: 'active',
  already_in_group: false,
};

function setup(options: {
  noToken?: boolean;
  status?: BindingStatusResponse;
  statusError?: ApiError;
  navigate?: (...args: unknown[]) => Promise<boolean>;
}) {
  const setGuestSessionToken = vi.fn();
  const setActiveGuestGroupId = vi.fn();
  const clearGuestSessionToken = vi.fn();
  const getGuestBindingStatus = vi.fn(() =>
    options.statusError
      ? throwError(() => options.statusError)
      : of(options.status ?? ACTIVE_STATUS),
  );
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
          getGuestBindingStatus,
          setGuestSessionToken,
          setActiveGuestGroupId,
          clearGuestSessionToken,
        },
      },
      ...(options.navigate
        ? [{ provide: Router, useValue: { navigate: options.navigate } }]
        : []),
    ],
  });
  TestBed.overrideComponent(GuestAccessComponent, {
    remove: { imports: [GuestBindingCtaComponent] },
    add: { imports: [StubGuestBindingCtaComponent] },
  });
  const fixture = TestBed.createComponent(GuestAccessComponent);
  fixture.detectChanges();
  return {
    fixture,
    setGuestSessionToken,
    setActiveGuestGroupId,
    clearGuestSessionToken,
    getGuestBindingStatus,
  };
}

describe('GuestAccessComponent', () => {
  it('現役未綁定 (active roster + active group): seeds the guest session and navigates to member-view', () => {
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

  it('已綁定: navigates to the login page instead of member-view (research.md #5)', () => {
    const navigateCalls: unknown[][] = [];
    const { clearGuestSessionToken } = setup({
      status: { ...ACTIVE_STATUS, already_bound: true },
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    expect(navigateCalls).toEqual([[['/auth/login']]]);
    // Bug fix: clears any stale stored token so GroupMemberViewComponent
    // can't later be fooled into thinking this browser is still a Guest.
    expect(clearGuestSessionToken).toHaveBeenCalledWith('g1');
  });

  it.each([
    ['left roster, active group', { ...ACTIVE_STATUS, roster_status: 'left' as const }],
    ['kicked roster, active group', { ...ACTIVE_STATUS, roster_status: 'kicked' as const }],
    ['active roster, disbanded group', { ...ACTIVE_STATUS, group_status: 'disbanded' as const }],
  ])('非現役未綁定 (%s): renders the 個人戰績摘要 screen in place, without navigating', (_label, status) => {
    const navigateCalls: unknown[][] = [];
    const { fixture } = setup({
      status,
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    expect(navigateCalls).toEqual([]);
    expect(fixture.componentInstance.status()).toBe('summary');
    expect(fixture.nativeElement.textContent).toContain('測試團');
    expect(fixture.nativeElement.textContent).toContain('小明');
    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).not.toBeNull();
  });

  it('非現役未綁定, but the logged-in account is already on this roster: no binding entry point', () => {
    // 團長 opening a kicked guest's own link from their own group — the
    // backend would refuse the bind with MEMBER_ALREADY_IN_GROUP, so the
    // entry point must not be offered in the first place.
    const { fixture } = setup({
      status: {
        ...ACTIVE_STATUS,
        roster_status: 'kicked' as const,
        already_in_group: true,
      },
    });

    expect(fixture.componentInstance.status()).toBe('summary');
    expect(fixture.nativeElement.textContent).toContain('測試團');
    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).toBeNull();
  });

  it('an invalid/expired token shows an error instead of navigating', () => {
    const navigateCalls: unknown[][] = [];
    const { fixture } = setup({
      statusError: {
        errorCode: 'LINK_NOT_FOUND',
        i18nKey: 'errors.LINK_NOT_FOUND',
        detail: null,
        status: 404,
      },
      navigate: (...args: unknown[]) => {
        navigateCalls.push(args);
        return Promise.resolve(true);
      },
    });

    expect(navigateCalls).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
  });

  it('a missing token param shows an error instead of calling the service', () => {
    const { fixture, getGuestBindingStatus } = setup({ noToken: true });

    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
    expect(getGuestBindingStatus).not.toHaveBeenCalled();
  });
});
