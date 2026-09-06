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
        useValue: { getAccessToken: () => 'fake-member-token' },
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
});
