import { Component, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { FriendshipStatus } from '../../core/api/friend.models';
import { FriendsService } from '../../features/friends/friends.service';

/** 026-match-record-friend-invite: shared "加好友" entry reused by every
 * match-record/live-status integration point (match-history,
 * group-member-view/match-records, and the roster list on both the
 * member-schedule page and the admin page's roster tab).
 *
 * The parent is responsible for batching `getInviteCandidatesStatus()` once
 * per page load/refresh and passing the resolved `friendshipStatus`/
 * `inviteEligible` in as inputs (research.md #2/#5) — this component never
 * calls that batch endpoint itself, and never renders at all for a
 * participant with no `member_id` (Guest) or the viewer's own row; that
 * exclusion is the parent template's job (FR-002/FR-003), driven by whether
 * it includes `<app-add-friend-button>` for a given row at all.
 *
 * Three render states (FR-004/FR-008):
 * - `friendshipStatus` is an existing relationship/pending request → the
 *   matching existing status label (reusing 006's i18n keys), never a
 *   button.
 * - `friendshipStatus === 'none'` and `inviteEligible` → a clickable
 *   button — text style by default (match-record rows), or a compact icon
 *   button when `iconStyle` is set (roster-list rows, matching the
 *   existing `.btn--icon` kick-member/regenerate-guest-link convention).
 * - `friendshipStatus === 'none'` and NOT `inviteEligible` (target opted
 *   out via the new privacy toggle) → renders nothing at all. */
@Component({
  selector: 'app-add-friend-button',
  imports: [TranslatePipe],
  templateUrl: './add-friend-button.component.html',
  styleUrl: './add-friend-button.component.scss',
})
export class AddFriendButtonComponent {
  private readonly friends = inject(FriendsService);

  readonly memberId = input.required<string>();
  readonly friendshipStatus = input.required<FriendshipStatus>();
  readonly inviteEligible = input.required<boolean>();
  /** Roster-list usage (admin roster tab, member-schedule roster list) —
   * a compact icon-only button instead of the default text button. */
  readonly iconStyle = input<boolean>(false);
  /** Only used to build a descriptive aria-label/title for the icon
   * variant (mirrors `kickMemberAriaLabel`/`regenerateGuestLinkAriaLabel`'s
   * existing `{{nickname}}` interpolation pattern) — the text variant
   * doesn't need it since its own visible label already says "加好友". */
  readonly nickname = input<string | null>(null);

  /** Optimistic local override once a send succeeds — takes priority over
   * the `friendshipStatus` input, which won't reflect the change until the
   * parent's next batch refresh. */
  readonly localStatus = signal<FriendshipStatus | null>(null);
  readonly sending = signal(false);
  readonly errorKey = signal<string | null>(null);

  effectiveStatus(): FriendshipStatus {
    return this.localStatus() ?? this.friendshipStatus();
  }

  /** Stops propagation itself (rather than requiring every integration
   * point's template to wrap this component in its own click-guard
   * element) since several integration points nest this button inside an
   * otherwise-clickable row (e.g. a match-record row that opens a detail
   * dialog on click) — an unguarded click would also trigger that
   * ancestor's handler. */
  send(event: Event): void {
    event.stopPropagation();
    if (this.sending()) {
      return;
    }
    this.sending.set(true);
    this.errorKey.set(null);
    this.friends.sendFriendRequestByMemberId(this.memberId()).subscribe({
      next: () => {
        this.sending.set(false);
        this.localStatus.set('pending_outgoing');
      },
      error: (error: ApiError) => {
        this.sending.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }
}
