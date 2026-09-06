import { Component, inject, input, output, signal, viewChild } from '@angular/core';
import { QRCodeComponent } from 'angularx-qrcode';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { CourtManagementService } from './court-management.service';
import { Court } from './court-management.models';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';

/** QR Code + one-click-copy for a single court's scoreboard/control-panel
 * links (spec FR-004) + regenerate-link buttons and confirmation (T040). */
@Component({
  selector: 'app-court-link-card',
  imports: [QRCodeComponent, TranslatePipe, ConfirmDialogComponent],
  templateUrl: './court-link-card.component.html',
  styleUrl: './court-link-card.component.scss',
})
export class CourtLinkCardComponent {
  readonly groupId = input.required<string>();
  readonly court = input.required<Court>();
  readonly regenerated = output<void>();

  private readonly courtService = inject(CourtManagementService);

  readonly copiedScoreboard = signal(false);
  readonly copiedControlPanel = signal(false);
  readonly errorKey = signal<string | null>(null);

  readonly scoreboardRegenDialog =
    viewChild.required<ConfirmDialogComponent>('scoreboardRegenDialog');
  readonly controlPanelRegenDialog =
    viewChild.required<ConfirmDialogComponent>('controlPanelRegenDialog');

  scoreboardUrl(): string {
    return `${window.location.origin}/scoreboard/${this.court().scoreboard_token}`;
  }

  controlPanelUrl(): string {
    return `${window.location.origin}/control/${this.court().control_panel_token}`;
  }

  async copyScoreboardLink(): Promise<void> {
    await navigator.clipboard.writeText(this.scoreboardUrl());
    this.copiedScoreboard.set(true);
    setTimeout(() => this.copiedScoreboard.set(false), 2000);
  }

  async copyControlPanelLink(): Promise<void> {
    await navigator.clipboard.writeText(this.controlPanelUrl());
    this.copiedControlPanel.set(true);
    setTimeout(() => this.copiedControlPanel.set(false), 2000);
  }

  openScoreboardRegenDialog(): void {
    this.scoreboardRegenDialog().open();
  }

  openControlPanelRegenDialog(): void {
    this.controlPanelRegenDialog().open();
  }

  confirmRegenerateScoreboardLink(): void {
    this.errorKey.set(null);
    this.courtService
      .regenerateScoreboardLink(this.groupId(), this.court().court_id, this.court().scoreboard_link_version)
      .subscribe({
        next: () => this.regenerated.emit(),
        error: (error: ApiError) => this.errorKey.set(error.i18nKey),
      });
  }

  confirmRegenerateControlPanelLink(): void {
    this.errorKey.set(null);
    this.courtService
      .regenerateControlPanelLink(
        this.groupId(),
        this.court().court_id,
        this.court().control_panel_link_version,
      )
      .subscribe({
        next: () => this.regenerated.emit(),
        error: (error: ApiError) => this.errorKey.set(error.i18nKey),
      });
  }
}
