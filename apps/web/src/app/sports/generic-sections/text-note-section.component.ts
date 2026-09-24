import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { Section, SectionComponent, SectionContext } from '../sport-type-module';
import { TextNoteData } from './section-data';

/** Generic `text_note` section: one translated line (e.g. "no matches yet"). */
@Component({
  selector: 'app-text-note-section',
  imports: [TranslatePipe],
  template: `
    <p class="empty-state" data-section-kind="text_note">
      {{ data().text_key | translate: data().params ?? {} }}
    </p>
  `,
})
export class TextNoteSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  readonly data = computed(
    () => (this.section().data as TextNoteData | null) ?? { text_key: 'sections.empty' },
  );
}
