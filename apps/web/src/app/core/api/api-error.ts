/** Normalized shape of every backend error response: `{"error_code": ..., "detail": ...}`
 * (constitution VIII — semantic error codes, never hardcoded display strings). */
export interface ApiError {
  errorCode: string;
  i18nKey: string;
  detail: Record<string, unknown> | null;
  status: number;
}
