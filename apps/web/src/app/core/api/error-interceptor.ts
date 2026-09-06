import {
  HttpErrorResponse,
  HttpEvent,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { Observable, catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../../features/auth/auth.service';
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
 * the member is logged out and the original error is surfaced. */
function handle(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService,
  alreadyRetried: boolean,
): Observable<HttpEvent<unknown>> {
  return next(req).pipe(
    catchError((response: unknown) => {
      if (!(response instanceof HttpErrorResponse)) {
        return throwError(() => response);
      }

      const apiError = toApiError(response);
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
          return handle(retried, next, authService, true);
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
  return handle(req, next, authService, false);
};
