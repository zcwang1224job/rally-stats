import type { InputSignal, Type } from '@angular/core';

/** A server-provided page block (contracts/sections-manifest.md §1). */
export interface Section {
  readonly kind: string;
  readonly title_key: string | null;
  readonly data: unknown;
}

/** What a section component knows besides its own section. */
export interface SectionContext {
  /** Sport type of the page (`net_rally`, `frames`, `generic`). */
  readonly typeKey: string;
  /**
   * The whole response the section came from, for `data: null` sections that
   * read top-level fields (research Decision 12).
   */
  readonly source: unknown;
}

/** Every component registered under `SportTypeModule.sectionKinds`. */
export interface SectionComponent {
  readonly section: InputSignal<Section>;
  readonly context: InputSignal<SectionContext>;
}

export type SportTypeKey = 'net_rally' | 'frames' | 'generic';

/**
 * One sport type's frontend module (contracts/plugin-boundary.md §4). Hosts
 * depend only on this interface and `SportTypeRegistry`.
 */
export interface SportTypeModule {
  readonly typeKey: SportTypeKey;
  readonly surfaces: {
    readonly scoreboard: Type<unknown>;
    readonly controlPanel: Type<unknown>;
    readonly allCourtsBlock: Type<unknown>;
    readonly courtControl: Type<unknown>;
    readonly createFormFields: Type<unknown> | null;
  };
  readonly sectionKinds: Readonly<Record<string, Type<SectionComponent>>>;
}
