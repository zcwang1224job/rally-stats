import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, Injector, inject } from '@angular/core';
import { Observable, catchError, map, of, shareReplay } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Section } from '../../sports/sport-type-module';
import {
  ActivitySummary,
  BuiltinSport,
  CustomSport,
  SportDefaults,
  SportSummary,
  SportsCatalogResponse,
} from './sport.models';

/** Badminton exactly as every group was before 043 — what the create form
 * starts on, and all the catalogue holds if `/sports` can't be reached. */
export const BADMINTON_FALLBACK: BuiltinSport = {
  sport_key: 'badminton',
  type_key: 'net_rally',
  name_key: 'sports.badminton',
  icon: 'shuttle',
  team_size_options: [1, 2],
  defaults: {
    team_size: 1,
    end_mode: 'target',
    target_score: 21,
    win_by: 2,
    cap_score: 30,
    allow_draw: false,
    score_steps: [1],
    type_params: { modules: { serve_tracking: true, shot_placement: true } },
    scoring_mode: '21pt',
  },
  nouns: { venue: 'court', score: 'point', member: 'player' },
};

export const FALLBACK_CATALOG: SportsCatalogResponse = {
  types: [],
  builtin: [BADMINTON_FALLBACK],
  custom: [],
};

export interface DashboardSectionsResponse {
  sport: SportSummary;
  type_key: string;
  total_matches: number;
  sections: Section[];
}

export interface CustomSportCreate {
  name: string;
  type_key: string;
  team_size_options: number[];
  defaults: SportDefaults & { nouns?: SportSummary['nouns'] };
}

/**
 * 043: the activity catalogue, custom activities and per-activity dashboards
 * (contracts/sports-api.md, contracts/sections-manifest.md).
 *
 * HttpClient is looked up per call, not injected up front, so screens that
 * only read the catalogue keep working in contexts without it (they get the
 * badminton-only fallback) — a failed `/sports` call degrades the same way.
 */
@Injectable({ providedIn: 'root' })
export class SportsService {
  private readonly injector = inject(Injector);
  private readonly baseUrl = environment.apiBaseUrl;
  /** One cache per login: the custom activities in it are the caller's. */
  private readonly catalogs = new Map<string, Observable<SportsCatalogResponse>>();

  private http(): HttpClient | null {
    return this.injector.get(HttpClient, null);
  }

  /** Cached for the page's lifetime; `refresh` re-reads it (after a custom
   * activity is added or removed). */
  getCatalog(headers?: Record<string, string>, refresh = false): Observable<SportsCatalogResponse> {
    const http = this.http();
    if (!http) {
      return of(FALLBACK_CATALOG);
    }
    const key = headers?.['Authorization'] ?? '';
    let catalog$ = this.catalogs.get(key);
    if (!catalog$ || refresh) {
      catalog$ = http
        .get<SportsCatalogResponse>(`${this.baseUrl}/sports`, { headers })
        .pipe(
          catchError(() => of(FALLBACK_CATALOG)),
          shareReplay(1),
        );
      this.catalogs.set(key, catalog$);
    }
    return catalog$;
  }

  createCustomSport(body: CustomSportCreate, headers: Record<string, string>): Observable<CustomSport> {
    return this.requireHttp().post<CustomSport>(`${this.baseUrl}/members/me/sports`, body, { headers });
  }

  deleteCustomSport(id: string, headers: Record<string, string>): Observable<void> {
    return this.requireHttp()
      .delete<null>(`${this.baseUrl}/members/me/sports/${id}`, { headers })
      .pipe(map(() => undefined));
  }

  /** The activities a member has match records for (dashboard tabs). */
  getActivities(headers: Record<string, string>, memberId?: string): Observable<ActivitySummary[]> {
    const who = memberId ?? 'me';
    return this.requireHttp()
      .get<{ activities: ActivitySummary[] }>(`${this.baseUrl}/members/${who}/activities`, { headers })
      .pipe(map((response) => response.activities));
  }

  getDashboardSections(
    params: HttpParams,
    headers: Record<string, string>,
    memberId?: string,
  ): Observable<DashboardSectionsResponse> {
    const who = memberId ?? 'me';
    return this.requireHttp().get<DashboardSectionsResponse>(
      `${this.baseUrl}/members/${who}/dashboard-sections`,
      { params, headers },
    );
  }

  private requireHttp(): HttpClient {
    const http = this.http();
    if (!http) {
      throw new Error('HttpClient is not available');
    }
    return http;
  }
}
