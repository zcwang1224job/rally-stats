import { AfterViewInit, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiClient } from '../../../core/api/api-client';
import { ApiError } from '../../../core/api/api-error';
import { GroupPublic } from '../../group-admin/group-admin.models';
import { JoinGroupResponse } from '../../../core/api/group-join.models';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../group-join.service';

type Step = 'loading' | 'password' | 'nickname' | 'confirm' | 'done' | 'restored' | 'error';

/** Password verification (if the group has one) -> Guest nickname entry
 * (or, for a logged-in member with a nickname already set, straight to a
 * one-click confirm step, FR-018) -> submit. Entered either directly (from
 * the list, US1) or via the link-preview redirect (US2).
 *
 * US4 (FR-023): before showing any step, check for an existing Guest
 * Session Token for this group and try to restore it — an invalid/stale
 * token (group disbanded, kicked, left) is cleared and treated as a fresh
 * join, never surfaced as an error.
 *
 * US6 (FR-019): a logged-in member with no nickname yet is redirected to
 * 006's settings page to complete first-login setup, then sent straight
 * back here via `returnTo` to finish joining. */
@Component({
  selector: 'app-join-flow',
  imports: [ReactiveFormsModule, TranslatePipe],
  templateUrl: './join-flow.component.html',
  styleUrl: './join-flow.component.scss',
})
export class JoinFlowComponent implements AfterViewInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly joinService = inject(GroupJoinService);

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  readonly groupId = this.route.snapshot.paramMap.get('groupId')!;
  readonly step = signal<Step>('loading');
  readonly errorKey = signal<string | null>(null);
  readonly passwordErrorKey = signal<string | null>(null);
  readonly result = signal<JoinGroupResponse | null>(null);
  readonly restoredNickname = signal<string | null>(null);
  private verifiedPassword: string | null = null;
  private isMember = false;

  readonly passwordForm = this.fb.nonNullable.group({
    password: ['', Validators.required],
  });

  readonly nicknameForm = this.fb.nonNullable.group({
    nickname: ['', [Validators.required, Validators.maxLength(20)]],
  });

  constructor() {
    if (this.auth.isLoggedIn()) {
      this.isMember = true;
      this.auth.getMe().subscribe({
        next: (member) => {
          if (member.nickname === null) {
            void this.router.navigate(['/member/settings'], {
              queryParams: { returnTo: `/groups/${this.groupId}/join` },
            });
            return;
          }
          this.loadGroupInfo();
        },
        error: () => this.loadGroupInfo(),
      });
      return;
    }

    const existingToken = this.joinService.getGuestSessionToken(this.groupId);
    if (existingToken) {
      this.joinService.resolveGuestSession(existingToken).subscribe({
        next: (session) => {
          this.restoredNickname.set(session.nickname);
          this.step.set('restored');
        },
        error: () => {
          this.joinService.clearGuestSessionToken(this.groupId);
          this.loadGroupInfo();
        },
      });
      return;
    }
    this.loadGroupInfo();
  }

  /** US5 (010-app-wide-ui-redesign, research.md Decision 4): every step
   * renders inside a centered `<dialog>` instead of replacing the whole
   * page — opened once, immediately, and never explicitly closed (there's
   * no "cancel" out of this flow; `step()` switching its content is the
   * only thing that changes for the lifetime of this page). */
  ngAfterViewInit(): void {
    // jsdom (unit tests) doesn't implement the <dialog> API at all — guard
    // rather than skip the call outright in real browsers.
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    }
  }

  private loadGroupInfo(): void {
    const token = this.auth.getAccessToken();
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
    this.api.get<GroupPublic>(`/groups/${this.groupId}`, headers).subscribe({
      next: (group) => {
        // 已是這個團的成員時，不管有沒有設密碼都直接進去——不需要再輸入
        // 一次通關密碼（後端 join_group() 的 FR-020a 短路同樣認得這種
        // 情況，這裡只是讓 UI 也提前跳過，不多問一次密碼）。
        if (this.isMember && group.already_joined === true) {
          this.confirmMemberJoin();
        } else if (group.has_password) {
          this.step.set('password');
        } else if (this.isMember) {
          this.step.set('confirm');
        } else {
          this.step.set('nickname');
        }
      },
      error: (error: ApiError) => {
        this.step.set('error');
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  submitPassword(): void {
    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    const password = this.passwordForm.getRawValue().password;
    this.passwordErrorKey.set(null);
    this.joinService.verifyPassword(this.groupId, password).subscribe({
      next: (response) => {
        if (response.correct) {
          this.verifiedPassword = password;
          this.step.set(this.isMember ? 'confirm' : 'nickname');
        } else {
          this.passwordErrorKey.set('errors.GROUP_PASSWORD_INCORRECT');
        }
      },
      error: (error: ApiError) => this.passwordErrorKey.set(error.i18nKey),
    });
  }

  submitNickname(): void {
    if (this.nicknameForm.invalid) {
      this.nicknameForm.markAllAsTouched();
      return;
    }
    this.submitJoin(this.nicknameForm.getRawValue().nickname);
  }

  confirmMemberJoin(): void {
    this.submitJoin(null);
  }

  goToGroup(): void {
    void this.router.navigate(['/groups', this.groupId, 'member-view']);
  }

  private submitJoin(nickname: string | null): void {
    this.errorKey.set(null);
    this.joinService
      .join(this.groupId, { password: this.verifiedPassword, nickname })
      .subscribe({
        next: (response) => {
          this.result.set(response);
          this.step.set('done');
        },
        error: (error: ApiError) => {
          this.errorKey.set(error.i18nKey);
        },
      });
  }
}
