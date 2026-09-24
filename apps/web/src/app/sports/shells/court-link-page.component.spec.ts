import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { EMPTY, of } from 'rxjs';

import { CourtControlService } from '../../core/api/court-control.service';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { CourtLinkPageComponent } from './court-link-page.component';

const INFO = {
  court_id: 'c1',
  group_id: 'g1',
  name: '球桌一',
  link_type: 'control_panel',
  link_version: 1,
  deleted: false,
  group_disbanded: false,
};

describe('CourtLinkPageComponent (043)', () => {
  it('reads the state again once the realtime channel is attached', async () => {
    const getState = vi.fn(() =>
      of({ ...INFO, round_number: 1, current_match: null, waiting_reason: null, next_up: null, scoreboard_scoring_enabled: false }),
    );
    let attached!: () => void;
    const whenAttached = vi.fn(() => new Promise<void>((resolve) => (attached = resolve)));
    TestBed.configureTestingModule({
      providers: [
        provideTranslateService({}),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } } },
        { provide: LinkHeartbeatService, useValue: { watchCourtLink: () => of(INFO) } },
        { provide: CourtControlService, useValue: { getState } },
        { provide: RealtimeService, useValue: { connectionState: signal('connected'), subscribe: () => EMPTY, whenAttached } },
        { provide: ReconnectRefetchService, useValue: { onReconnect: () => EMPTY } },
      ],
    });
    const fixture = TestBed.createComponent(CourtLinkPageComponent);
    fixture.detectChanges();
    expect(whenAttached).toHaveBeenCalledWith('court:g1:c1');
    expect(getState).toHaveBeenCalledTimes(1);

    attached();
    await Promise.resolve();
    await Promise.resolve();
    expect(getState).toHaveBeenCalledTimes(2);
  });
});
