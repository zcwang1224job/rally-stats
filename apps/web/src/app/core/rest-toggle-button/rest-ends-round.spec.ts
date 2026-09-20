import { ApiError } from '../api/api-error';
import { restEndsRound, restEndsRoundKeys } from './rest-ends-round';

function error(errorCode: string, detail: Record<string, unknown> | null): ApiError {
  return { errorCode, i18nKey: `errors.${errorCode}`, detail, status: 409 };
}

describe('restEndsRound', () => {
  it('reads how many matches the rest would cost, and whether the round ends now', () => {
    expect(
      restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: 2, immediate: true })),
    ).toEqual({ count: 2, immediate: true });
    expect(
      restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: 3, immediate: false })),
    ).toEqual({ count: 3, immediate: false });
  });

  it('treats a refusal without the flag (older backend) as the round ending now', () => {
    expect(restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: 1 }))).toEqual({
      count: 1,
      immediate: true,
    });
  });

  it('is null for any other error', () => {
    expect(restEndsRound(error('ROSTER_ENTRY_NOT_FOUND', {}))).toBeNull();
    expect(restEndsRound(error('GROUP_DISBANDED', { matches_to_cancel: 2 }))).toBeNull();
  });

  it('is null when the detail is missing or not a positive whole number', () => {
    expect(restEndsRound(error('REST_ENDS_ROUND', null))).toBeNull();
    expect(restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: '2' }))).toBeNull();
    expect(restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: 0 }))).toBeNull();
    expect(restEndsRound(error('REST_ENDS_ROUND', { matches_to_cancel: 1.5 }))).toBeNull();
  });
});

describe('restEndsRoundKeys', () => {
  it('picks the wording for each case', () => {
    expect(restEndsRoundKeys({ count: 1, immediate: true })).toEqual({
      title: 'restToggle.endsRound.title',
      body: 'restToggle.endsRound.body',
    });
    expect(restEndsRoundKeys({ count: 1, immediate: false })).toEqual({
      title: 'restToggle.endsRound.laterTitle',
      body: 'restToggle.endsRound.laterBody',
    });
    expect(restEndsRoundKeys({ count: 1, immediate: false }, true).body).toBe(
      'restToggle.endsRound.laterAdminBody',
    );
    expect(restEndsRoundKeys({ count: 1, immediate: true }, true).body).toBe(
      'restToggle.endsRound.adminBody',
    );
  });
});
