import en from '../../../assets/i18n/en.json';
import zhTW from '../../../assets/i18n/zh-TW.json';

interface Tree {
  [key: string]: string | Tree;
}

function leaves(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      out[path] = value;
    } else {
      Object.assign(out, leaves(value, path));
    }
  }
  return out;
}

describe('shareCard language keys (041 FR-030)', () => {
  const zh = leaves((zhTW as unknown as { shareCard: Tree }).shareCard);
  const eng = leaves((en as unknown as { shareCard: Tree }).shareCard);

  it('has exactly the same keys in zh-TW and en', () => {
    expect(Object.keys(eng).sort()).toEqual(Object.keys(zh).sort());
  });

  it('never leaves a value empty', () => {
    for (const [key, value] of [...Object.entries(zh), ...Object.entries(eng)]) {
      expect(value.trim().length, key).toBeGreaterThan(0);
    }
  });

  it('carries the date pattern the card draws with (moved from 040)', () => {
    expect(zh['dateFormat']).toBe('yyyy/M/d');
    expect(eng['dateFormat']).toBe('MMM d, yyyy');
  });

  it('keeps the Chinese tagline short enough for the footer (16 characters at most)', () => {
    expect([...zh['tagline']].length).toBeLessThanOrEqual(16);
  });
});
