import { DatePipe } from '@angular/common';
import { Component, computed, input, output } from '@angular/core';
import { IconComponent } from '../icon/icon.component';
import { TranslatePipe } from '@ngx-translate/core';
import { InviteCandidateStatus } from '../../core/api/friend.models';
import { MatchRecordSummary } from '../../core/api/group-member-view.models';
import { NicknameComponent } from '../../core/nickname/nickname.component';
import { AddFriendButtonComponent } from '../add-friend-button/add-friend-button.component';

/** Whose perspective the card is read from: the viewer's own result
 * (match history, a friend's records) or the group's (who won). */
export type MatchCardResult = 'win' | 'loss' | null;

/** One completed match as a scorecard row — used by every match list (my
 * match history, a friend's records, a group's records and history).
 * Rendered on the list's own `<li>` so the list keeps its semantics; the
 * whole card opens the match detail.
 *
 * - `result` set: a colored edge plus an explicit 勝/敗 badge (never color
 *   alone) for the viewer's own outcome.
 * - `result` null (a group's list): no win/loss coloring at all — the
 *   winners are named in a neutral badge, since green here would read as
 *   "you won". */
@Component({
  // An attribute selector on purpose: the card IS the list's <li>, so the
  // list keeps its semantics and the whole row is the click target.
  // eslint-disable-next-line @angular-eslint/component-selector
  selector: 'li[app-match-card]',
  imports: [DatePipe, TranslatePipe, NicknameComponent, AddFriendButtonComponent, IconComponent],
  templateUrl: './match-card.component.html',
  styleUrl: './match-card.component.scss',
  host: {
    class: 'card match-card record-row--clickable',
    '[class.match-card--win]': "result() === 'win'",
    '[class.match-card--loss]': "result() === 'loss'",
    role: 'button',
    tabindex: '0',
    '(click)': 'opened.emit()',
    '(keydown.enter)': 'opened.emit()',
    '(keydown.space)': 'opened.emit(); $event.preventDefault()',
  },
})
export class MatchCardComponent {
  readonly match = input.required<MatchRecordSummary>();
  readonly result = input<MatchCardResult>(null);
  /** Shown as the first tag when the list spans several groups. */
  readonly groupName = input<string | null>(null);
  /** Date format for the start time; a single group's list is one day. */
  readonly startFormat = input('M/d HH:mm');
  /** Add-friend eligibility per member, or null to never offer it. */
  readonly candidateFor = input<((memberId: string) => InviteCandidateStatus | undefined) | null>(
    null,
  );
  readonly opened = output<void>();

  readonly winnerNames = computed(() => {
    const match = this.match();
    const winners = match.winner_team === 'A' ? match.team_a : match.team_b;
    return winners.map((p) => p.nickname).join('、');
  });

  candidate(participant: MatchRecordSummary['team_a'][number]): InviteCandidateStatus | undefined {
    const lookup = this.candidateFor();
    return participant.member_id && lookup ? lookup(participant.member_id) : undefined;
  }
}
