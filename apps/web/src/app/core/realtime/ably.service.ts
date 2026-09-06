import { Injectable, signal } from '@angular/core';
import * as Ably from 'ably';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/** Centralized Ably JS SDK wrapper. The client is always token-authenticated
 * via the backend's subscribe-only `/realtime/ably-token` endpoint — this
 * frontend MUST NEVER hold a publish-capable credential (constitution X). */
@Injectable({ providedIn: 'root' })
export class RealtimeService {
  private client: Ably.Realtime | null = null;

  readonly connectionState = signal<Ably.ConnectionState>('initialized');

  private getClient(): Ably.Realtime {
    if (!this.client) {
      this.client = new Ably.Realtime({
        authUrl: `${environment.apiBaseUrl}/realtime/ably-token`,
      });
      this.client.connection.on((change) => {
        this.connectionState.set(change.current);
      });
    }
    return this.client;
  }

  /** Subscribes to a single event on a channel; unsubscribes on teardown. */
  subscribe(channelName: string, event: string): Observable<Ably.Message> {
    return new Observable<Ably.Message>((subscriber) => {
      const channel = this.getClient().channels.get(channelName);
      const listener = (message: Ably.Message) => subscriber.next(message);
      channel.subscribe(event, listener);
      return () => channel.unsubscribe(event, listener);
    });
  }
}
