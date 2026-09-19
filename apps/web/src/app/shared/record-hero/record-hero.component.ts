import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

interface PerformanceTier {
  icon: string;
  labelKey: string;
}

/** The "athlete card" at the top of a record page (my match history, my
 * history in one group): a win-rate ring plus a scoreboard-style W–L
 * record — one focal number reads faster than four equal stat tiles. */
@Component({
  selector: 'app-record-hero',
  imports: [TranslatePipe],
  templateUrl: './record-hero.component.html',
  styleUrl: './record-hero.component.scss',
})
export class RecordHeroComponent {
  readonly wins = input.required<number>();
  readonly losses = input.required<number>();
  readonly total = input.required<number>();
  /** 0–1. */
  readonly winRate = input.required<number>();

  readonly winPercent = computed(() => Math.round(this.winRate() * 100));

  readonly ringGradient = computed(() => {
    if (this.total() === 0) {
      return 'conic-gradient(var(--color-border) 0 100%)';
    }
    const win = this.winRate() * 100;
    return `conic-gradient(var(--color-positive) 0 ${win}%, var(--color-negative) ${win}% 100%)`;
  });

  /** A light motivational framing of the win rate (no gameplay effect),
   * only once there is at least one match — a brand-new member isn't told
   * they're "蓄勢待發" off a 0-match sample. */
  readonly tier = computed<PerformanceTier | null>(() => {
    if (this.total() === 0) {
      return null;
    }
    const rate = this.winRate();
    if (rate >= 0.7) {
      return { icon: '🏆', labelKey: 'member.matchHistory.tier.elite' };
    }
    if (rate >= 0.5) {
      return { icon: '🔥', labelKey: 'member.matchHistory.tier.strong' };
    }
    if (rate >= 0.3) {
      return { icon: '📈', labelKey: 'member.matchHistory.tier.rising' };
    }
    return { icon: '💪', labelKey: 'member.matchHistory.tier.building' };
  });
}
