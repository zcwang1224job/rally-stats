import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';
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
          listGroups: () => of({ groups, page: 1, total_pages: totalPages }),
          getActiveGuestGroupId: () => options.activeGuestGroupId ?? null,
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
  it('shows match mode and activity time on each card', () => {
    const fixture = setup(1);

    const text = fixture.nativeElement.textContent;
    expect(text).toContain('createGroup.matchModeDoubles');
    expect(text).toContain('19:00');
    expect(text).toContain('21:00');
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
});
