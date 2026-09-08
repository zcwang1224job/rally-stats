import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { FriendsService } from '../../friends/friends.service';
import { MyGroupsComponent } from './my-groups.component';

const group = {
  group_id: 'g1',
  group_number: 1001,
  name: '週三團',
  status: 'active' as const,
  is_creator: true,
  member_status: 'active' as const,
};

describe('MyGroupsComponent', () => {
  it('renders each group with a forgot-PIN button', () => {
    TestBed.configureTestingModule({
      imports: [MyGroupsComponent],
      providers: [
        provideTranslateService({}),
        { provide: FriendsService, useValue: { getMyGroups: () => of({ groups: [group] }) } },
        { provide: GroupAdminService, useValue: { setAdminToken: () => undefined } },
        { provide: Router, useValue: { navigate: () => Promise.resolve(true) } },
      ],
    });
    const fixture = TestBed.createComponent(MyGroupsComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('週三團');
    expect(fixture.nativeElement.querySelector('.group-list button')).not.toBeNull();
  });

  it('renders role and member-status badges (014-member-groups-history)', () => {
    const joinedGroup = {
      group_id: 'g2',
      group_number: 1002,
      name: '別人開的團',
      status: 'active' as const,
      is_creator: false,
      member_status: 'left' as const,
    };
    TestBed.configureTestingModule({
      imports: [MyGroupsComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: FriendsService,
          useValue: { getMyGroups: () => of({ groups: [group, joinedGroup] }) },
        },
        { provide: GroupAdminService, useValue: { setAdminToken: () => undefined } },
        { provide: Router, useValue: { navigate: () => Promise.resolve(true) } },
      ],
    });
    const fixture = TestBed.createComponent(MyGroupsComponent);
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('.group-list li');
    expect(rows[0].textContent).toContain('myGroups.role.creator');
    expect(rows[0].textContent).toContain('myGroups.status.active');
    expect(rows[1].textContent).toContain('myGroups.role.member');
    expect(rows[1].textContent).toContain('myGroups.status.left');
    // Only the creator's own row gets the forgot-PIN button.
    expect(rows[0].querySelectorAll('button').length).toBe(2);
    expect(rows[1].querySelectorAll('button').length).toBe(1);
  });

  it('clicking a row navigates to that group\'s history page', () => {
    const navigateCalls: unknown[][] = [];
    TestBed.configureTestingModule({
      imports: [MyGroupsComponent],
      providers: [
        provideTranslateService({}),
        { provide: FriendsService, useValue: { getMyGroups: () => of({ groups: [group] }) } },
        { provide: GroupAdminService, useValue: { setAdminToken: () => undefined } },
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
    const fixture = TestBed.createComponent(MyGroupsComponent);
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.group-row-main').click();

    expect(navigateCalls).toEqual([[['/member/my-groups', 'g1']]]);
  });

  it('confirming forgot-PIN stores the new admin token and navigates to the admin page', () => {
    let storedToken: { groupId: string; token: string } | undefined;
    const navigateCalls: unknown[][] = [];

    TestBed.configureTestingModule({
      imports: [MyGroupsComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: FriendsService,
          useValue: {
            getMyGroups: () => of({ groups: [group] }),
            forgotAdminPin: () => of({ admin_pin: '123456', admin_token: 'new-token' }),
          },
        },
        {
          provide: GroupAdminService,
          useValue: {
            setAdminToken: (groupId: string, token: string) => {
              storedToken = { groupId, token };
            },
          },
        },
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
    const fixture = TestBed.createComponent(MyGroupsComponent);
    fixture.detectChanges();

    fixture.componentInstance.openForgotPinDialog(group);
    fixture.componentInstance.confirmForgotPin();

    expect(storedToken).toEqual({ groupId: 'g1', token: 'new-token' });
    expect(navigateCalls).toEqual([[['/groups', 'g1', 'admin']]]);
  });
});
