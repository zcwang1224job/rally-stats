import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { LoginRecordSummary, MemberPublic } from '../../../core/api/member-auth.models';
import { AuthService } from '../../auth/auth.service';
import {
  passwordStrengthValidator,
  passwordsMatchValidator,
} from '../../auth/auth-form-validators';
import { LanguageService } from '../../../core/language/language.service';

type SettingsSection = 'basic' | 'accountDetails' | 'security' | 'privacy';

/** FR-012/019 (006): the "首次登入設定暱稱" redirect lands here whenever
 * GET /members/me returns nickname === null (see member.component.ts, and
 * 004's join-flow — a member joining without a nickname yet is sent here
 * with `?returnTo=` so a successful save sends them straight back to
 * finish joining instead of the generic member home). */
/** 022-member-personal-settings FR-024: reorganized into four independently
 * switchable sections (基本設定/帳號詳細資訊/安全性/隱私設定) — switching
 * `activeSection` only toggles which `@if` block renders; every section's
 * own form state lives in this class's signals/FormGroups, so it survives
 * a switch away and back (FR-026, no cross-section state loss). */
@Component({
  selector: 'app-member-settings',
  imports: [ReactiveFormsModule, TranslatePipe, DatePipe],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly languageService = inject(LanguageService);

  readonly activeSection = signal<SettingsSection>('basic');

  readonly member = signal<MemberPublic | null>(null);

  // --- 基本設定：暱稱（既有，行為不變） ---
  readonly nicknameSubmitting = signal(false);
  readonly nicknameErrorKey = signal<string | null>(null);
  readonly nicknameSaved = signal(false);

  readonly nicknameForm = this.fb.nonNullable.group({
    nickname: ['', [Validators.required, Validators.maxLength(20)]],
  });

  // --- 基本設定：語言偏好（022-member-personal-settings FR-004/005） ---
  readonly languages = signal<string[]>([]);
  readonly languageSubmitting = signal(false);
  readonly languageErrorKey = signal<string | null>(null);
  readonly languageSaved = signal(false);

  readonly languageForm = this.fb.nonNullable.group({
    language: ['zh-TW', Validators.required],
  });

  // --- 帳號詳細資訊：登入紀錄（022-member-personal-settings FR-006~010） ---
  readonly loginRecords = signal<LoginRecordSummary[]>([]);
  readonly loginRecordsPage = signal(1);
  readonly loginRecordsTotalPages = signal(1);
  readonly loginRecordsLoading = signal(false);
  readonly loginRecordsErrorKey = signal<string | null>(null);

  // --- 安全性：密碼（既有，行為不變） ---
  readonly passwordSubmitting = signal(false);
  readonly passwordErrorKey = signal<string | null>(null);
  readonly passwordSaved = signal(false);

  readonly passwordForm = this.fb.nonNullable.group(
    {
      current_password: ['', Validators.required],
      new_password: ['', [Validators.required, passwordStrengthValidator]],
      confirm_new_password: ['', Validators.required],
    },
    { validators: [passwordsMatchValidator('new_password', 'confirm_new_password')] },
  );

  // --- 安全性：刪除帳號（025-delete-account FR-001/FR-002） ---
  readonly deleteAccountSubmitting = signal(false);
  readonly deleteAccountErrorKey = signal<string | null>(null);

  readonly deleteAccountForm = this.fb.nonNullable.group({
    current_password: ['', Validators.required],
  });

  // --- 隱私設定（022-member-personal-settings FR-016~023） ---
  // 使用者要求：checkbox 只是暫存草稿，切換不會立即送出；MUST 按下「儲存」
  // 才呼叫 PATCH /members/me/privacy——與其他三個分區「填寫後按按鈕送出」
  // 的既有互動模式一致。
  readonly privacySubmitting = signal(false);
  readonly privacyErrorKey = signal<string | null>(null);
  readonly privacySaved = signal(false);

  readonly privacyForm = this.fb.nonNullable.group({
    allow_search: [true],
    share_match_records_with_friends: [true],
    // 026-match-record-friend-invite FR-006: independent of the other two.
    allow_friend_invite_from_match_pages: [true],
  });

  ngOnInit(): void {
    this.auth.getMe().subscribe({
      next: (member) => {
        this.member.set(member);
        this.nicknameForm.patchValue({ nickname: member.nickname ?? '' });
        this.languageForm.patchValue({ language: member.language_preference });
        this.privacyForm.patchValue({
          allow_search: member.allow_search,
          share_match_records_with_friends: member.share_match_records_with_friends,
          allow_friend_invite_from_match_pages: member.allow_friend_invite_from_match_pages,
        });
      },
    });
    this.auth.getSupportedLanguages().subscribe({
      next: (response) => this.languages.set(response.languages),
    });
    this.loadLoginRecords(1);
  }

  setActiveSection(section: SettingsSection): void {
    this.activeSection.set(section);
  }

  submitNickname(): void {
    if (this.nicknameForm.invalid) {
      this.nicknameForm.markAllAsTouched();
      return;
    }
    this.nicknameSubmitting.set(true);
    this.nicknameErrorKey.set(null);
    this.auth.setNickname(this.nicknameForm.getRawValue().nickname).subscribe({
      next: () => {
        this.nicknameSubmitting.set(false);
        this.nicknameSaved.set(true);
        const returnTo = this.route.snapshot.queryParamMap.get('returnTo');
        void this.router.navigateByUrl(returnTo ?? '/member');
      },
      error: (error: ApiError) => {
        this.nicknameSubmitting.set(false);
        this.nicknameErrorKey.set(error.i18nKey);
      },
    });
  }

  submitLanguage(): void {
    if (this.languageForm.invalid) {
      return;
    }
    this.languageSubmitting.set(true);
    this.languageErrorKey.set(null);
    this.auth.setLanguagePreference(this.languageForm.getRawValue().language).subscribe({
      next: (member) => {
        this.languageSubmitting.set(false);
        this.languageSaved.set(true);
        this.member.set(member);
        // FR-003c: converge with the global switcher — apply the new
        // language immediately instead of only persisting it server-side.
        this.languageService.applyLanguage(member.language_preference);
      },
      error: (error: ApiError) => {
        this.languageSubmitting.set(false);
        this.languageErrorKey.set(error.i18nKey);
      },
    });
  }

  submitPassword(): void {
    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    const raw = this.passwordForm.getRawValue();
    this.passwordSubmitting.set(true);
    this.passwordErrorKey.set(null);
    this.auth
      .changePassword(raw.current_password, raw.new_password, raw.confirm_new_password)
      .subscribe({
        next: () => {
          this.passwordSubmitting.set(false);
          this.passwordSaved.set(true);
          this.passwordForm.reset();
        },
        error: (error: ApiError) => {
          this.passwordSubmitting.set(false);
          this.passwordErrorKey.set(error.i18nKey);
        },
      });
  }

  submitDeleteAccount(): void {
    if (this.deleteAccountForm.invalid) {
      this.deleteAccountForm.markAllAsTouched();
      return;
    }
    this.deleteAccountSubmitting.set(true);
    this.deleteAccountErrorKey.set(null);
    this.auth.deleteAccount(this.deleteAccountForm.getRawValue().current_password).subscribe({
      next: () => {
        this.deleteAccountSubmitting.set(false);
        // Deletion already invalidated every token server-side (token_version
        // bump) — logout() here just clears the now-stale local copy.
        this.auth.logout();
        void this.router.navigateByUrl('/');
      },
      error: (error: ApiError) => {
        this.deleteAccountSubmitting.set(false);
        this.deleteAccountErrorKey.set(error.i18nKey);
      },
    });
  }

  loadLoginRecords(page: number): void {
    this.loginRecordsLoading.set(true);
    this.loginRecordsErrorKey.set(null);
    this.auth.getLoginRecords(page).subscribe({
      next: (response) => {
        this.loginRecordsLoading.set(false);
        this.loginRecords.set(response.records);
        this.loginRecordsPage.set(response.page);
        this.loginRecordsTotalPages.set(response.total_pages);
      },
      error: (error: ApiError) => {
        this.loginRecordsLoading.set(false);
        this.loginRecordsErrorKey.set(error.i18nKey);
      },
    });
  }

  submitPrivacy(): void {
    const raw = this.privacyForm.getRawValue();
    this.privacyErrorKey.set(null);
    this.privacySubmitting.set(true);
    this.auth
      .setPrivacySettings({
        allow_search: raw.allow_search,
        share_match_records_with_friends: raw.share_match_records_with_friends,
        allow_friend_invite_from_match_pages: raw.allow_friend_invite_from_match_pages,
      })
      .subscribe({
        next: (response) => {
          this.privacySubmitting.set(false);
          const current = this.member();
          if (current) {
            this.member.set({
              ...current,
              allow_search: response.allow_search,
              share_match_records_with_friends: response.share_match_records_with_friends,
              allow_friend_invite_from_match_pages: response.allow_friend_invite_from_match_pages,
            });
          }
          this.privacySaved.set(true);
        },
        error: (error: ApiError) => {
          this.privacySubmitting.set(false);
          this.privacyErrorKey.set(error.i18nKey);
        },
      });
  }
}
