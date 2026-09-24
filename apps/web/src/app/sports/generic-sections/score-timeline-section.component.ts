import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { Section, SectionComponent, SectionContext } from '../sport-type-module';
import { ScoreTimelineData } from './section-data';

/** Generic `score_timeline` section: the running score, one row per
 * scoring event (only `point` events — other spine kinds never change the
 * score). */
@Component({
  selector: 'app-score-timeline-section',
  imports: [TranslatePipe],
  template: `
    <section class="card score-timeline-section" data-section-kind="score_timeline">
      <h3 class="score-timeline-section__title">
        {{ (section().title_key ?? 'sections.scoreTimeline') | translate }}
      </h3>
      @if (points().length === 0) {
        <p class="empty-state">{{ 'sections.empty' | translate }}</p>
      } @else {
        <ol class="score-timeline-section__list">
          @for (event of points(); track $index) {
            <li class="score-timeline-section__row">
              <span class="score-timeline-section__time">{{ minutes(event.elapsed_seconds) }}</span>
              <span class="status-badge" [class.status-badge--success]="event.delta > 0" [class.status-badge--danger]="event.delta < 0">
                {{ 'sections.team' | translate: { team: event.side } }}
                {{ event.delta > 0 ? '+' + event.delta : event.delta }}
              </span>
              <span class="score-timeline-section__score">{{ event.score_a }} : {{ event.score_b }}</span>
            </li>
          }
        </ol>
      }
    </section>
  `,
  styles: `
    .score-timeline-section__title { margin: 0 0 0.75rem; font-size: 1rem; }
    .score-timeline-section__list { list-style: none; margin: 0; padding: 0; }
    .score-timeline-section__row {
      display: grid; grid-template-columns: 3.5rem auto 1fr; gap: 0.5rem; align-items: center;
      padding: 0.35rem 0; border-bottom: 1px solid var(--color-border);
    }
    .score-timeline-section__time { color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
    .score-timeline-section__score { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
  `,
})
export class ScoreTimelineSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  readonly points = computed(() => {
    const data = this.section().data as ScoreTimelineData | null;
    return (data?.events ?? []).filter((event) => (event.kind ?? 'point') === 'point');
  });

  minutes(seconds: number): string {
    const whole = Math.max(0, Math.floor(seconds));
    const m = Math.floor(whole / 60);
    const s = whole % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }
}
