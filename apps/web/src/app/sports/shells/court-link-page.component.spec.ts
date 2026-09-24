import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { EMPTY, Subject, of } from 'rxjs';

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

  it('reads the state again shortly after the last realtime push', () => {
    vi.useFakeTimers();
    try {
      const match = { match_id: 'm1', participants: [], score_a: 0, score_b: 0 };
      const getState = vi.fn(() =>
        of({ ...INFO, round_number: 1, current_match: match, waiting_reason: null, next_up: null, scoreboard_scoring_enabled: false }),
      );
      const pushes = new Subject<{ data: unknown }>();
      TestBed.configureTestingModule({
        providers: [
          provideTranslateService({}),
          { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } } },
          { provide: LinkHeartbeatService, useValue: { watchCourtLink: () => of(INFO) } },
          { provide: CourtControlService, useValue: { getState } },
          {
            provide: RealtimeService,
            useValue: {
              connectionState: signal('connected'),
              subscribe: (_channel: string, event: string) => (event === 'match.eventApplied' ? pushes : EMPTY),
              whenAttached: () => new Promise<void>(() => undefined),
            },
          },
          { provide: ReconnectRefetchService, useValue: { onReconnect: () => EMPTY } },
        ],
      });
      const fixture = TestBed.createComponent(CourtLinkPageComponent);
      fixture.detectChanges();
      expect(getState).toHaveBeenCalledTimes(1);
      pushes.next({ data: { match_id: 'm1', score_a: 2, score_b: 0 } });
      pushes.next({ data: { match_id: 'm1', score_a: 1, score_b: 0 } }); // arrived late
      expect(fixture.componentInstance.state()?.current_match?.score_a).toBe(1);
      vi.advanceTimersByTime(CourtLinkPageComponent.SETTLE_MS);
      expect(getState).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

