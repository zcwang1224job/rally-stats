import { buildLineShareUrl } from './line-share';

describe('buildLineShareUrl', () => {
  it('sends the link and the message to LINE\'s share endpoint', () => {
    expect(buildLineShareUrl('https://rally.example/guest-access/tok-abc', 'hello')).toBe(
      'https://social-plugins.line.me/lineit/share' +
        '?url=https%3A%2F%2Frally.example%2Fguest-access%2Ftok-abc&text=hello',
    );
  });

  it('percent-encodes both parameters so neither can break the other', () => {
    const url = buildLineShareUrl('https://rally.example/g?a=1#top', '小明 你好 & 歡迎');

    // 連結裡的 & 和 # 若沒編碼，就會被當成 lineit/share 自己的參數／片段。
    expect(url).toContain('url=https%3A%2F%2Frally.example%2Fg%3Fa%3D1%23top');
    expect(url).toContain('text=%E5%B0%8F%E6%98%8E%20%E4%BD%A0%E5%A5%BD%20%26%20%E6%AD%A1%E8%BF%8E');
    expect(url.split('?')[1].split('&').length).toBe(2);
  });
});
