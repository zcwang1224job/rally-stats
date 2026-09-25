import { NgComponentOutlet } from '@angular/common';
import { Component, Type, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { FallbackSectionComponent } from '../generic-sections/fallback-section.component';
import { GENERIC_SECTION_COMPONENTS } from '../generic-sections/generic-sections';
import { SportTypeRegistry } from '../registry';
import { Section, SectionComponent, SectionContext, SportTypeModule } from '../sport-type-module';

/**
 * 043 FR-021: renders a server-provided list of sections. Each kind resolves
 * to the sport type module's own component, then a generic section, then the
 * fallback — so an unknown kind is never blank and never an error (SC-008).
 * The page decides nothing about which sections exist.
 */
@Component({
  selector: 'app-section-outlet',
  imports: [NgComponentOutlet, TranslatePipe],
  template: `
    <div class="section-stack section-outlet">
      @if (!ready() && needsModule()) {
        <p class="loading-state" role="status" data-state="sections-loading">{{ 'common.loading' | translate }}</p>
      } @else {
      @for (section of sections(); track $index) {
        <ng-container
          *ngComponentOutlet="componentFor(section); inputs: { section: section, context: context() }"
        />
      }
      }
    </div>
  `,
})
export class SectionOutletComponent {
  private readonly registry = inject(SportTypeRegistry);

  readonly sections = input.required<readonly Section[]>();
  readonly context = input.required<SectionContext>();

  /** The page's sport type module once its chunk has loaded; until then (or
   * if it fails to load) the generic sections and the fallback render. */
  private readonly loaded = signal<SportTypeModule | undefined>(undefined);
  /** False while the module chunk loads: a module kind must not flash the
   * "needs a newer version" fallback first. A failed load renders anyway. */
  readonly ready = signal(false);
  /** Generic kinds render at once; only `<typeKey>.*` kinds need the chunk. */
  readonly needsModule = computed(() => {
    const prefix = `${this.context().typeKey}.`;
    return this.sections().some((section) => section.kind.startsWith(prefix));
  });

  constructor() {
    effect(() => {
      const typeKey = this.context().typeKey;
      untracked(() => {
        const ready = this.registry.peek(typeKey);
        this.loaded.set(ready);
        this.ready.set(ready !== undefined);
        if (!ready) {
          this.registry.resolve(typeKey).then(
            (module) => {
              if (this.context().typeKey === typeKey) {
                this.loaded.set(module);
                this.ready.set(true);
              }
            },
            () => {
              if (this.context().typeKey === typeKey) {
                this.ready.set(true);
              }
            },
          );
        }
      });
    });
  }

  componentFor(section: Section): Type<SectionComponent> {
    const module = this.loaded() ?? this.registry.peek(this.context().typeKey);
    return (
      module?.sectionKinds[section.kind] ??
      GENERIC_SECTION_COMPONENTS[section.kind] ??
      FallbackSectionComponent
    );
  }
}
