import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  MemberMatchRecordFilters,
  MemberMatchRecordsResponse,
} from '../../core/api/group-member-view.models';
import {
  ChangePasswordResponse,
  ForgotPasswordResponse,
  LoginRequest,
  LoginResponse,
  MemberPublic,
  RefreshResponse,
  RegisterRequest,
  RegisterResponse,
  ResendVerificationResponse,
  ResetPasswordResponse,
  VerifyEmailResponse,
} from '../../core/api/member-auth.models';

const ACCESS_TOKEN_KEY = 'rally-stats:member-access-token';
const REFRESH_TOKEN_KEY = 'rally-stats:member-refresh-token';
const MEMBER_ID_KEY = 'rally-stats:member-id';

/** Centralized API layer for the member-auth feature (006), plus member
 * token storage in localStorage (unlike group-admin's per-group
 * sessionStorage — a member session is a single global identity meant to
 * persist across tabs/restarts, matching the refresh token's 30-day TTL). */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiClient);

  private readonly loggedInState = signal(this.getAccessToken() !== null);
  /** Reactive login-state for the nav shell (009) — flips on setTokens()/logout(),
   * so templates don't need to poll isLoggedIn() to notice a change. */
  readonly loggedIn = this.loggedInState.asReadonly();

  register(payload: RegisterRequest): Observable<RegisterResponse> {
    return this.api.post<RegisterResponse>('/auth/register', payload);
  }

  login(payload: LoginRequest): Observable<LoginResponse> {
    return this.api.post<LoginResponse>('/auth/login', payload).pipe(
      tap((response) => {
        this.setTokens(response.access_token, response.refresh_token);
        this.setCachedMemberId(response.member.member_id);
      }),
    );
  }

  refresh(): Observable<RefreshResponse> {
    return this.api
      .post<RefreshResponse>('/auth/refresh', { refresh_token: this.getRefreshToken() })
      .pipe(tap((response) => this.setAccessToken(response.access_token)));
  }

  verifyEmail(token: string): Observable<VerifyEmailResponse> {
    return this.api.get<VerifyEmailResponse>(`/auth/verify-email/${token}`);
  }

  resendVerification(): Observable<ResendVerificationResponse> {
    return this.api.post<ResendVerificationResponse>(
      '/auth/resend-verification',
      {},
      this.authHeader(),
    );
  }

  getMe(): Observable<MemberPublic> {
    return this.api
      .get<MemberPublic>('/members/me', this.authHeader())
      .pipe(tap((member) => this.setCachedMemberId(member.member_id)));
  }

  forgotPassword(email: string): Observable<ForgotPasswordResponse> {
    return this.api.post<ForgotPasswordResponse>('/auth/forgot-password', { email });
  }

  resetPassword(
    token: string,
    newPassword: string,
    confirmNewPassword: string,
  ): Observable<ResetPasswordResponse> {
    return this.api.post<ResetPasswordResponse>(`/auth/reset-password/${token}`, {
      new_password: newPassword,
      confirm_new_password: confirmNewPassword,
    });
  }

  getMatchRecords(
    page = 1,
    filters: MemberMatchRecordFilters = {},
  ): Observable<MemberMatchRecordsResponse> {
    const params = new URLSearchParams({ page: String(page) });
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && value !== '') {
        params.set(key, String(value));
      }
    }
    return this.api.get<MemberMatchRecordsResponse>(
      `/members/me/match-records?${params.toString()}`,
      this.authHeader(),
    );
  }

  setNickname(nickname: string): Observable<MemberPublic> {
    return this.api.patch<MemberPublic>('/members/me/nickname', { nickname }, this.authHeader());
  }

  changePassword(
    currentPassword: string,
    newPassword: string,
    confirmNewPassword: string,
  ): Observable<ChangePasswordResponse> {
    return this.api
      .patch<ChangePasswordResponse>(
        '/members/me/password',
        {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_new_password: confirmNewPassword,
        },
        this.authHeader(),
      )
      .pipe(tap((response) => this.setTokens(response.access_token, response.refresh_token)));
  }

  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    this.loggedInState.set(true);
  }

  setAccessToken(accessToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  }

  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  clearTokens(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(MEMBER_ID_KEY);
  }

  /** Cached at login/`getMe()` time so features that only need the signed-in
   * member's own id (e.g. subscribing to their notification channel) don't
   * have to call `getMe()` on every page load just to learn it
   * (specs/012-realtime-notifications/research.md #2). */
  setCachedMemberId(memberId: string): void {
    localStorage.setItem(MEMBER_ID_KEY, memberId);
  }

  getCachedMemberId(): string | null {
    return localStorage.getItem(MEMBER_ID_KEY);
  }

  isLoggedIn(): boolean {
    return this.getAccessToken() !== null;
  }

  /** Local-only sign-out (009): clears stored tokens and flips `loggedIn` to
   * false. Does not call the API and does not navigate — callers decide
   * where to send the user afterwards. */
  logout(): void {
    this.clearTokens();
    this.loggedInState.set(false);
  }

  private authHeader(): Record<string, string> {
    const token = this.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
}
