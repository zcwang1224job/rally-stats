import en from '../../assets/i18n/en.json';
import zhTW from '../../assets/i18n/zh-TW.json';
import { waitingReasonKey } from './waiting-reason-label';

function lookup(bundle: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      bundle,
    );
}

describe('waitingReasonKey', () => {
  it('names the two rest reasons', () => {
    expect(waitingReasonKey('held_for_rest')).toBe('scheduleManagement.waitingHeldForRest');
    expect(waitingReasonKey('not_enough_ready')).toBe('scheduleManagement.waitingNotEnoughReady');
  });

  it('keeps the member page wording for the original reasons', () => {
    expect(waitingReasonKey('manual_assignment', 'member')).toBe(
      'groupMemberView.schedule.waitingManualAssignment',
    );
    expect(waitingReasonKey('no_queued_match', 'member')).toBe(
      'groupMemberView.schedule.waitingNoQueuedMatch',
    );
  });

  it('falls back to "next round" for a reason it does not know, or none', () => {
    expect(waitingReasonKey('something_new')).toBe('scheduleManagement.waitingNoQueuedMatch');
    expect(waitingReasonKey(null, 'member')).toBe('groupMemberView.schedule.waitingNoQueuedMatch');
  });

  it('points at strings that exist in both languages', () => {
    const reasons = ['manual_assignment', 'no_queued_match', 'held_for_rest', 'not_enough_ready'];
    for (const reason of reasons) {
      for (const scope of ['court', 'member'] as const) {
        const key = waitingReasonKey(reason, scope);
        expect(typeof lookup(zhTW, key), `zh-TW ${key}`).toBe('string');
        expect(typeof lookup(en, key), `en ${key}`).toBe('string');
      }
    }
  });
});
