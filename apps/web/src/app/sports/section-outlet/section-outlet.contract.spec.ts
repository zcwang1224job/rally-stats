// 043 T117 (US7, SC-008): every section kind the backend's sport types may
// send has a component on this side — the sport type's own, or a generic
// one — and an unknown kind still renders the fallback. The list comes from
// apps/api/app/sports/section-kinds.json, which the backend's plugin
// contract test keeps in step with the registered plugins.
import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import manifest from '../../../../../api/app/sports/section-kinds.json';
import { FallbackSectionComponent } from '../generic-sections/fallback-section.component';
import { GENERIC_SECTION_COMPONENTS } from '../generic-sections/generic-sections';
import { SportTypeModule } from '../sport-type-module';
import { SectionOutletComponent } from './section-outlet.component';
// eslint-disable-next-line no-restricted-imports -- contract test: checks every module (constitution XII)
import { FRAMES } from '../types/frames/frames.module';
// eslint-disable-next-line no-restricted-imports -- contract test: checks every module (constitution XII)
import { GENERIC } from '../types/generic/generic.module';
// eslint-disable-next-line no-restricted-imports -- contract test: checks every module (constitution XII)
import { NET_RALLY } from '../types/net-rally/net-rally.module';
import { preloadSportTypeModule } from '../registry';

const MODULES: Record<string, SportTypeModule> = {
  net_rally: NET_RALLY,
  frames: FRAMES,
  generic: GENERIC,
};

// net_rally's two kinds are markers rendered by the existing pages from the
// response's top-level fields (research Decision 12), never by the outlet.
const PAGE_RENDERED = new Set(['net_rally.match_detail', 'net_rally.dashboard']);

describe('section kinds contract (043 SC-008)', () => {
  it('knows the same sport types as the backend', () => {
    expect(Object.keys(manifest.types).sort()).toEqual(Object.keys(MODULES).sort());
  });

  it('the generic kinds all have components', () => {
    for (const kind of manifest.generic_kinds) {
      expect(GENERIC_SECTION_COMPONENTS[kind], kind).toBeDefined();
    }
  });

  for (const [typeKey, kinds] of Object.entries(manifest.types)) {
    it(`every ${typeKey} kind has a component in its module`, () => {
      const module = MODULES[typeKey];
      for (const kind of kinds as string[]) {
        if (PAGE_RENDERED.has(kind)) {
          continue;
        }
        expect(module.sectionKinds[kind], kind).toBeDefined();
      }
    });
  }

  it('the outlet renders a module kind with its component and an unknown kind with the fallback', () => {
    for (const module of Object.values(MODULES)) {
      preloadSportTypeModule(module);
    }
    TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
    const fixture = TestBed.createComponent(SectionOutletComponent);
    fixture.componentRef.setInput('sections', []);
    fixture.componentRef.setInput('context', { typeKey: 'frames', source: null });
    fixture.detectChanges();
    const outlet = fixture.componentInstance;
    const pick = (kind: string): Type<unknown> => outlet.componentFor({ kind, title_key: null, data: null });
    expect(pick('frames.frame_list')).toBe(FRAMES.sectionKinds['frames.frame_list']);
    expect(pick('metric_grid')).toBe(GENERIC_SECTION_COMPONENTS['metric_grid']);
    expect(pick('unknown.kind')).toBe(FallbackSectionComponent);
  });
});
