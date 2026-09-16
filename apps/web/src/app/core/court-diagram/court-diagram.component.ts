import { Component, input } from '@angular/core';

/** 032-match-record-scoring-stats (research.md Decision 5): the purely
 * visual badminton-court box — regulation-proportion lines, the
 * singles-only out-of-play shading, and an optional landing marker —
 * extracted out of `ShotPlacementPickerComponent`'s `.court` so both the
 * interactive picker (wraps this in its own pointer-handling `.court-area`)
 * and this feature's read-only landing display can share one drawing
 * without duplicating the CSS. Purely presentational: no pointer events of
 * its own, no internal state. */
@Component({
  selector: 'app-court-diagram',
  imports: [],
  templateUrl: './court-diagram.component.html',
  styleUrl: './court-diagram.component.scss',
})
export class CourtDiagramComponent {
  readonly isSinglesMatch = input.required<boolean>();
  readonly landingX = input<number | null>(null);
  readonly landingY = input<number | null>(null);
}
