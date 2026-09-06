import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupMemberViewService } from '../group-member-view.service';
import { LeaveGroupComponent } from './leave-group.component';

/** Leaving a group used to send the member to /groups/:groupId/join (the
 * join screen for the group they just left) — now goes to /groups (the
 * browse list) instead, since staying on a page scoped to a group they're
 * no longer in doesn't make sense. */
describe('LeaveGroupComponent navigates to /groups after leaving', () => {
  it('calls router.navigate with ["/groups"] once leaveGroup() succeeds', () => {
    const navigateCalls: unknown[][] = [];

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
      ],
    });

    const fixture = TestBed.createComponent(LeaveGroupComponent);
    fixture.componentRef.setInput('groupId', 'g1');
    fixture.detectChanges();

    fixture.componentInstance.confirmLeave();

    expect(navigateCalls).toEqual([[['/groups']]]);
  });
});
