// 043-sport-type-plugin-foundation: mirrors app/sports/presentation.py and
// contracts/sports-api.md / contracts/sections-manifest.md.

export type { Section } from '../../sports/sport-type-module';

export type SportTypeKey = 'net_rally' | 'frames' | 'generic';
export type EndMode = 'target' | 'manual';
export type VenueNoun = 'court' | 'table' | 'board' | 'arena' | 'station' | 'venue';
export type ScoreNoun = 'point' | 'frame' | 'score';
export type MemberNoun = 'player' | 'member' | 'competitor';

export interface SportNouns {
  venue: VenueNoun;
  score: ScoreNoun;
  member: MemberNoun;
}

/** What every group / match response says about its activity. Built-ins
 * carry `name_key` (an i18n key); custom and "other" activities carry the
 * user's own `name` instead. */
export interface SportSummary {
  sport_key: string;
  type_key: SportTypeKey;
  name_key: string | null;
  name: string | null;
  icon: string;
  nouns: SportNouns;
}

/** An activity's default common parameters (+ type-specific `type_params`). */
export interface SportDefaults {
  team_size: number;
  end_mode: EndMode;
  target_score: number;
  win_by: number;
  cap_score: number | null;
  allow_draw: boolean;
  score_steps: number[];
  type_params: Record<string, unknown>;
  scoring_mode?: string;
}

export interface SportType {
  type_key: SportTypeKey;
  team_size_range: [number, number];
  modules: string[];
  params_schema: Record<string, unknown>;
  section_kinds: string[];
}

export interface BuiltinSport {
  sport_key: string;
  type_key: SportTypeKey;
  name_key: string;
  icon: string;
  team_size_options: number[];
  defaults: SportDefaults;
  nouns: SportNouns;
}

export interface CustomSport {
  id: string;
  name: string;
  type_key: SportTypeKey;
  team_size_options: number[];
  defaults: SportDefaults & { nouns?: SportNouns };
  created_at: string;
}

export interface SportsCatalogResponse {
  types: SportType[];
  builtin: BuiltinSport[];
  custom: CustomSport[];
}

/** One activity a member has match records for (a dashboard tab). */
export interface ActivitySummary {
  sport: SportSummary;
  /** Ready to pass back as the `sport` query parameter. */
  filter_value: string;
  match_count: number;
}

/** 043 US6: the built-in activities, in catalogue order ("other" last) —
 * the list filters offer each, plus "custom or other". */
export const BUILTIN_SPORT_KEYS = [
  'badminton',
  'table_tennis',
  'pickleball',
  'tennis_tiebreak',
  'billiards',
  'darts',
  'board_game',
  'esports',
  'other',
] as const;

/** The `sport` filter value covering every custom and "other" activity. */
export const CUSTOM_OR_OTHER = 'custom_or_other';

/** The translation key (built-in) or the typed name (custom / other) of an
 * activity — pass the key through the translate pipe. */
export function sportLabel(sport: SportSummary): { key: string | null; name: string | null } {
  return { key: sport.name ? null : sport.name_key, name: sport.name };
}
