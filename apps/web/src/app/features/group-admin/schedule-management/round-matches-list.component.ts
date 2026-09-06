import { Component, inject, input, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { RoundMatchSummary } from './schedule.models';
import { ScheduleService } from './schedule.service';

/** 011-round-robin-scheduling: 本輪賽程清單——讓管理員能看到整份預先排好
 * 的循環賽賽程（queued/in_progress/completed/abandoned 全部列出），而不
 * 只是每個場地目前這一場。預設收合，展開時才拉取資料，避免大團（賽程可能
 * 高達數十甚至數百場）在未開啟此區塊時也持續輪詢一份大清單。 */
@Component({
  selector: 'app-round-matches-list',
  imports: [TranslatePipe],
  templateUrl: './round-matches-list.component.html',
  styleUrl: './round-matches-list.component.scss',
})
export class RoundMatchesListComponent {
  readonly groupId = input.required<string>();

  private readonly scheduleService = inject(ScheduleService);

  readonly expanded = signal(false);
  readonly loading = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly roundNumber = signal<number | null>(null);
  readonly matches = signal<RoundMatchSummary[]>([]);

  toggle(): void {
    const next = !this.expanded();
    this.expanded.set(next);
    if (next) {
      this.load();
    }
  }

  load(): void {
    this.loading.set(true);
    this.errorKey.set(null);
    this.scheduleService.getRoundMatches(this.groupId()).subscribe({
      next: (response) => {
        this.roundNumber.set(response.round_number);
        this.matches.set(response.matches);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  vsLabel(match: RoundMatchSummary): string {
    const teamA = match.participants.filter((p) => p.team === 'A').map((p) => p.nickname);
    const teamB = match.participants.filter((p) => p.team === 'B').map((p) => p.nickname);
    return `${teamA.join(' / ')} vs ${teamB.join(' / ')}`;
  }
}
