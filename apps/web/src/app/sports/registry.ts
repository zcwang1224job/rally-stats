import { Injectable } from '@angular/core';

import { SportTypeKey, SportTypeModule } from './sport-type-module';

export type SportTypeLoader = () => Promise<SportTypeModule>;

/**
 * 043 research Decisions 14 / 20: the one place core code reaches into
 * `sports/types/**`, and only through dynamic `import()` — so every sport
 * type module is its own lazy chunk and a user who never meets a sport type
 * never downloads it. Composition root: each loader line carries an eslint
 * exception for the plugin boundary rule.
 */
export const SPORT_TYPE_LOADERS: Partial<Record<SportTypeKey, SportTypeLoader>> = {
  // eslint-disable-next-line no-restricted-syntax -- composition root (constitution XII)
  net_rally: () => import('./types/net-rally/net-rally.module').then((m) => m.NET_RALLY),
  // eslint-disable-next-line no-restricted-syntax -- composition root (constitution XII)
  frames: () => import('./types/frames/frames.module').then((m) => m.FRAMES),
  // eslint-disable-next-line no-restricted-syntax -- composition root (constitution XII)
  generic: () => import('./types/generic/generic.module').then((m) => m.GENERIC),
};

// Outside any injector on purpose: a loaded chunk stays loaded for the app's
// lifetime, and TestBed builds a fresh injector per test. Specs preload the
// modules they exercise from their own bundle (a module preloaded from a
// separate setup bundle would carry its own copies of every class and DI
// token — research Decision 14 revisited in implementation).
const loaded = new Map<string, SportTypeModule>();
const pending = new Map<string, Promise<SportTypeModule>>();

/** Makes a module available synchronously (test setup; eager loaders). */
export function preloadSportTypeModule(module: SportTypeModule): void {
  loaded.set(module.typeKey, module);
}

/** For tests that exercise loading: forget what was loaded. */
export function clearPreloadedSportTypeModules(typeKeys: readonly string[]): void {
  for (const key of typeKeys) {
    loaded.delete(key);
    pending.delete(key);
  }
}

@Injectable({ providedIn: 'root' })
export class SportTypeRegistry {
  /** The module if it is already loaded — lets hosts render synchronously. */
  peek(typeKey: string): SportTypeModule | undefined {
    return loaded.get(typeKey);
  }

  /** Loads (once) and returns the module; rejects if the chunk fails to
   * load, and a later call retries. */
  resolve(typeKey: string): Promise<SportTypeModule> {
    const ready = loaded.get(typeKey);
    if (ready) {
      return Promise.resolve(ready);
    }
    const inFlight = pending.get(typeKey);
    if (inFlight) {
      return inFlight;
    }
    const loader = SPORT_TYPE_LOADERS[typeKey as SportTypeKey];
    if (!loader) {
      return Promise.reject(new Error(`unknown sport type: ${typeKey}`));
    }
    const promise = loader().then(
      (module) => {
        loaded.set(typeKey, module);
        pending.delete(typeKey);
        return module;
      },
      (error: unknown) => {
        pending.delete(typeKey);
        throw error;
      },
    );
    pending.set(typeKey, promise);
    return promise;
  }
}
