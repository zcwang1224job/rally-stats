// Mirrors CourtByTokenResponse in apps/api/app/domains/court/schemas.py.

export type CourtLinkType = 'scoreboard' | 'control_panel';

export interface CourtByTokenResponse {
  court_id: string;
  group_id: string;
  name: string;
  link_type: CourtLinkType;
  link_version: number;
  deleted: boolean;
  group_disbanded: boolean;
  // The group creator's display language ("zh-TW" if the group has no
  // creator on record) — scoreboard/control-panel have no login and so no
  // language switcher of their own; they apply this instead.
  owner_language: string;
}
