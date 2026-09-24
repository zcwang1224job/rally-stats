import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { Section, SectionComponent, SectionContext } from '../sport-type-module';

/** FR-021 / SC-008: a section kind this client doesn't know. Never blank,
 * never an error — say it needs a newer version and show whatever flat
 * values the data carries. */
@Component({
  selector: 'app-fallback-section',
  imports: [TranslatePipe],
  template: `
    <section class="card fallback-section" data-section-kind="fallback" [attr.data-unknown-kind]="section().kind">
      @if (section().title_key; as titleKey) {
        <h3 class="fallback-section__title">{{ titleKey | translate }}</h3>
      }
      <p class="empty-state">{{ 'sections.unsupported' | translate }}</p>
      @if (entries().length > 0) {
        <dl class="fallback-section__entries">
          @for (entry of entries(); track entry[0]) {
            <div><dt>{{ entry[0] }}</dt><dd>{{ entry[1] }}</dd></div>
          }
        </dl>
      }
    </section>
  `,
  styles: `
    .fallback-section__title { margin: 0 0 0.5rem; font-size: 1rem; }
    .fallback-section__entries { margin: 0; display: grid; gap: 0.25rem; }
    .fallback-section__entries div { display: flex; gap: 0.5rem; }
    .fallback-section__entries dt { color: var(--color-text-muted); }
    .fallback-section__entries dd { margin: 0; }
  `,
})
export class FallbackSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  /** Top-level scalar fields only; nested structures are not guessed at. */
  readonly entries = computed<[string, string][]>(() => {
    const data = this.section().data;
    if (data === null || typeof data !== 'object' || Array.isArray(data)) {
      return [];
    }
    return Object.entries(data as Record<string, unknown>)
      .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value))
      .map(([key, value]) => [key, String(value)]);
  });
}
