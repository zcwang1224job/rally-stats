import { Component, viewChild } from '@angular/core';
import { MatchRecordDetailResponse } from '../../api/group-member-view.models';
import { ShareCardPreviewComponent } from '../../share-card/share-card-preview/share-card-preview.component';
import { ShareCardContext } from '../share-card.models';
import { buildShareCardModel } from '../share-card-model';
import { toMatchShareCardOption } from '../match-share-card-option';

/** 040-match-share-card: the preview opened from the match detail dialog.
 * Since 041 the preview itself is the shared one; this keeps 040's
 * `open(detail, context)` so the detail dialog and its four callers are
 * untouched. The match card is the only option, so there is no kind
 * switch — and no perspective switch: the entry point decides it (FR-017a). */
@Component({
  selector: 'app-share-card-dialog',
  imports: [ShareCardPreviewComponent],
  template: '<app-share-card-preview />',
})
export class ShareCardDialogComponent {
  private readonly preview = viewChild.required(ShareCardPreviewComponent);

  open(detail: MatchRecordDetailResponse, context: ShareCardContext): void {
    this.preview().open([toMatchShareCardOption(buildShareCardModel(detail, context))]);
  }

  close(): void {
    this.preview().close();
  }
}
