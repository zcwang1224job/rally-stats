import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupJoinService } from '../../group-join/group-join.service';
import { GroupMemberViewService } from '../group-member-view.service';
import { LeaveGroupComponent } from './leave-group.component';

function setup(options: { activeGuestGroupId?: string | null } = {}) {
  const navigateCalls: unknown[][] = [];
  let clearedActiveGuestGroupId = false;

  TestBed.configureTestingModule({
    imports: [LeaveGroupComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: Router,
        useValue: {
          navigate: (...args: unknown[]) => {
            navigateCalls.push(args);
            return Promise.resolve(true);
          },
        },
      },
      {
        provide: GroupMemberViewService,
        useValue: {
          resolveRosterEntryId: () => of('r1'),
          leaveGroup: () => of({ roster_entry_id: 'r1', status: 'left' }),
        },
      },
      {
        provide: GroupJoinService,
        useValue: {
          getActiveGuestGroupId: () => options.activeGuestGroupId ?? null,
          clearActiveGuestGroupId: () => {
            clearedActiveGuestGroupId = true;
          },
        },
      },
    ],
  });

  const fixture = TestBed.createComponent(LeaveGroupComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.detectChanges();

  return { fixture, navigateCalls, wasActiveGuestGroupIdCleared: () => clearedActiveGuestGroupId };
}

/** Leaving a group used to send the member to /groups/:groupId/join (the
 * join screen for the group they just left) — now goes to /groups (the
 * browse list) instead, since staying on a page scoped to a group they're
 * no longer in doesn't make sense. */
describe('LeaveGroupComponent navigates to /groups after leaving', () => {
  it('calls router.navigate with ["/groups"] once leaveGroup() succeeds', () => {
    const { fixture, navigateCalls } = setup();

    fixture.componentInstance.confirmLeave();

    expect(navigateCalls).toEqual([[['/groups']]]);
  });
});

/** A Guest's "which group am I active in" localStorage marker (US: same-
 * browser one-active-group nicety for Guests) must not outlive the group
 * it points to, or the list/join-flow guards would keep blocking a Guest
 * who has actually already left. */
describe('LeaveGroupComponent clears the Guest active-group marker on leaving', () => {
  it('clears it when it matches the group just left', () => {
    const { fixture, wasActiveGuestGroupIdCleared } = setup({ activeGuestGroupId: 'g1' });

    fixture.componentInstance.confirmLeave();

    expect(wasActiveGuestGroupIdCleared()).toBe(true);
  });

  it('leaves it alone when it points to a different group (e.g. a Member with nothing tracked)', () => {
    const { fixture, wasActiveGuestGroupIdCleared } = setup({ activeGuestGroupId: 'some-other-group' });

    fixture.componentInstance.confirmLeave();

    expect(wasActiveGuestGroupIdCleared()).toBe(false);
  });
});
