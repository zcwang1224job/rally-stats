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
}
