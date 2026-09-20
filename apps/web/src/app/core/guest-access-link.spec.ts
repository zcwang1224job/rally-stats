import { guestAccessLink } from './guest-access-link';

describe('guestAccessLink', () => {
  it('points at this origin\'s guest-access route for the token', () => {
    expect(guestAccessLink('tok-abc')).toBe(
      `${window.location.origin}/guest-access/tok-abc?openExternalBrowser=1`,
    );
  });

  it('asks LINE to hand the link to the phone\'s default browser', () => {
    const url = new URL(guestAccessLink('tok-abc'));

    expect(url.searchParams.get('openExternalBrowser')).toBe('1');
    // token 留在路徑上（GuestAccessComponent 只讀 `:token`），不是 query。
    expect(url.pathname).toBe('/guest-access/tok-abc');
  });
});
