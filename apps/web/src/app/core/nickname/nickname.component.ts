import { Component, computed, input } from '@angular/core';
import { DELETED_MEMBER_PLACEHOLDER_NICKNAME } from './deleted-member-nickname';

/** Renders a nickname exactly as given, except a deleted account's
 * placeholder ("Deleted User") is visually muted — a color distinguishing
 * "this person no longer exists" from a real, active nickname — wherever
 * match/roster history renders participant names. The distinguishing
 * signal is the text itself (already different from any real nickname);
 * the muted color is reinforcement, never the sole signal (constitution
 * VII — never color-alone for state). */
@Component({
  selector: 'app-nickname',
  templateUrl: './nickname.component.html',
  styleUrl: './nickname.component.scss',
})
export class NicknameComponent {
  readonly value = input.required<string | null>();

  readonly isDeleted = computed(() => this.value() === DELETED_MEMBER_PLACEHOLDER_NICKNAME);
}
