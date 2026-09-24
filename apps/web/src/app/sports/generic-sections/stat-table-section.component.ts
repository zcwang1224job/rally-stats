import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { Section, SectionComponent, SectionContext } from '../sport-type-module';
import { StatTableData } from './section-data';

/** Generic `stat_table` section (e.g. the opponent breakdown). */
@Component({
  selector: 'app-stat-table-section',
  imports: [TranslatePipe],
  template: `
    <section class="card stat-table-section" data-section-kind="stat_table">
      @if (section().title_key; as titleKey) {
        <h3 class="stat-table-section__title">{{ titleKey | translate }}</h3>
      }
      @if (data().rows.length === 0) {
        <p class="empty-state">{{ 'sections.empty' | translate }}</p>
      } @else {
        <div class="stat-table-section__scroll">
          <table class="stat-table-section__table">
            <thead>
              <tr>
                @for (column of data().columns; track column.key) {
                  <th scope="col">{{ column.label_key | translate }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @for (row of data().rows; track $index) {
                <tr>
                  @for (column of data().columns; track column.key) {
                    <td>{{ row[column.key] ?? '—' }}</td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
  styles: `
    .stat-table-section__title { margin: 0 0 0.75rem; font-size: 1rem; }
    .stat-table-section__scroll { overflow-x: auto; }
    .stat-table-section__table { width: 100%; border-collapse: collapse; }
    .stat-table-section__table th, .stat-table-section__table td {
      padding: 0.4rem 0.5rem; text-align: left; border-bottom: 1px solid var(--color-border);
    }
  `,
})
export class StatTableSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  readonly data = computed(
    () => (this.section().data as StatTableData | null) ?? { columns: [], rows: [] },
  );
}
