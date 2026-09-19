import { ApiError } from '../api/api-error';

/** What a REST_ENDS_ROUND refusal says: how many matches resting would
 * cost, and whether the round ends right now (`immediate`) or they'd be
 * cancelled only if the round ends before the player is back. */
export interface RestEndsRound {
  count: number;
  immediate: boolean;
}

/** 037-rest-ready-toggle FR-031/FR-032: when the backend refused a rest
 * that would cost the player matches (REST_ENDS_ROUND), what to ask — the
 * page then prompts and resends with `confirm_round_end`. Anything else (or
 * a malformed detail) is null, so the caller shows its usual error. */
export function restEndsRound(error: ApiError): RestEndsRound | null {
  if (error.errorCode !== 'REST_ENDS_ROUND') {
    return null;
  }
  const count = error.detail?.['matches_to_cancel'];
  if (typeof count !== 'number' || !Number.isInteger(count) || count <= 0) {
    return null;
  }
  // An older backend sent no flag: it only ever refused a round ending now.
  return { count, immediate: error.detail?.['immediate'] !== false };
}

/** i18n keys for the prompt's title and body; the admin's names the player. */
export function restEndsRoundKeys(
  refusal: RestEndsRound,
  forAdmin = false,
): { title: string; body: string } {
  if (refusal.immediate) {
    return {
      title: 'restToggle.endsRound.title',
      body: forAdmin ? 'restToggle.endsRound.adminBody' : 'restToggle.endsRound.body',
    };
  }
  return {
    title: 'restToggle.endsRound.laterTitle',
    body: forAdmin ? 'restToggle.endsRound.laterAdminBody' : 'restToggle.endsRound.laterBody',
  };
}
