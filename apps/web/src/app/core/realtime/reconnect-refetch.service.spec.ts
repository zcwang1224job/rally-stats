import { ApplicationRef, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import * as Ably from 'ably';
import { RealtimeService } from './ably.service';
import { ReconnectRefetchService } from './reconnect-refetch.service';

describe('ReconnectRefetchService', () => {
  let connectionState: ReturnType<typeof signal<Ably.ConnectionState>>;

  beforeEach(() => {
    connectionState = signal<Ably.ConnectionState>('connected');
    TestBed.configureTestingModule({
      providers: [{ provide: RealtimeService, useValue: { connectionState } }],
    });
  });

  function set(state: Ably.ConnectionState): void {
    connectionState.set(state);
    TestBed.inject(ApplicationRef).tick();
  }

  it('does not emit on the initial state', () => {
    const service = TestBed.runInInjectionContext(() => new ReconnectRefetchService());
    const emissions: void[] = [];
    TestBed.runInInjectionContext(() =>
      service.onReconnect().subscribe(() => emissions.push(undefined)),
    );
    TestBed.inject(ApplicationRef).tick();

    expect(emissions.length).toBe(0);
  });

  it('emits when the connection transitions from a non-connected state back to connected', () => {
    const service = TestBed.runInInjectionContext(() => new ReconnectRefetchService());
    const emissions: void[] = [];
    TestBed.runInInjectionContext(() =>
      service.onReconnect().subscribe(() => emissions.push(undefined)),
    );

    set('disconnected');
    set('connected');

    expect(emissions.length).toBe(1);
  });

  it('does not emit for transitions that never reach connected', () => {
    const service = TestBed.runInInjectionContext(() => new ReconnectRefetchService());
    const emissions: void[] = [];
    TestBed.runInInjectionContext(() =>
      service.onReconnect().subscribe(() => emissions.push(undefined)),
    );

    set('disconnected');
    set('suspended');
    set('connecting');

    expect(emissions.length).toBe(0);
  });

  it('does not emit again for repeated connected states without an intervening disconnect', () => {
    const service = TestBed.runInInjectionContext(() => new ReconnectRefetchService());
    const emissions: void[] = [];
    TestBed.runInInjectionContext(() =>
      service.onReconnect().subscribe(() => emissions.push(undefined)),
    );

    set('disconnected');
    set('connected');
    set('connected');

    expect(emissions.length).toBe(1);
  });
});
