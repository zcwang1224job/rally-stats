import { ApiError } from '../api/api-error';
import { restEndsRoundCount } from './rest-ends-round';

function error(errorCode: string, detail: Record<string, unknown> | null): ApiError {
  return { errorCode, i18nKey: `errors.${errorCode}`, detail, status: 409 };
}

describe('restEndsRoundCount', () => {
  it('reads the number of matches the rest would cancel', () => {
    expect(restEndsRoundCount(error('REST_ENDS_ROUND', { matches_to_cancel: 2 }))).toBe(2);
  });

  it('is null for any other error', () => {
    expect(restEndsRoundCount(error('ROSTER_ENTRY_NOT_FOUND', {}))).toBeNull();
    expect(restEndsRoundCount(error('GROUP_DISBANDED', { matches_to_cancel: 2 }))).toBeNull();
  });

  it('is null when the detail is missing or not a positive whole number', () => {
    expect(restEndsRoundCount(error('REST_ENDS_ROUND', null))).toBeNull();
    expect(restEndsRoundCount(error('REST_ENDS_ROUND', { matches_to_cancel: '2' }))).toBeNull();
    expect(restEndsRoundCount(error('REST_ENDS_ROUND', { matches_to_cancel: 0 }))).toBeNull();
    expect(restEndsRoundCount(error('REST_ENDS_ROUND', { matches_to_cancel: 1.5 }))).toBeNull();
  });
});
