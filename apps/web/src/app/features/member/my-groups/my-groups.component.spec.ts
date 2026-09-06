import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupAdminService } from '../../group-admin/group-admin.service';
import { FriendsService } from '../../friends/friends.service';
import { MyGroupsComponent } from './my-groups.component';

const group = { group_id: 'g1', group_number: 1001, name: '週三團', status: 'active' as const };

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
