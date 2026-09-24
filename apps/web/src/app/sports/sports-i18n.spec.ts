// 043 FR-037 / SC-007: every activity, noun and sport-type key exists in both
// languages.
import en from '../../assets/i18n/en.json';
import zhTW from '../../assets/i18n/zh-TW.json';

type Tree = Record<string, unknown>;

function leafKeys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    value !== null && typeof value === 'object'
      ? leafKeys(value as Tree, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

const SPORT_SUBTREES = ['sports', 'sections', 'frames', 'genericSport'];

describe('043 i18n parity', () => {
  for (const subtree of SPORT_SUBTREES) {
    it(`"${subtree}" has the same keys in zh-TW and en`, () => {
      const zh = (zhTW as Tree)[subtree] as Tree | undefined;
      const english = (en as Tree)[subtree] as Tree | undefined;
      expect(Boolean(zh)).toBe(Boolean(english));
      if (zh && english) {
        expect(leafKeys(english).sort()).toEqual(leafKeys(zh).sort());
      }
    });
  }

  it('every built-in activity has a name', () => {
    const keys = ['badminton', 'table_tennis', 'pickleball', 'tennis_tiebreak', 'billiards', 'darts', 'board_game', 'esports', 'other'];
    for (const key of keys) {
      expect(((zhTW as Tree)['sports'] as Tree)[key]).toBeTruthy();
      expect(((en as Tree)['sports'] as Tree)[key]).toBeTruthy();
    }
  });

  it('the create-group and error keys added for activities exist in both languages', () => {
    const zhKeys = new Set(leafKeys(zhTW as Tree));
    const enKeys = new Set(leafKeys(en as Tree));
    const added = [...enKeys].filter(
      (key) => key.startsWith('createGroup.generic.') || key.startsWith('createGroup.activity'),
    );
    expect(added.length).toBeGreaterThan(0);
    for (const key of added) {
      expect(zhKeys.has(key)).toBe(true);
    }
  });
});
