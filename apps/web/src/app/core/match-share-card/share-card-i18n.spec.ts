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

describe('matchShareCard language keys (040 FR-027)', () => {
  const zh = leaves((zhTW as unknown as { matchShareCard: Tree }).matchShareCard);
  const eng = leaves((en as unknown as { matchShareCard: Tree }).matchShareCard);

  it('has exactly the same keys in zh-TW and en', () => {
    expect(Object.keys(eng).sort()).toEqual(Object.keys(zh).sort());
  });

  it('never leaves a value empty', () => {
    for (const [key, value] of [...Object.entries(zh), ...Object.entries(eng)]) {
      expect(value.trim().length, key).toBeGreaterThan(0);
    }
  });

  it('covers every highlight kind and the date format', () => {
    for (const kind of [
      'comeback',
      'matchPointsSaved',
      'deuceWin',
      'run',
      'winnerRate',
      'leadChanges',
      'bigMargin',
    ]) {
      expect(zh[`highlight.${kind}`], kind).toBeTruthy();
    }
    expect(zh['dateFormat']).toBe('yyyy/M/d');
    expect(eng['dateFormat']).toBe('MMM d, yyyy');
  });
});
