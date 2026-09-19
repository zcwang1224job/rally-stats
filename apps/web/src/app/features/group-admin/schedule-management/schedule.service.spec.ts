import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client';
import { GroupAdminService } from '../group-admin.service';
import { ScheduleService } from './schedule.service';

// 037-rest-ready-toggle US4: the admin's rest/ready request.
describe('ScheduleService.setMemberRestState', () => {
  it('sends the target state with the admin token', () => {
    const calls: { path: string; body: unknown; headers?: Record<string, string> }[] = [];
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ApiClient,
          useValue: {
            put: (path: string, body: unknown, headers?: Record<string, string>) => {
              calls.push({ path, body, headers });
              return of({});
            },
          },
        },
        { provide: GroupAdminService, useValue: { getAdminToken: () => 'admin-tok' } },
      ],
    });
    const service = TestBed.inject(ScheduleService);

    service.setMemberRestState('g1', 'r1', true).subscribe();
    service.setMemberRestState('g1', 'r1', true, true).subscribe();

    expect(calls).toEqual([
      {
        path: '/groups/g1/members/r1/rest-state',
        body: { resting: true, confirm_round_end: false },
        headers: { Authorization: 'Bearer admin-tok' },
      },
      {
        path: '/groups/g1/members/r1/rest-state',
        body: { resting: true, confirm_round_end: true },
        headers: { Authorization: 'Bearer admin-tok' },
      },
    ]);
  });
});
