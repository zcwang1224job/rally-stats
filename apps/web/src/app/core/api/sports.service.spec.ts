import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { FALLBACK_CATALOG, SportsService } from './sports.service';
import { SportsCatalogResponse } from './sport.models';

const CATALOG: SportsCatalogResponse = { ...FALLBACK_CATALOG, types: [] };

describe('SportsService', () => {
  it('without an HttpClient the catalogue is the badminton-only fallback', async () => {
    TestBed.configureTestingModule({});
    const catalog = await firstValueFrom(TestBed.inject(SportsService).getCatalog());
    expect(catalog).toBe(FALLBACK_CATALOG);
    expect(catalog.builtin.map((sport) => sport.sport_key)).toEqual(['badminton']);
  });

  describe('with HttpClient', () => {
    let http: HttpTestingController;
    let service: SportsService;

    beforeEach(() => {
      TestBed.configureTestingModule({
        providers: [provideHttpClient(), provideHttpClientTesting()],
      });
      http = TestBed.inject(HttpTestingController);
      service = TestBed.inject(SportsService);
    });

    afterEach(() => http.verify());

    it('reads GET /sports once and caches it', async () => {
      const first = firstValueFrom(service.getCatalog());
      http.expectOne((request) => request.url.endsWith('/sports')).flush(CATALOG);
      expect(await first).toEqual(CATALOG);
      expect(await firstValueFrom(service.getCatalog())).toEqual(CATALOG);
      http.expectNone((request) => request.url.endsWith('/sports'));
    });

    it('refresh re-reads it', async () => {
      const first = firstValueFrom(service.getCatalog());
      http.expectOne((request) => request.url.endsWith('/sports')).flush(CATALOG);
      await first;
      const again = firstValueFrom(service.getCatalog(undefined, true));
      http.expectOne((request) => request.url.endsWith('/sports')).flush(CATALOG);
      expect(await again).toEqual(CATALOG);
    });

    it('a failed request falls back instead of breaking the form', async () => {
      const result = firstValueFrom(service.getCatalog());
      http
        .expectOne((request) => request.url.endsWith('/sports'))
        .flush('down', { status: 503, statusText: 'Service Unavailable' });
      expect(await result).toBe(FALLBACK_CATALOG);
    });
  });
});
