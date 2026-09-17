import { Component, input } from '@angular/core';

/** 032-match-record-scoring-stats (research.md Decision 5): the purely
 * visual badminton-court box — regulation-proportion lines, the
 * singles-only out-of-play shading, and an optional landing marker —
 * extracted out of `ShotPlacementPickerComponent`'s `.court` so both the
 * interactive picker (wraps this in its own pointer-handling `.court-area`)
 * and this feature's read-only landing display can share one drawing
 * without duplicating the CSS. Purely presentational: no pointer events of
 * its own, no internal state. */
/** 033-match-record-derived-stats: one point of a player's landing
 * distribution, in the same coordinate system as `landingX`/`landingY`. */
export interface CourtMarker {
  x: number;
  y: number;
  kind: 'scored' | 'lost';
}

@Component({
  selector: 'app-court-diagram',
  imports: [],
  templateUrl: './court-diagram.component.html',
  styleUrl: './court-diagram.component.scss',
  host: { '[class.court--dense]': 'dense()' },
})
export class CourtDiagramComponent {
  readonly isSinglesMatch = input.required<boolean>();
  readonly landingX = input<number | null>(null);
  readonly landingY = input<number | null>(null);
  /** 033: many points at once, alongside (never instead of) the single
   * landing marker above — existing callers pass nothing and see no change. */
  readonly markers = input<CourtMarker[]>([]);
  /** 034-clutch-points-player-dashboard: a cross-match distribution can
   * carry hundreds of markers. Dense mode draws them smaller and more
   * transparent so overlap reads as density; circle vs diamond is untouched,
   * so the two kinds still differ by shape. Existing callers pass nothing
   * and see no change. */
  readonly dense = input(false);
}
