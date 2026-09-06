// Mirrors apps/api/app/domains/court/schemas.py — see contracts/courts-api.md.

export interface Court {
  court_id: string;
  name: string;
  scoreboard_token: string;
  control_panel_token: string;
  scoreboard_link_version: number;
  control_panel_link_version: number;
  created_at: string;
}

export interface CourtListResponse {
  courts: Court[];
  active_court_count: number;
}

export interface DeleteCourtResponse {
  court_id: string;
  deleted: boolean;
  had_active_match: boolean;
}

export interface RegenerateScoreboardLinkResponse {
  scoreboard_token: string;
  scoreboard_link_version: number;
}

export interface RegenerateControlPanelLinkResponse {
  control_panel_token: string;
  control_panel_link_version: number;
}
