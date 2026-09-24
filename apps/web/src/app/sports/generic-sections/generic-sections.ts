import { Type } from '@angular/core';

import { SectionComponent } from '../sport-type-module';
import { MetricGridSectionComponent } from './metric-grid-section.component';
import { ScoreTimelineSectionComponent } from './score-timeline-section.component';
import { StatTableSectionComponent } from './stat-table-section.component';
import { TextNoteSectionComponent } from './text-note-section.component';

/** Section kinds any sport type may emit (mirrors
 * app/sports/presentation.py GENERIC_SECTION_KINDS). */
export const GENERIC_SECTION_COMPONENTS: Readonly<Record<string, Type<SectionComponent>>> = {
  metric_grid: MetricGridSectionComponent,
  stat_table: StatTableSectionComponent,
  score_timeline: ScoreTimelineSectionComponent,
  text_note: TextNoteSectionComponent,
};

export const GENERIC_SECTION_KINDS: readonly string[] = Object.keys(GENERIC_SECTION_COMPONENTS);
