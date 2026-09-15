import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { ApiClient } from '../../core/api/api-client';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordFilters,
  MemberMatchRecordsResponse,
} from '../../core/api/group-member-view.models';
import {
  AddEmailResponse,
  ChangePasswordResponse,
  DeleteAccountResponse,
  ForgotPasswordResponse,
  LoginRecordsResponse,
  LoginRequest,
  LoginResponse,
  MemberPublic,
  OAuthStartResponse,
  PrivacySettingsRequest,
  PrivacySettingsResponse,
  RefreshResponse,
  RegisterRequest,
  RegisterResponse,
  ResendVerificationResponse,
  ResetPasswordResponse,
  SupportedLanguagesResponse,
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

  /** 027-google-line-oauth-login contracts/oauth-login-api.md
   * `GET /auth/oauth/{provider}/start`. `intent=login` (US1/US2) needs no
   * auth header; `intent=link` (US3, from Settings) does — the backend
   * rejects an unauthenticated `link` attempt with 401.
   *
   * `bindGuestToken` (028-guest-stats-binding research.md #3): only valid
   * with `intent=login` — carries a guest's `guest_session_token` through
   * the OAuth redirect round-trip so the backend can bind it once login/
   * registration succeeds. */
  startOAuthFlow(
    provider: 'google' | 'line',
    intent: 'login' | 'link' = 'login',
    bindGuestToken?: string,
  ): Observable<OAuthStartResponse> {
    const params = new URLSearchParams({ intent });
    if (bindGuestToken) {
      params.set('bind_guest_token', bindGuestToken);
    }
    return this.api.get<OAuthStartResponse>(
      `/auth/oauth/${provider}/start?${params.toString()}`,
      intent === 'link' ? this.authHeader() : {},
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

  /** 016-match-score-timeline (US1/US2/US3): shared by the cross-group
   * match-history list and the "我的團→歷史" list — both are a logged-in
   * Member viewing a match they have "ever a member" access to (not
   * requiring current/active membership), matching `verify_ever_group_
   * member()` on the backend (research.md #1/#4). Deliberately NOT
   * `GroupMemberViewService.getMatchRecordDetail()`, which requires
   * active membership and serves only the 團內對戰紀錄 tab. */
  getMatchRecordDetail(matchId: string): Observable<MatchRecordDetailResponse> {
    return this.api.get<MatchRecordDetailResponse>(
      `/members/me/match-records/${matchId}`,
      this.authHeader(),
    );
  }

  setNickname(nickname: string): Observable<MemberPublic> {
    return this.api.patch<MemberPublic>('/members/me/nickname', { nickname }, this.authHeader());
  }

  /** 027-google-line-oauth-login research.md #7: `currentPassword` is
   * optional — omit it (or pass `null`) for a member who has never set a
   * password yet (`MemberPublic.has_password === false`); the backend
   * treats that call as "set my first password" rather than "change it". */
  changePassword(
    currentPassword: string | null,
    newPassword: string,
    confirmNewPassword: string,
  ): Observable<ChangePasswordResponse> {
    return this.api
      .patch<ChangePasswordResponse>(
        '/members/me/password',
        {
          current_password: currentPassword ?? undefined,
          new_password: newPassword,
          confirm_new_password: confirmNewPassword,
        },
        this.authHeader(),
      )
      .pipe(tap((response) => this.setTokens(response.access_token, response.refresh_token)));
  }

  deleteAccount(currentPassword: string | null): Observable<DeleteAccountResponse> {
    return this.api.post<DeleteAccountResponse>(
      '/members/me/delete',
      { current_password: currentPassword ?? undefined },
      this.authHeader(),
    );
  }

  getSupportedLanguages(): Observable<SupportedLanguagesResponse> {
    return this.api.get<SupportedLanguagesResponse>(
      '/members/me/supported-languages',
      this.authHeader(),
    );
  }

  setLanguagePreference(language: string): Observable<MemberPublic> {
    return this.api.patch<MemberPublic>(
      '/members/me/language',
      { language },
      this.authHeader(),
    );
  }

  setPrivacySettings(payload: PrivacySettingsRequest): Observable<PrivacySettingsResponse> {
    return this.api.patch<PrivacySettingsResponse>(
      '/members/me/privacy',
      payload,
      this.authHeader(),
    );
  }

  getLoginRecords(page = 1): Observable<LoginRecordsResponse> {
    return this.api.get<LoginRecordsResponse>(
      `/members/me/login-records?page=${page}`,
      this.authHeader(),
    );
  }

  /** 023-view-friend-match-records: identical shape to `getMatchRecords()`
   * above, just targeting a friend's `member_id` instead of `me` — the
   * backend endpoint (022) already enforces friendship + the target's
   * privacy setting on every call, so this deliberately does NOT cache or
   * pre-check eligibility client-side (spec.md FR-008). Advanced filters
   * are intentionally not exposed here (research.md #1). */
  getFriendMatchRecords(memberId: string, page = 1): Observable<MemberMatchRecordsResponse> {
    return this.api.get<MemberMatchRecordsResponse>(
      `/members/${memberId}/match-records?page=${page}`,
      this.authHeader(),
    );
  }

  getFriendMatchRecordDetail(
    memberId: string,
    matchId: string,
  ): Observable<MatchRecordDetailResponse> {
    return this.api.get<MatchRecordDetailResponse>(
      `/members/${memberId}/match-records/${matchId}`,
      this.authHeader(),
    );
  }

  /** 027-google-line-oauth-login contracts/account-recovery-api.md
   * `DELETE /members/me/oauth-identities/{provider}` (US3). */
  unlinkOauthIdentity(provider: 'google' | 'line'): Observable<void> {
    return this.api.delete<void>(`/members/me/oauth-identities/${provider}`, this.authHeader());
  }

  /** 027-google-line-oauth-login contracts/account-recovery-api.md
   * `POST /members/me/email` (FR-013) — only valid while the member's
   * `email` is still `null`; the backend is the source of truth for that
   * guard (`EMAIL_ALREADY_SET` otherwise). */
  addEmail(email: string): Observable<AddEmailResponse> {
    return this.api.post<AddEmailResponse>('/members/me/email', { email }, this.authHeader());
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
