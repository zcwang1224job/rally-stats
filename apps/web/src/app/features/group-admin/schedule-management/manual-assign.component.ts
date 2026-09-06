import { Component, inject, input, output, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { MatchMode } from '../group-admin.models';
import { ScheduleService } from './schedule.service';
import { RosterScheduleStatus, Team } from './schedule.models';

/** 手動安排選人介面 (US2, T034). 篩選掉目前已在其他場地進行中的成員（FR-013a，
 * 由父層傳入的 roster 已內含 currently_playing 旗標，跨場地一律有效）；
 * 已離開/被踢除者本就不會出現在 active roster 清單中（FR-013b）。 */
@Component({
  selector: 'app-manual-assign',
  imports: [TranslatePipe],
  templateUrl: './manual-assign.component.html',
  styleUrl: './manual-assign.component.scss',
})
export class ManualAssignComponent {
  readonly groupId = input.required<string>();
  readonly courtId = input.required<string>();
  readonly matchMode = input.required<MatchMode>();
  readonly roster = input.required<RosterScheduleStatus[]>();
  readonly assigned = output<void>();

  private readonly scheduleService = inject(ScheduleService);

  readonly selectedTeamA = signal<string[]>([]);
  readonly selectedTeamB = signal<string[]>([]);
  readonly errorKey = signal<string | null>(null);

  availableRoster(): RosterScheduleStatus[] {
    return this.roster().filter((entry) => !entry.currently_playing);
  }

  requiredPerTeam(): number {
    return this.matchMode() === 'singles' ? 1 : 2;
  }

  isSelected(rosterEntryId: string): Team | null {
    if (this.selectedTeamA().includes(rosterEntryId)) return 'A';
    if (this.selectedTeamB().includes(rosterEntryId)) return 'B';
    return null;
  }

  toggle(rosterEntryId: string, team: Team): void {
    const current = this.isSelected(rosterEntryId);
    if (current === team) {
      // deselect
      this.selectedTeamA.update((list) => list.filter((id) => id !== rosterEntryId));
      this.selectedTeamB.update((list) => list.filter((id) => id !== rosterEntryId));
      return;
    }
    this.selectedTeamA.update((list) => list.filter((id) => id !== rosterEntryId));
    this.selectedTeamB.update((list) => list.filter((id) => id !== rosterEntryId));
    if (team === 'A' && this.selectedTeamA().length < this.requiredPerTeam()) {
      this.selectedTeamA.update((list) => [...list, rosterEntryId]);
    } else if (team === 'B' && this.selectedTeamB().length < this.requiredPerTeam()) {
      this.selectedTeamB.update((list) => [...list, rosterEntryId]);
    }
  }

  canSubmit(): boolean {
    return (
      this.selectedTeamA().length === this.requiredPerTeam() &&
      this.selectedTeamB().length === this.requiredPerTeam()
    );
  }

  submit(): void {
    if (!this.canSubmit()) {
      return;
    }
    const teams: Record<string, Team> = {};
    for (const id of this.selectedTeamA()) teams[id] = 'A';
    for (const id of this.selectedTeamB()) teams[id] = 'B';
    const participantIds = [...this.selectedTeamA(), ...this.selectedTeamB()];

    this.errorKey.set(null);
    this.scheduleService.manualAssign(this.groupId(), this.courtId(), participantIds, teams).subscribe({
      next: () => {
        this.selectedTeamA.set([]);
        this.selectedTeamB.set([]);
        this.assigned.emit();
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }
}
