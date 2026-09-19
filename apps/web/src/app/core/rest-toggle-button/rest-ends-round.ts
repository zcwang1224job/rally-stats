import { ApiError } from '../api/api-error';

/** 037-rest-ready-toggle FR-031/FR-032: when the backend refused a rest
 * because it would end the round on the spot (REST_ENDS_ROUND), how many
 * matches it would cancel — the page then asks, and resends with
 * `confirm_round_end`. Anything else (or a malformed detail) is null, so
 * the caller shows its usual error instead. */
export function restEndsRoundCount(error: ApiError): number | null {
  if (error.errorCode !== 'REST_ENDS_ROUND') {
    return null;
  }
  const count = error.detail?.['matches_to_cancel'];
  return typeof count === 'number' && Number.isInteger(count) && count > 0 ? count : null;
}
