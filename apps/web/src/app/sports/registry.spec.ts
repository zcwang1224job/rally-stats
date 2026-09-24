import { TestBed } from '@angular/core/testing';
import { Component } from '@angular/core';

import {
  SPORT_TYPE_LOADERS,
  SportTypeRegistry,
  clearPreloadedSportTypeModules,
  preloadSportTypeModule,
} from './registry';
import { SportTypeModule } from './sport-type-module';

@Component({ selector: 'app-dummy-surface', template: '' })
class DummySurfaceComponent {}

function fakeModule(typeKey: SportTypeModule['typeKey']): SportTypeModule {
  return {
    typeKey,
    surfaces: {
      scoreboard: DummySurfaceComponent,
      controlPanel: DummySurfaceComponent,
      allCourtsBlock: DummySurfaceComponent,
      courtControl: DummySurfaceComponent,
      createFormFields: null,
    },
    sectionKinds: {},
  };
}

describe('SportTypeRegistry', () => {
  let registry: SportTypeRegistry;
  const saved = { ...SPORT_TYPE_LOADERS };

  beforeEach(() => {
    registry = TestBed.inject(SportTypeRegistry);
  });

  afterEach(() => {
    for (const key of Object.keys(SPORT_TYPE_LOADERS)) {
      delete (SPORT_TYPE_LOADERS as Record<string, unknown>)[key];
    }
    Object.assign(SPORT_TYPE_LOADERS, saved);
    clearPreloadedSportTypeModules(['generic']);
  });

  it('peek() is undefined for a module nobody has loaded', () => {
    delete (SPORT_TYPE_LOADERS as Record<string, unknown>)['generic'];
    clearPreloadedSportTypeModules(['generic']);
    expect(registry.peek('generic')).toBeUndefined();
  });

  it('resolve() loads once and caches, after which peek() is synchronous', async () => {
    const module = fakeModule('generic');
    let calls = 0;
    SPORT_TYPE_LOADERS.generic = () => {
      calls += 1;
      return Promise.resolve(module);
    };
    clearPreloadedSportTypeModules(['generic']);

    expect(await registry.resolve('generic')).toBe(module);
    expect(await registry.resolve('generic')).toBe(module);
    expect(calls).toBe(1);
    expect(registry.peek('generic')).toBe(module);
  });

  it('a failed load rejects and can be retried', async () => {
    const module = fakeModule('generic');
    let fail = true;
    SPORT_TYPE_LOADERS.generic = () => (fail ? Promise.reject(new Error('offline')) : Promise.resolve(module));
    clearPreloadedSportTypeModules(['generic']);

    await expect(registry.resolve('generic')).rejects.toThrow('offline');
    fail = false;
    expect(await registry.resolve('generic')).toBe(module);
  });

  it('an unknown type key rejects', async () => {
    await expect(registry.resolve('nope')).rejects.toThrow('nope');
  });

  it('a preloaded module is visible to every injector synchronously', () => {
    const module = fakeModule('generic');
    preloadSportTypeModule(module);
    TestBed.resetTestingModule();
    expect(TestBed.inject(SportTypeRegistry).peek('generic')).toBe(module);
  });
});
