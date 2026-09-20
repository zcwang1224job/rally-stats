import { buildLineShareUrl } from './line-share';

describe('buildLineShareUrl', () => {
  it('puts the message into LINE\'s share URL scheme', () => {
    expect(buildLineShareUrl('hello')).toBe('https://line.me/R/share?text=hello');
  });

  it('percent-encodes the message so a link inside it survives', () => {
    const url = buildLineShareUrl('小明 你好：https://rally.example/guest-access/tok-abc');

    expect(url.startsWith('https://line.me/R/share?text=')).toBe(true);
    expect(url).toContain('https%3A%2F%2Frally.example%2Fguest-access%2Ftok-abc');
    // 訊息裡不能留下沒編碼的 & 或 #，不然會被當成 URL 參數／片段而截斷。
    expect(url.slice('https://line.me/R/share?text='.length)).not.toMatch(/[&#]/);
  });
});
