import { MEDAL_COLORS, MEDAL_TEXT } from './group-share-card-palette';

/** WCAG 2.x relative luminance of a #rrggbb color. */
function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

describe('medal colors (041 FR-009)', () => {
  for (const rank of [1, 2, 3] as const) {
    it(`keeps the rank number readable on medal ${rank} (4.5:1 or better)`, () => {
      expect(MEDAL_COLORS[rank]).toMatch(/^#[0-9a-f]{6}$/i);
      expect(contrast(MEDAL_TEXT, MEDAL_COLORS[rank])).toBeGreaterThanOrEqual(4.5);
    });
  }
});
