import { Injectable, inject } from '@angular/core';
import { Observable, timer } from 'rxjs';
import { switchMap } from 'rxjs/operators';
import { ApiClient } from './api-client';
import { CourtByTokenResponse } from './court-link.models';
import { AllCourtsBootstrapResponse } from '../../features/control-panel/all-courts/all-courts-control-panel.models';

// FR-034: 5-minute heartbeat ceiling. Also serves as the initial bootstrap
// fetch (first tick fires immediately) — see research.md #4 in 002's plan:
// one endpoint, reused for both purposes, rather than a separate route.
const HEARTBEAT_INTERVAL_MS = 5 * 60 * 1000;

/** Court-level and all-courts-level link heartbeat/bootstrap polling (T042).
 * Per FR-034 these MUST use independent endpoints — kept as two methods
 * rather than one parameterized call to make that separation explicit. */
@Injectable({ providedIn: 'root' })
export class LinkHeartbeatService {
  private readonly api = inject(ApiClient);

  watchCourtLink(token: string): Observable<CourtByTokenResponse> {
    return timer(0, HEARTBEAT_INTERVAL_MS).pipe(
      switchMap(() => this.api.get<CourtByTokenResponse>(`/courts/by-token/${token}`)),
    );
  }

  watchAllCourtsLink(token: string): Observable<AllCourtsBootstrapResponse> {
    return timer(0, HEARTBEAT_INTERVAL_MS).pipe(
      switchMap(() =>
        this.api.get<AllCourtsBootstrapResponse>(`/groups/by-all-courts-token/${token}`),
      ),
    );
  }
}
