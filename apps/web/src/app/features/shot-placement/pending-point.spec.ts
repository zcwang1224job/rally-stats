import { PendingPoint, PendingPointAction } from './pending-point';

const confirm: PendingPointAction = {
  kind: 'confirm',
  detail: {
    rosterEntryId: null,
    losingRosterEntryId: null,
    landingX: null,
    landingY: null,
    endingType: 'net',
  },
};

describe('PendingPoint', () => {
  it('queues an action taken before the score request resolves, and hands it back on resolve', () => {
    const point = new PendingPoint('m1', 'A');

    expect(point.request(confirm)).toBe(false);
    expect(point.resolve('ev1', false)).toEqual(confirm);
    expect(point.scoreEventId).toBe('ev1');
  });

  it('lets an action through straight away once resolved', () => {
    const point = new PendingPoint('m1', 'A');
    expect(point.resolve('ev1', true)).toBeNull();

    expect(point.request({ kind: 'cancel' })).toBe(true);
    expect(point.matchCompleted).toBe(true);
  });

  it('keeps only the latest action taken while unresolved', () => {
    const point = new PendingPoint('m1', 'B');
    point.request(confirm);
    point.request({ kind: 'cancel' });

    expect(point.resolve('ev1', false)).toEqual({ kind: 'cancel' });
  });
});
