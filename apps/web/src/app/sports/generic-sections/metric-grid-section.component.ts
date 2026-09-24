import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { Section, SectionComponent, SectionContext } from '../sport-type-module';
import { MetricGridData, formatMetricValue } from './section-data';

/** Generic `metric_grid` section: one tile per metric, with the group
 * average beside it when the server sends one (FR-027). */
@Component({
  selector: 'app-metric-grid-section',
  imports: [TranslatePipe],
  template: `
    <section class="card metric-grid-section" data-section-kind="metric_grid">
      @if (section().title_key; as titleKey) {
        <h3 class="metric-grid-section__title">{{ titleKey | translate }}</h3>
      }
      <dl class="metric-grid-section__grid">
        @for (metric of data().metrics; track metric.key) {
          <div class="metric-grid-section__tile" [attr.data-metric]="metric.key">
            <dt>{{ metric.label_key | translate }}</dt>
            <dd class="metric-grid-section__value">{{ format(metric.kind, metric.value) }}</dd>
            @if (metric.numerator !== undefined && metric.numerator !== null && metric.denominator) {
              <dd class="metric-grid-section__fraction">{{ metric.numerator }} / {{ metric.denominator }}</dd>
            }
            @if (metric.group_average !== undefined && metric.group_average !== null) {
              <dd class="metric-grid-section__average">
                {{ 'sections.groupAverage' | translate }} {{ format(metric.kind, metric.group_average) }}
              </dd>
            }
          </div>
        }
      </dl>
    </section>
  `,
  styles: `
    .metric-grid-section__title { margin: 0 0 0.75rem; font-size: 1rem; }
    .metric-grid-section__grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 9rem), 1fr));
      gap: 0.75rem;
      margin: 0;
    }
    .metric-grid-section__tile { padding: 0.5rem 0.75rem; border: 1px solid var(--color-border); border-radius: 8px; }
    .metric-grid-section__tile dt { font-size: 0.85rem; color: var(--color-text-muted); }
    .metric-grid-section__tile dd { margin: 0; }
    .metric-grid-section__value { font-size: 1.5rem; font-weight: 700; }
    .metric-grid-section__fraction, .metric-grid-section__average { font-size: 0.8rem; color: var(--color-text-muted); }
  `,
})
export class MetricGridSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  readonly data = computed(() => (this.section().data as MetricGridData | null) ?? { metrics: [] });
  readonly format = formatMetricValue;
}
