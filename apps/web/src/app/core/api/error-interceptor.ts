import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../../features/auth/auth.service';
import { GroupJoinService } from '../../features/group-join/group-join.service';
import { ApiError } from './api-error';

function toApiError(response: HttpErrorResponse): ApiError {
  const body = response.error as { error_code?: string; detail?: Record<string, unknown> } | null;
  const errorCode = body?.error_code ?? 'UNKNOWN_ERROR';
  return {
    errorCode,
    i18nKey: `errors.${errorCode}`,
    detail: body?.detail ?? null,
    status: response.status,
  };
}

/** Maps every backend `{"error_code": ..., "detail": ...}` response onto an
 * `errors.<error_code>` i18n key, so components never branch on raw strings
 * (constitution VIII) — they just look up `error.i18nKey` via the translate pipe.
 *
 * Also handles a member access token expiring mid-session (60min TTL, see
 * config.member_access_token_ttl_minutes): on `MEMBER_TOKEN_INVALID`, it
 * silently exchanges the refresh token for a new access token and retries
 * the request once, so the user isn't kicked out just because an hour
 * passed. If the refresh itself fails (refresh token dead/expired too),
 * the member is logged out and the original error is surfaced.
 *
 * `MEMBERSHIP_REQUIRED` gets a global redirect to /groups: it has exactly
 * one source across the whole backend (group/service.py
 * `resolve_active_roster_membership`, gating every group-member-view read
 * endpoint — schedule/standings/match-records) and means "the viewer's own
 * RosterEntry stopped being active" — left elsewhere, or kicked, mid-
 * session. Handling it here once covers all three tabs, whichever is
 * active when it happens, instead of each duplicating its own redirect.
 * Also clears the Guest active-group marker unconditionally (not just when
 * it matches this request's group) — this error already means SOME
 * RosterEntry of the caller's stopped being active, so keeping a
 * possibly-stale marker around only risks under-blocking a Guest's next
 * join attempt (the safe direction to fail in), never over-blocking one. */
function handle(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService,
  groupJoinService: GroupJoinService,
  router: Router,
  alreadyRetried: boolean,
): Observable<HttpEvent<unknown>> {
  return next(req).pipe(
    catchError((response: unknown) => {
      if (!(response instanceof HttpErrorResponse)) {
        return throwError(() => response);
      }

      const apiError = toApiError(response);
      if (apiError.errorCode === 'MEMBERSHIP_REQUIRED') {
        groupJoinService.clearActiveGuestGroupId();
        void router.navigate(['/groups']);
      }

      const canRetry =
        !alreadyRetried &&
        apiError.errorCode === 'MEMBER_TOKEN_INVALID' &&
        !req.url.endsWith('/auth/refresh') &&
        authService.getRefreshToken() !== null;

      if (!canRetry) {
        return throwError(() => apiError);
      }

      return authService.refresh().pipe(
        switchMap((refreshed) => {
          const retried = req.clone({
            setHeaders: { Authorization: `Bearer ${refreshed.access_token}` },
          });
          return handle(retried, next, authService, groupJoinService, router, true);
        }),
        catchError(() => {
          authService.logout();
          return throwError(() => apiError);
        }),
      );
    }),
  );
}

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const groupJoinService = inject(GroupJoinService);
  const router = inject(Router);
  return handle(req, next, authService, groupJoinService, router, false);
};
