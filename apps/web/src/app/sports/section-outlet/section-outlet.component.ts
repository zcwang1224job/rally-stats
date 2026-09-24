import { NgComponentOutlet } from '@angular/common';
import { Component, Type, effect, inject, input, signal, untracked } from '@angular/core';

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
  imports: [NgComponentOutlet],
  template: `
    <div class="section-stack section-outlet">
      @for (section of sections(); track $index) {
        <ng-container
          *ngComponentOutlet="componentFor(section); inputs: { section: section, context: context() }"
        />
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

  constructor() {
    effect(() => {
      const typeKey = this.context().typeKey;
      untracked(() => {
        const ready = this.registry.peek(typeKey);
        this.loaded.set(ready);
        if (!ready) {
          this.registry.resolve(typeKey).then(
            (module) => {
              if (this.context().typeKey === typeKey) {
                this.loaded.set(module);
              }
            },
            () => undefined,
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
