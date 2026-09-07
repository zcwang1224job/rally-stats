import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { AuthService } from '../auth/auth.service';
import { NotificationService } from './notification.service';

describe('NotificationService', () => {
  function setup(unreadCounts: number[]) {
    let call = 0;
    const apiGet = vi.fn(() => of({ unread_count: unreadCounts[Math.min(call++, unreadCounts.length - 1)] }));
    const notificationCreated$ = new Subject<unknown>();
    const reconnect$ = new Subject<void>();

    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: { get: apiGet, post: vi.fn() } },
        {
          provide: AuthService,
          useValue: {
            getCachedMemberId: () => 'member-1',
            getAccessToken: () => 'token-1',
            getMe: vi.fn(),
          },
        },
        { provide: RealtimeService, useValue: { subscribe: () => notificationCreated$ } },
        { provide: ReconnectRefetchService, useValue: { onReconnect: () => reconnect$ } },
      ],
    });

    return {
      service: TestBed.inject(NotificationService),
      notificationCreated$,
      reconnect$,
      apiGet,
    };
  }

  it('fetches the unread count once on init', () => {
    const { service, apiGet } = setup([3]);

    service.init();

    expect(service.unreadCount()).toBe(3);
    expect(apiGet).toHaveBeenCalledWith('/notifications/unread-count', expect.anything());
  });

  it('overwrites unreadCount from the server on notification.created, not an optimistic increment', () => {
    const { service, notificationCreated$ } = setup([0, 5]);
    service.init();
    expect(service.unreadCount()).toBe(0);

    notificationCreated$.next({});

    // Server said 5 — not "0 + 1" — proving this is a re-fetch/overwrite,
    // not a local optimistic increment (research.md #3).
    expect(service.unreadCount()).toBe(5);
  });

  it('reconnecting triggers the same overwrite-from-server refetch', () => {
    const { service, reconnect$ } = setup([0, 7]);
    service.init();
    expect(service.unreadCount()).toBe(0);

    reconnect$.next();

    expect(service.unreadCount()).toBe(7);
  });

  it('init() is idempotent — a second call does not re-subscribe or re-fetch', () => {
    const { service, apiGet } = setup([1]);

    service.init();
    service.init();

    expect(apiGet).toHaveBeenCalledTimes(1);
  });
});
