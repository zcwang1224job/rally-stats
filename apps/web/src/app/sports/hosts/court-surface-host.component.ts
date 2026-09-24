import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';

import { CourtControlService } from '../../core/api/court-control.service';
import { LEGACY_SPORT_TYPE } from '../sport-type-module';
import { SportSurfaceComponent, SurfaceName } from './sport-surface.component';

/**
 * 043: the `/scoreboard/:courtToken` and `/control/:courtToken` routes. Reads
 * the court's state once to learn the group's sport type, then renders that
 * type's scoreboard or control panel (route data `surface`). The surface
 * reads the token from the same route and loads its own state, exactly as
 * when it was the route component itself.
 *
 * A failed lookup (bad token, network) still renders the legacy surface,
 * whose own error states explain what went wrong.
 */
@Component({
  selector: 'app-court-surface-host',
  imports: [SportSurfaceComponent],
  template: `
    @if (typeKey(); as key) {
      <app-sport-surface [typeKey]="key" [surface]="surface" />
    }
  `,
})
export class CourtSurfaceHostComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly courtControl = inject(CourtControlService);

  readonly surface = this.route.snapshot.data['surface'] as SurfaceName;
  readonly typeKey = signal<string | null>(null);

  constructor() {
    const token = this.route.snapshot.paramMap.get('courtToken') ?? '';
    this.courtControl
      .getState(token)
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe({
        next: (state) => this.typeKey.set(state.sport?.type_key ?? LEGACY_SPORT_TYPE),
        error: () => this.typeKey.set(LEGACY_SPORT_TYPE),
      });
  }
}
