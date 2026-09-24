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

  it('every key the backend puts in a section exists in both languages', () => {
    // Title / label / text keys emitted by app/sports (sections-manifest §2–§3).
    const emitted = [
      'sections.opponents',
      'sections.scoreTimeline',
      'sections.column.opponent',
      'sections.metric.match_win_rate',
      'sections.metric.matches',
      'sections.metric.wins',
      'sections.metric.losses',
      'sections.metric.draws',
      'sections.metric.avg_points_for',
      'sections.metric.avg_points_against',
      'sections.metric.points_a',
      'sections.metric.points_b',
      'sections.metric.margin',
      'frames.sections.frameList',
      'frames.sections.frameTrend',
      'frames.sections.summary',
      'frames.metric.frame_win_rate',
      'frames.metric.win_rate_after_first_frame',
      'frames.metric.avg_frames_per_match',
      'playerDashboard.empty',
    ];
    const zhKeys = new Set(leafKeys(zhTW as Tree));
    const enKeys = new Set(leafKeys(en as Tree));
    for (const key of emitted) {
      expect(zhKeys.has(key), key).toBe(true);
      expect(enKeys.has(key), key).toBe(true);
    }
  });

  it('every error code the sport type endpoints return has a message', () => {
    const codes = [
      'EVENT_KIND_NOT_ALLOWED',
      'NOTHING_TO_UNDO',
      'UNDO_NOT_SUPPORTED',
      'UNDO_CONFLICT',
      'SPORT_TYPE_NOT_SUPPORTED',
      'SCORE_STEP_NOT_ALLOWED',
      'FINISH_NOT_AVAILABLE',
      'DRAW_NOT_ALLOWED',
      'FRAME_SCORING_DISABLED',
      'FRAME_SCORE_FLOOR',
      'MATCH_NOT_IN_PROGRESS',
      'CUSTOM_SPORT_NAME_TAKEN',
      'CUSTOM_SPORT_LIMIT',
      'CUSTOM_SPORT_NOT_FOUND',
      'CUSTOM_SPORT_FORBIDDEN',
      'INVALID_SPORT_FILTER',
      'SPORT_REQUIRED',
    ];
    for (const code of codes) {
      expect(((zhTW as Tree)['errors'] as Tree)[code], code).toBeTruthy();
      expect(((en as Tree)['errors'] as Tree)[code], code).toBeTruthy();
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
