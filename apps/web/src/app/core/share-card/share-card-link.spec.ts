import { buildShareCardLink } from './share-card-link';
import { ShareCardSource } from './share-card-option';

const site = { origin: 'https://rallystats.example', host: 'rallystats.example' };
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

describe('buildShareCardLink (041 FR-019, FR-021)', () => {
  const sources: ShareCardSource[] = ['card-rank', 'card-me', 'card-match'];

  for (const source of sources) {
    it(`points the QR code at the home page, tagged ${source}`, () => {
      expect(buildShareCardLink(site, source).qrUrl).toBe(
        `https://rallystats.example/?ref=${source}`,
      );
    });
  }

  it('shows just the host, with no scheme, path or parameters', () => {
    const { displayUrl } = buildShareCardLink(site, 'card-rank');

    expect(displayUrl).toBe('rallystats.example');
    expect(displayUrl).not.toMatch(/http|\/|\?/);
  });

  it('keeps a port — cards made on a LAN test site point back to it', () => {
    const link = buildShareCardLink(
      { origin: 'http://192.168.1.23:4200', host: '192.168.1.23:4200' },
      'card-me',
    );

    expect(link.qrUrl).toBe('http://192.168.1.23:4200/?ref=card-me');
    expect(link.displayUrl).toBe('192.168.1.23:4200');
  });

  it('carries no ID of any kind', () => {
    for (const source of sources) {
      const link = buildShareCardLink(site, source);
      expect(link.qrUrl).not.toMatch(UUID);
      expect(link.qrUrl.split('?')[1]).toBe(`ref=${source}`);
    }
  });
});
