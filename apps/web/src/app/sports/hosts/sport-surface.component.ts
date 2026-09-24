import {
  Component,
  ComponentRef,
  DestroyRef,
  OnInit,
  ViewContainerRef,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { OutputRefSubscription } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { SportTypeRegistry } from '../registry';
import { SportTypeModule } from '../sport-type-module';

export type SurfaceName = keyof SportTypeModule['surfaces'];

interface Subscribable {
  subscribe(listener: (value: unknown) => void): OutputRefSubscription | { unsubscribe(): void };
}

/**
 * 043 research Decision 14: renders one whole surface (scoreboard, control
 * panel, all-courts block, court control, create-form fields) of whichever
 * sport type `typeKey` names. A preloaded module renders in the same change
 * detection pass — the existing synchronous specs rely on that (the vitest
 * setup preloads net rally); otherwise the module chunk loads first, and a
 * failed load shows a retry instead of a broken page.
 *
 * Inputs are passed through by name; `outputs` maps an output name to a
 * handler, so the surface's own events (e.g. `changed`) reach the page.
 */
@Component({
  selector: 'app-sport-surface',
  imports: [TranslatePipe],
  template: `
    @if (failed()) {
      <p class="empty-state" role="alert" data-state="sport-module-failed">
        {{ 'errors.sportModuleLoadFailed' | translate }}
        <button type="button" class="btn btn--secondary" (click)="retry()">
          {{ 'common.retry' | translate }}
        </button>
      </p>
    } @else if (loading()) {
      <p class="loading-state" data-state="sport-module-loading">{{ 'common.loading' | translate }}</p>
    }
  `,
})
export class SportSurfaceComponent implements OnInit {
  private readonly registry = inject(SportTypeRegistry);
  private readonly container = inject(ViewContainerRef);

  readonly typeKey = input.required<string>();
  readonly surface = input.required<SurfaceName>();
  readonly inputs = input<Record<string, unknown>>({});
  readonly outputs = input<Record<string, (value: unknown) => void>>({});

  readonly loading = signal(false);
  readonly failed = signal(false);

  private ref: ComponentRef<unknown> | null = null;
  private renderedKey: string | null = null;
  private subscriptions: { unsubscribe(): void }[] = [];

  constructor() {
    inject(DestroyRef).onDestroy(() => this.clear());
    // Later input changes reach the rendered surface; a different sport type
    // swaps the surface.
    effect(() => {
      const typeKey = this.typeKey();
      const inputs = this.inputs();
      untracked(() => {
        if (this.renderedKey !== null && typeKey !== this.renderedKey) {
          this.load();
          return;
        }
        this.applyInputs(inputs);
      });
    });
  }

  ngOnInit(): void {
    this.load();
  }

  retry(): void {
    this.load();
  }

  private load(): void {
    const typeKey = this.typeKey();
    const ready = this.registry.peek(typeKey);
    if (ready) {
      this.render(ready, typeKey);
      return;
    }
    this.loading.set(true);
    this.failed.set(false);
    this.registry.resolve(typeKey).then(
      (module) => {
        if (this.typeKey() !== typeKey) {
          // The sport type changed while this one loaded (a page that
          // learns its group's activity after first render): load that one.
          this.load();
          return;
        }
        this.loading.set(false);
        this.render(module, typeKey);
      },
      () => {
        if (this.typeKey() !== typeKey) {
          this.load();
          return;
        }
        this.loading.set(false);
        this.failed.set(true);
      },
    );
  }

  private render(module: SportTypeModule, typeKey: string): void {
    this.clear();
    const component = module.surfaces[this.surface()];
    if (!component) {
      return;
    }
    this.failed.set(false);
    this.ref = this.container.createComponent(component);
    this.renderedKey = typeKey;
    this.applyInputs(this.inputs());
    for (const [name, handler] of Object.entries(this.outputs())) {
      const emitter = (this.ref.instance as Record<string, unknown>)[name] as Subscribable | undefined;
      if (emitter && typeof emitter.subscribe === 'function') {
        this.subscriptions.push(emitter.subscribe(handler));
      }
    }
    this.ref.changeDetectorRef.detectChanges();
  }

  private applyInputs(inputs: Record<string, unknown>): void {
    if (!this.ref) {
      return;
    }
    for (const [name, value] of Object.entries(inputs)) {
      this.ref.setInput(name, value);
    }
  }

  private clear(): void {
    for (const subscription of this.subscriptions) {
      subscription.unsubscribe();
    }
    this.subscriptions = [];
    this.ref?.destroy();
    this.ref = null;
    this.renderedKey = null;
    this.container.clear();
  }
}
