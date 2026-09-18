import { getBenchmarkGroup, setBenchmarkGroup } from './benchmark-group-preference';

describe('benchmark group preference (036 FR-027)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('remembers the last group per member', () => {
    setBenchmarkGroup('member-1', 'group-a');
    setBenchmarkGroup('member-2', 'group-b');

    expect(getBenchmarkGroup('member-1')).toBe('group-a');
    expect(getBenchmarkGroup('member-2')).toBe('group-b');
    expect(getBenchmarkGroup('member-3')).toBeNull();
  });

  it('does nothing without a member id', () => {
    setBenchmarkGroup(null, 'group-a');
    expect(getBenchmarkGroup(null)).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it('never throws when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(getBenchmarkGroup('member-1')).toBeNull();
    expect(() => setBenchmarkGroup('member-1', 'group-a')).not.toThrow();
  });
});
