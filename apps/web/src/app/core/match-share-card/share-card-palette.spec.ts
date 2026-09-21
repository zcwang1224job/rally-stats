import { SharePalette, ShareTheme } from './share-card.models';
import { SHARE_PALETTES } from './share-card-palette';

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

describe('SHARE_PALETTES (040 US5, research.md Decision 10)', () => {
  const themes: ShareTheme[] = ['light', 'dark'];

  it('uses #rrggbb colors throughout (so contrast can be checked)', () => {
    for (const theme of themes) {
      for (const [key, value] of Object.entries(SHARE_PALETTES[theme])) {
        expect(value, `${theme}.${key}`).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
  });

  it('gives dark its own background, darker than light', () => {
    expect(SHARE_PALETTES.dark.background).not.toBe(SHARE_PALETTES.light.background);
    expect(luminance(SHARE_PALETTES.dark.background)).toBeLessThan(
      luminance(SHARE_PALETTES.light.background),
    );
  });

  for (const theme of themes) {
    describe(theme, () => {
      const p: SharePalette = SHARE_PALETTES[theme];

      it('keeps all text at 4.5:1 or better against what it sits on', () => {
        const pairs: [string, string, string][] = [
          ['text on background', p.text, p.background],
          ['muted text on background', p.textMuted, p.background],
          ['text on panel', p.text, p.panel],
          ['muted text on panel', p.textMuted, p.panel],
          ['badge text', p.badgeText, p.badgeBackground],
          ['muted badge text', p.badgeMutedText, p.badgeMutedBackground],
        ];
        for (const [label, fg, bg] of pairs) {
          expect(contrast(fg, bg), label).toBeGreaterThanOrEqual(4.5);
        }
      });

      it('keeps team colors and trend lines at 3:1 or better (graphics)', () => {
        const pairs: [string, string, string][] = [
          ['team A bar', p.teamA, p.background],
          ['team B bar', p.teamB, p.background],
          ['trend A', p.trendA, p.panel],
          ['trend B', p.trendB, p.panel],
          ['highlight dot A', p.teamA, p.panel],
          ['highlight dot B', p.teamB, p.panel],
        ];
        for (const [label, fg, bg] of pairs) {
          expect(contrast(fg, bg), label).toBeGreaterThanOrEqual(3);
        }
      });
    });
  }
});
