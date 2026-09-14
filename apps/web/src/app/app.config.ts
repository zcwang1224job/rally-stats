import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideTranslateHttpLoader } from '@ngx-translate/http-loader';
import { provideTranslateService } from '@ngx-translate/core';

import { routes } from './app.routes';
import { errorInterceptor } from './core/api/error-interceptor';
import { resolveInitialLanguage } from './core/language/language.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([errorInterceptor])),
    provideTranslateService({
      lang: resolveInitialLanguage(),
      // 024-add-english-language FR-005: the fallback stays hardcoded to
      // zh-TW regardless of the resolved starting language — a key missing
      // from a freshly-added translation file degrades to Chinese, not an
      // empty string, and existing zh-TW users are never affected by this
      // fallback at all.
      fallbackLang: 'zh-TW',
      // i18n JSON isn't content-hashed like the JS/CSS bundles, so a stale
      // S3/CDN or iOS Safari cache can keep serving an old translation file
      // after a deploy. A per-load query param busts that cache regardless
      // of what Cache-Control the static host sends.
      loader: provideTranslateHttpLoader({
        prefix: '/assets/i18n/',
        suffix: `.json?v=${Date.now()}`,
      }),
    }),
  ]
};
