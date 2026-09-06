// Mirrors apps/api/app/domains/member/schemas.py — see contracts/auth-api.md, member-api.md.

export type VerificationStatus = 'unverified' | 'verified';

export interface MemberPublic {
  member_id: string;
  email: string;
  nickname: string | null;
  user_number: string;
  verification_status: VerificationStatus;
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
