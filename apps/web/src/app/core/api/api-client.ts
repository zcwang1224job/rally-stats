import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

/** Thin base over HttpClient: prefixes every call with the API base URL so
 * feature services only ever deal with resource paths. Error normalization
 * happens once, centrally, via `errorInterceptor`. */
@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  get<T>(path: string, headers?: Record<string, string>): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${path}`, { headers });
  }

  post<T>(path: string, body: unknown = {}, headers?: Record<string, string>): Observable<T> {
    return this.http.post<T>(`${this.baseUrl}${path}`, body, { headers });
  }

  patch<T>(path: string, body: unknown, headers?: Record<string, string>): Observable<T> {
    return this.http.patch<T>(`${this.baseUrl}${path}`, body, { headers });
  }

  delete<T>(path: string, headers?: Record<string, string>): Observable<T> {
    return this.http.delete<T>(`${this.baseUrl}${path}`, { headers });
  }
}
