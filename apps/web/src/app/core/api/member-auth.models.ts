// Mirrors apps/api/app/domains/member/schemas.py — see contracts/auth-api.md, member-api.md.

export type VerificationStatus = 'unverified' | 'verified';

export interface MemberPublic {
  member_id: string;
  email: string;
  nickname: string | null;
  user_number: string;
  verification_status: VerificationStatus;
  // 020-resend-verification-email: null means resend is available right
  // now (or the account is already verified — verification_status already
  // disambiguates that), computed server-side (constitution X) — MUST NOT
  // be re-derived client-side.
  resend_verification_available_at: string | null;
  // 022-member-personal-settings
  language_preference: string;
  allow_search: boolean;
  share_match_records_with_friends: boolean;
}

export interface SupportedLanguagesResponse {
  languages: string[];
}

export interface PrivacySettingsRequest {
  allow_search?: boolean;
  share_match_records_with_friends?: boolean;
}

export interface PrivacySettingsResponse {
  allow_search: boolean;
  share_match_records_with_friends: boolean;
}

export interface LoginRecordSummary {
  created_at: string;
  device_category: 'desktop' | 'mobile' | 'unknown';
}

export interface LoginRecordsResponse {
  records: LoginRecordSummary[];
  page: number;
  total_pages: number;
}

export interface RegisterRequest {
  email: string;
  password: string;
  confirm_password: string;
  turnstile_token: string;
}

export interface RegisterResponse {
  member_id: string;
  email: string;
  user_number: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  member: MemberPublic;
}

export interface RefreshResponse {
  access_token: string;
}

export interface VerifyEmailResponse {
  verified: boolean;
}

export interface ResendVerificationResponse {
  sent: boolean;
  // Cooldown end time for the *next* resend — present even on a first-ever
  // manual resend, which always succeeds regardless of cooldown.
  available_at: string;
}

export interface ForgotPasswordResponse {
  sent: boolean;
}

export interface ResetPasswordResponse {
  reset: boolean;
}

export interface ChangePasswordResponse {
  changed: boolean;
  access_token: string;
  refresh_token: string;
}
