import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';
import { environment } from '../../../../environments/environment';

declare global {
  interface Window {
    turnstile?: {
      render(container: HTMLElement, options: Record<string, unknown>): string;
      remove(widgetId: string): void;
      reset(widgetId: string): void;
    };
  }
}

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
let scriptLoadPromise: Promise<void> | null = null;

function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) {
    return Promise.resolve();
  }
  if (!scriptLoadPromise) {
    scriptLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('Failed to load Cloudflare Turnstile script'));
      document.head.appendChild(script);
    });
  }
  return scriptLoadPromise;
}

/** Wraps the Cloudflare Turnstile widget (spec FR-007), re-rendering when the
 * active i18n language changes so the challenge UI follows the user's locale. */
@Component({
  selector: 'app-turnstile-widget',
  template: `<div #container></div>`,
  styleUrl: './turnstile-widget.component.scss',
})
export class TurnstileWidgetComponent implements AfterViewInit, OnDestroy {
  readonly language = input<string>('zh-tw');
  readonly verified = output<string>();
  readonly expired = output<void>();

  private readonly container = viewChild.required<ElementRef<HTMLDivElement>>('container');
  private widgetId: string | null = null;
  private viewReady = false;

  constructor() {
    effect(() => {
      this.language();
      if (this.viewReady) {
        void this.render();
      }
    });
  }

  async ngAfterViewInit(): Promise<void> {
    this.viewReady = true;
    await this.render();
  }

  ngOnDestroy(): void {
    if (this.widgetId && window.turnstile) {
      window.turnstile.remove(this.widgetId);
    }
  }

  private async render(): Promise<void> {
    await loadTurnstileScript();
    if (this.widgetId && window.turnstile) {
      window.turnstile.remove(this.widgetId);
    }
    this.widgetId = window.turnstile!.render(this.container().nativeElement, {
      sitekey: environment.turnstileSiteKey,
      language: this.language(),
      callback: (token: string) => this.verified.emit(token),
      'expired-callback': () => this.expired.emit(),
    });
  }
}
