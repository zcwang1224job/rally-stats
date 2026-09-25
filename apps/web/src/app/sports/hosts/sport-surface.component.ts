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
  /** A change of this key rebuilds the surface even for the same sport
   * type (the create form: two activities of one type keep separate
   * parameter fields). */
  readonly instanceKey = input<string | null>(null);

  readonly loading = signal(false);
  readonly failed = signal(false);

  private ref: ComponentRef<unknown> | null = null;
  /** `typeKey|instanceKey` of the last load asked for, and of what is on
   * screen (set even when the module has no such surface, or failed). */
  private requested: string | null = null;
  private rendered: string | null = null;
  private subscriptions: { unsubscribe(): void }[] = [];

  constructor() {
    inject(DestroyRef).onDestroy(() => this.clear());
    // Later input changes reach the rendered surface; a different sport type
    // swaps the surface.
    effect(() => {
      const wanted = this.wanted();
      const inputs = this.inputs();
      untracked(() => {
        if (this.requested !== null && wanted !== this.requested) {
          if (wanted === this.rendered) {
            // Back to what is on screen while another type was loading:
            // keep it; the pending load is dropped when it resolves.
            this.requested = wanted;
            this.loading.set(false);
            this.failed.set(false);
          } else {
            this.load();
            return;
          }
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

  private wanted(): string {
    return `${this.typeKey()}|${this.instanceKey() ?? ''}`;
  }

  private load(): void {
    const typeKey = this.typeKey();
    const wanted = this.wanted();
    this.requested = wanted;
    const ready = this.registry.peek(typeKey);
    if (ready) {
      this.loading.set(false);
      this.failed.set(false);
      this.render(ready, wanted);
      return;
    }
    this.loading.set(true);
    this.failed.set(false);
    this.registry.resolve(typeKey).then(
      (module) => {
        if (this.requested !== wanted) {
          this.retarget();
          return;
        }
        this.loading.set(false);
        if (this.rendered !== wanted) {
          this.render(module, wanted);
        }
      },
      () => {
        if (this.requested !== wanted) {
          this.retarget();
          return;
        }
        this.loading.set(false);
        this.failed.set(true);
      },
    );
  }

  /** A load finished for a sport type the surface no longer wants (a page
   * that learns its group's activity after first render). If the wanted
   * type is already on screen, only the loading state goes; otherwise load
   * the wanted type. */
  private retarget(): void {
    if (this.rendered === this.requested) {
      this.loading.set(false);
      return;
    }
    this.load();
  }

  private render(module: SportTypeModule, wanted: string): void {
    this.clear();
    this.rendered = wanted;
    const component = module.surfaces[this.surface()];
    if (!component) {
      return;
    }
    this.failed.set(false);
    this.ref = this.container.createComponent(component);
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
    this.rendered = null;
    this.container.clear();
  }
}
