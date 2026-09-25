import { Component, input } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import { SPORT_TYPE_LOADERS, clearPreloadedSportTypeModules, preloadSportTypeModule } from '../registry';
import { Section, SectionComponent, SectionContext, SportTypeModule } from '../sport-type-module';
import { SectionOutletComponent } from './section-outlet.component';

@Component({
  selector: 'app-probe-section',
  template: `<p class="probe">{{ section().kind }}|{{ sourceTag() }}</p>`,
})
class ProbeSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();
  sourceTag(): string {
    return (this.context().source as { tag?: string } | null)?.tag ?? '';
  }
}

@Component({ selector: 'app-probe-surface', template: '' })
class ProbeSurfaceComponent {}

const PROBE_MODULE: SportTypeModule = {
  typeKey: 'frames',
  surfaces: {
    scoreboard: ProbeSurfaceComponent,
    controlPanel: ProbeSurfaceComponent,
    allCourtsBlock: ProbeSurfaceComponent,
    courtControl: ProbeSurfaceComponent,
    createFormFields: null,
  },
  sectionKinds: { 'frames.frame_list': ProbeSectionComponent },
};

function render(sections: Section[], typeKey = 'frames', source: unknown = null): HTMLElement {
  const fixture = TestBed.createComponent(SectionOutletComponent);
  fixture.componentRef.setInput('sections', sections);
  fixture.componentRef.setInput('context', { typeKey, source });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('SectionOutletComponent', () => {
  beforeEach(() => {
    preloadSportTypeModule(PROBE_MODULE);
    TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  });

  afterEach(() => clearPreloadedSportTypeModules(['frames']));

  it('renders a kind the sport type module registers with its own component', () => {
    const el = render([{ kind: 'frames.frame_list', title_key: null, data: { frames: [] } }]);
    expect(el.querySelector('.probe')?.textContent).toContain('frames.frame_list');
  });

  it('passes the page source through for data:null sections', () => {
    const el = render([{ kind: 'frames.frame_list', title_key: null, data: null }], 'frames', {
      tag: 'top-level',
    });
    expect(el.querySelector('.probe')?.textContent).toContain('top-level');
  });

  it('renders a generic kind without any sport type module', () => {
    const el = render(
      [
        {
          kind: 'metric_grid',
          title_key: null,
          data: { metrics: [{ key: 'wins', label_key: 'x', kind: 'count', value: 3 }] },
        },
      ],
      'generic',
    );
    expect(el.querySelector('[data-section-kind="metric_grid"]')).not.toBeNull();
    expect(el.querySelector('[data-metric="wins"]')?.textContent).toContain('3');
  });

  it('shows nothing but a loading note until the sport type chunk has loaded (no fallback flash)', async () => {
    clearPreloadedSportTypeModules(['frames']);
    const savedFramesLoader = SPORT_TYPE_LOADERS.frames;
    let finish!: () => void;
    SPORT_TYPE_LOADERS.frames = () => new Promise((resolve) => (finish = () => resolve(PROBE_MODULE)));
    const fixture = TestBed.createComponent(SectionOutletComponent);
    fixture.componentRef.setInput('sections', [{ kind: 'frames.frame_list', title_key: null, data: null }]);
    fixture.componentRef.setInput('context', { typeKey: 'frames', source: null });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-state="sections-loading"]')).not.toBeNull();
    expect(el.querySelector('[data-section-kind]')).toBeNull();
    finish();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(el.querySelector('[data-state="sections-loading"]')).toBeNull();
    expect(el.querySelector('.probe')?.textContent).toContain('frames.frame_list');
    SPORT_TYPE_LOADERS.frames = savedFramesLoader;
  });

  it('an unknown kind falls back instead of rendering nothing or throwing', () => {
    const el = render([{ kind: 'unknown.kind', title_key: null, data: { streak: 4 } }]);
    const fallback = el.querySelector('[data-section-kind="fallback"]');
    expect(fallback).not.toBeNull();
    expect(fallback?.getAttribute('data-unknown-kind')).toBe('unknown.kind');
    expect(fallback?.textContent).toContain('streak');
  });

  it('keeps the server order of sections', () => {
    const el = render([
      { kind: 'text_note', title_key: null, data: { text_key: 'a' } },
      { kind: 'frames.frame_list', title_key: null, data: null },
      { kind: 'stat_table', title_key: null, data: { columns: [], rows: [] } },
    ]);
    const kinds = Array.from(el.querySelectorAll('[data-section-kind], .probe')).map(
      (node) => node.getAttribute('data-section-kind') ?? 'probe',
    );
    expect(kinds).toEqual(['text_note', 'probe', 'stat_table']);
  });
});
