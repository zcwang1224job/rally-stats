import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of, throwError } from 'rxjs';
import { AuthService } from '../../auth/auth.service';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { GroupJoinService } from '../group-join.service';
import { GroupListComponent } from './group-list.component';

const group = {
  group_id: 'g1',
  group_number: 1,
  name: '週三夜羽球團',
  has_password: false,
  current_member_count: 4,
  max_members: 8,
  match_mode: 'doubles' as const,
  scheduling_mechanism: 'fair_rotation' as const,
  activity_time_start: '19:00',
  activity_time_end: '21:00',
  status: 'active' as const,
  court_names: ['場地一'],
  creator_nickname: '王小明',
  joined_by_me: false,
};

function setup(
  totalPages: number,
  groups: unknown[] = [group],
  options: {
    getCreatorAdminToken?: () => Observable<{ admin_token: string; group_id: string }>;
    isLoggedIn?: boolean;
    activeGuestGroupId?: string | null;
    verifiedActiveGuestGroupId?: string | null;
    listGroups?: (...args: unknown[]) => Observable<unknown>;
  } = {},
) {
  TestBed.configureTestingModule({
    imports: [GroupListComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: GroupJoinService,
        useValue: {
          listGroups:
            options.listGroups ?? (() => of({ groups, page: 1, total_pages: totalPages })),
          getActiveGuestGroupId: () => options.activeGuestGroupId ?? null,
          verifyActiveGuestGroupId: () =>
            of(
              'verifiedActiveGuestGroupId' in options
                ? (options.verifiedActiveGuestGroupId as string | null)
                : (options.activeGuestGroupId ?? null),
            ),
        },
      },
      {
        provide: GroupAdminService,
        useValue: {
          getCreatorAdminToken:
            options.getCreatorAdminToken ??
            (() => of({ admin_token: 'fresh-admin-token', group_id: 'g1' })),
          setAdminToken: () => undefined,
        },
      },
      {
        provide: AuthService,
        useValue: {
          getAccessToken: () => 'fake-member-token',
          isLoggedIn: () => options.isLoggedIn ?? true,
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(GroupListComponent);
  fixture.detectChanges();
  return fixture;
}

describe('GroupListComponent', () => {
  it('shows an error instead of a stuck loading spinner when the initial fetch fails', () => {
    const fixture = setup(1, [], {
      listGroups: () =>
        throwError(() => ({ errorCode: 'SOMETHING', i18nKey: 'errors.SOMETHING' })),
    });

    expect(fixture.componentInstance.loading()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('errors.SOMETHING');
  });

  it('shows a create-group entry point in the page header', () => {
    const fixture = setup(1);

    const link = fixture.nativeElement.querySelector('a[href="/groups/new"]');
    expect(link).not.toBeNull();
  });

  it('shows match mode and activity time on each card', () => {
    const fixture = setup(1);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('createGroup.matchModeDoubles');
    expect(text).toContain('19:00');
    expect(text).toContain('21:00');
  });

  it('shows every court name for a group, without any court ID', () => {
    const twoCourtGroup = { ...group, court_names: ['1號場', '2號場'] };
    const fixture = setup(1, [twoCourtGroup]);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('1號場');
    expect(text).toContain('2號場');
    expect(fixture.nativeElement.querySelector('input[formcontrolname="court_id"]')).toBeNull();
  });

  it('sends group name, creator nickname, and match mode filters when applied', () => {
    const listGroups = vi.fn(() => of({ groups: [group], page: 1, total_pages: 1 }));
    const fixture = setup(1, [group], { listGroups });

    fixture.componentInstance.filterForm.patchValue({
      group_name: '夜羽球',
      creator_nickname: '王小明',
      match_mode: 'singles',
    });
    fixture.componentInstance.applyFilters();

    expect(listGroups).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        group_name: '夜羽球',
        creator_nickname: '王小明',
        match_mode: 'singles',
      }),
    );
  });

  it('shows an empty-state message instead of the grid when no groups match', () => {
    const fixture = setup(1, []);

    expect(fixture.nativeElement.querySelector('.empty-state')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.group-grid li')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('groupJoin.emptyState');
  });

  it('renders a chip for each applied filter, and none when no filters are applied', () => {
    const fixture = setup(1);

    expect(fixture.nativeElement.querySelector('.filter-chips')).toBeNull();

    fixture.componentInstance.filterForm.patchValue({ group_name: '夜羽球', match_mode: 'singles' });
    fixture.componentInstance.applyFilters();
    fixture.detectChanges();

    const chips = fixture.nativeElement.querySelectorAll('.filter-chips button');
    expect(chips.length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('夜羽球');
    expect(fixture.nativeElement.textContent).toContain('createGroup.matchModeSingles');
  });

  it('clicking a filter chip clears just that filter and re-applies', () => {
    const listGroups = vi.fn(() => of({ groups: [group], page: 1, total_pages: 1 }));
    const fixture = setup(1, [group], { listGroups });

    fixture.componentInstance.filterForm.patchValue({ group_name: '夜羽球', creator_nickname: '王小明' });
    fixture.componentInstance.applyFilters();
    fixture.detectChanges();

    (fixture.nativeElement.querySelector('.filter-chips button') as HTMLButtonElement).click();

    expect(fixture.componentInstance.filterForm.getRawValue().group_name).toBe('');
    expect(fixture.componentInstance.filterForm.getRawValue().creator_nickname).toBe('王小明');
    expect(listGroups).toHaveBeenLastCalledWith(
      1,
      expect.objectContaining({ group_name: undefined, creator_nickname: '王小明' }),
    );
  });

  it('"clear filters" resets every field and re-applies', () => {
    const listGroups = vi.fn(() => of({ groups: [group], page: 1, total_pages: 1 }));
    const fixture = setup(1, [group], { listGroups });

    fixture.componentInstance.filterForm.patchValue({ group_name: '夜羽球', match_mode: 'singles' });
    fixture.componentInstance.applyFilters();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.filter-chips')).not.toBeNull();

    fixture.componentInstance.clearAllFilters();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.filter-chips')).toBeNull();
    expect(listGroups).toHaveBeenLastCalledWith(
      1,
      expect.objectContaining({ group_name: undefined, match_mode: undefined }),
    );
  });

  it('capacityPercent caps at 100 and handles a zero max_members defensively', () => {
    const fixture = setup(1);
    const component = fixture.componentInstance;

    expect(component.capacityPercent({ ...group, current_member_count: 4, max_members: 8 })).toBe(50);
    expect(component.capacityPercent({ ...group, current_member_count: 10, max_members: 8 })).toBe(100);
    expect(component.capacityPercent({ ...group, current_member_count: 0, max_members: 0 })).toBe(0);
  });

  it('renders pagination controls when totalPages > 1', () => {
    const fixture = setup(3);

    expect(fixture.nativeElement.querySelector('.pagination')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.pagination button').length).toBe(5); // prev + 3 pages + next
  });

  it('does not render pagination controls when there is only one page', () => {
    const fixture = setup(1);

    expect(fixture.nativeElement.querySelector('.pagination')).toBeNull();
  });

  it('an already-joined member navigates straight to member-view, not the password-gated join flow', () => {
    const joinedGroup = { ...group, joined_by_me: true, current_member_count: 8, max_members: 8 };
    const fixture = setup(1, [joinedGroup]);
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('li button');
    button.click();

    expect(navigateSpy).toHaveBeenCalledWith(['/groups', 'g1', 'member-view']);
  });

  it('the group creator is routed to the admin page with a freshly issued admin token instead of member-view', () => {
    const ownGroup = {
      ...group,
      joined_by_me: true,
      created_by_me: true,
      current_member_count: 8,
      max_members: 8,
    };
    const getCreatorAdminToken = vi.fn(() =>
      of({ admin_token: 'fresh-admin-token', group_id: 'g1' }),
    );
    const fixture = setup(1, [ownGroup], { getCreatorAdminToken });
    const groupAdmin = TestBed.inject(GroupAdminService);
    const setAdminTokenSpy = vi.spyOn(groupAdmin, 'setAdminToken');
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');

    const button: HTMLButtonElement = fixture.nativeElement.querySelector('li button');
    button.click();

    expect(getCreatorAdminToken).toHaveBeenCalledWith('g1', {
      Authorization: 'Bearer fake-member-token',
    });
    expect(setAdminTokenSpy).toHaveBeenCalledWith('g1', 'fresh-admin-token');
    expect(navigateSpy).toHaveBeenCalledWith(['/groups', 'g1', 'admin']);
  });

  it('a Member active in another group sees a badge instead of a join button for this one', () => {
    const blockedGroup = { ...group, member_active_elsewhere: true };
    const fixture = setup(1, [blockedGroup]);

    const li = fixture.nativeElement.querySelector('li');
    expect(li.textContent).toContain('groupJoin.activeElsewhereLabel');
    expect(li.querySelector('button')).toBeNull();
  });

  it('clickJoin() is a no-op front-check for member_active_elsewhere, even if called directly', () => {
    const blockedGroup = { ...group, member_active_elsewhere: true };
    const fixture = setup(1, [blockedGroup]);
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');

    fixture.componentInstance.clickJoin(blockedGroup);

    expect(navigateSpy).not.toHaveBeenCalled();
  });

  it('a Guest active in another group (same browser) sees the same badge instead of a join button', () => {
    const otherGroup = { ...group, group_id: 'g2' };
    const fixture = setup(1, [otherGroup], { isLoggedIn: false, activeGuestGroupId: 'g1' });

    const li = fixture.nativeElement.querySelector('li');
    expect(li.textContent).toContain('groupJoin.activeElsewhereLabel');
    expect(li.querySelector('button')).toBeNull();
  });

  it('a Guest active in THIS group sees "已加入"/"返回組團" instead of a join button, and it navigates to member-view', () => {
    const fixture = setup(1, [group], { isLoggedIn: false, activeGuestGroupId: 'g1' });
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');

    const li = fixture.nativeElement.querySelector('li');
    expect(li.textContent).not.toContain('groupJoin.activeElsewhereLabel');
    expect(li.textContent).toContain('groupJoin.alreadyJoinedLabel');
    expect(li.textContent).toContain('groupJoin.returnButton');
    expect(li.textContent).not.toContain('groupJoin.joinButton');

    (li.querySelector('button') as HTMLButtonElement).click();

    expect(navigateSpy).toHaveBeenCalledWith(['/groups', 'g1', 'member-view']);
  });

  it('a Guest with no tracked active group is not blocked', () => {
    const fixture = setup(1, [group], { isLoggedIn: false, activeGuestGroupId: null });

    const li = fixture.nativeElement.querySelector('li');
    expect(li.textContent).not.toContain('groupJoin.activeElsewhereLabel');
    expect(li.querySelector('button')).not.toBeNull();
  });

  /** Regression test: disbanding a group (manually, or via the inactivity
   * auto-disband scheduler) never touches RosterEntry.status — so a marker
   * pointing at a since-disbanded group must not permanently lock a Guest
   * out of joining anywhere else. verifyActiveGuestGroupId() is
   * responsible for that liveness check; this confirms a row isn't blocked
   * (nor mistaken for the Guest's "own group") when it reports the raw
   * marker as stale. */
  it('a Guest whose tracked group has since disbanded (stale marker) is not blocked anywhere', () => {
    const otherGroup = { ...group, group_id: 'g2' };
    const fixture = setup(1, [otherGroup], {
      isLoggedIn: false,
      activeGuestGroupId: 'disbanded-group',
      verifiedActiveGuestGroupId: null,
    });

    const li = fixture.nativeElement.querySelector('li');
    expect(li.textContent).not.toContain('groupJoin.activeElsewhereLabel');
    expect(li.textContent).not.toContain('groupJoin.alreadyJoinedLabel');
    expect(li.querySelector('button')).not.toBeNull();
  });
});
