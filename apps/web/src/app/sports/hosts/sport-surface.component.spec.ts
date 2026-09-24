import { Component, input, output } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import {
  SPORT_TYPE_LOADERS,
  clearPreloadedSportTypeModules,
  preloadSportTypeModule,
} from '../registry';
import { SportTypeModule } from '../sport-type-module';
import { SportSurfaceComponent } from './sport-surface.component';

@Component({ selector: 'app-probe-block', template: `<p class="probe">{{ label() }}</p>` })
class ProbeBlockComponent {
  static last: ProbeBlockComponent | null = null;
  readonly label = input('');
  readonly changed = output<string>();
  constructor() {
    ProbeBlockComponent.last = this;
  }
}

@Component({ selector: 'app-other-block', template: `<p class="other">other</p>` })
class OtherBlockComponent {}

function module(typeKey: SportTypeModule['typeKey'], block: SportTypeModule['surfaces']['scoreboard']): SportTypeModule {
  return {
    typeKey,
    surfaces: {
      scoreboard: block,
      controlPanel: block,
      allCourtsBlock: block,
      courtControl: block,
      createFormFields: null,
    },
    sectionKinds: {},
  };
}

describe('SportSurfaceComponent', () => {
  const savedLoaders = { ...SPORT_TYPE_LOADERS };

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  });

  afterEach(() => {
    clearPreloadedSportTypeModules(['frames', 'generic']);
    for (const key of Object.keys(SPORT_TYPE_LOADERS)) {
      delete (SPORT_TYPE_LOADERS as Record<string, unknown>)[key];
    }
    Object.assign(SPORT_TYPE_LOADERS, savedLoaders);
  });

  function create(typeKey: string, inputs: Record<string, unknown> = {}, outputs = {}) {
    const fixture = TestBed.createComponent(SportSurfaceComponent);
    fixture.componentRef.setInput('typeKey', typeKey);
    fixture.componentRef.setInput('surface', 'allCourtsBlock');
    fixture.componentRef.setInput('inputs', inputs);
    fixture.componentRef.setInput('outputs', outputs);
    fixture.detectChanges();
    return fixture;
  }

  it('renders a preloaded module synchronously, with its inputs', () => {
    preloadSportTypeModule(module('frames', ProbeBlockComponent));
    const fixture = create('frames', { label: 'court 1' });
    const probe = (fixture.nativeElement.parentElement as HTMLElement).querySelector('.probe');
    expect(probe?.textContent).toBe('court 1');
  });

  it('passes later input changes through', () => {
    preloadSportTypeModule(module('frames', ProbeBlockComponent));
    const fixture = create('frames', { label: 'a' });
    fixture.componentRef.setInput('inputs', { label: 'b' });
    fixture.detectChanges();
    const probe = (fixture.nativeElement.parentElement as HTMLElement).querySelector('.probe');
    expect(probe?.textContent).toBe('b');
  });

  it('forwards the surface outputs to the given handlers', () => {
    preloadSportTypeModule(module('frames', ProbeBlockComponent));
    const seen: unknown[] = [];
    ProbeBlockComponent.last = null;
    create('frames', {}, { changed: (value: unknown) => seen.push(value) });
    const rendered = ProbeBlockComponent.last as ProbeBlockComponent | null;
    rendered?.changed.emit('refresh');
    expect(seen).toEqual(['refresh']);
  });

  it('loads a module that is not preloaded, showing a loading state first', async () => {
    SPORT_TYPE_LOADERS.generic = () => Promise.resolve(module('generic', OtherBlockComponent));
    const fixture = create('generic');
    expect(fixture.nativeElement.querySelector('[data-state="sport-module-loading"]')).not.toBeNull();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="sport-module-loading"]')).toBeNull();
    expect((fixture.nativeElement.parentElement as HTMLElement).querySelector('.other')).not.toBeNull();
  });

  it('a failed load shows a retry, and retrying renders the surface', async () => {
    let fail = true;
    SPORT_TYPE_LOADERS.generic = () =>
      fail ? Promise.reject(new Error('offline')) : Promise.resolve(module('generic', OtherBlockComponent));
    const fixture = create('generic');
    await fixture.whenStable();
    fixture.detectChanges();
    const alert = fixture.nativeElement.querySelector('[data-state="sport-module-failed"]') as HTMLElement;
    expect(alert).not.toBeNull();

    fail = false;
    (alert.querySelector('button') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-state="sport-module-failed"]')).toBeNull();
    expect((fixture.nativeElement.parentElement as HTMLElement).querySelector('.other')).not.toBeNull();
  });

  it('the net rally module is a registered loader whose surfaces are the existing screens', async () => {
    clearPreloadedSportTypeModules(['net_rally']);
    const loader = SPORT_TYPE_LOADERS.net_rally;
    expect(loader).toBeDefined();
    const netRally = await loader!();
    expect(netRally.typeKey).toBe('net_rally');
    expect(netRally.surfaces.scoreboard.name).toContain('ScoreboardComponent');
    expect(netRally.surfaces.courtControl.name).toContain('CourtControlComponent');
  });
});
