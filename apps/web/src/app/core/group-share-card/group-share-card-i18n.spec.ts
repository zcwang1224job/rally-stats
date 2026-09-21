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

describe('groupShareCard language keys (041 FR-030)', () => {
  const zh = leaves((zhTW as unknown as { groupShareCard: Tree }).groupShareCard);
  const eng = leaves((en as unknown as { groupShareCard: Tree }).groupShareCard);

  it('has exactly the same keys in zh-TW and en', () => {
    expect(Object.keys(eng).sort()).toEqual(Object.keys(zh).sort());
  });

  it('never leaves a value empty', () => {
    for (const [key, value] of [...Object.entries(zh), ...Object.entries(eng)]) {
      expect(value.trim().length, key).toBeGreaterThan(0);
    }
  });

  it('never calls the leaderboard "final" — a group can still be playing (FR-012)', () => {
    expect(zh['leaderboard.title']).not.toContain('最終');
    expect(eng['leaderboard.title']).not.toMatch(/final/i);
  });

  it('takes every rank in the alt text from a parameter, never a fixed number (FR-008)', () => {
    for (const lang of [zh, eng]) {
      for (const count of [1, 2, 3]) {
        const text = lang[`leaderboard.altText${count}`];
        for (let n = 1; n <= count; n++) {
          expect(text, `altText${count}`).toContain(`{{rank${n}}}`);
          expect(text, `altText${count}`).toContain(`{{name${n}}}`);
        }
        expect(text).toContain('{{group}}');
      }
    }
  });
});
