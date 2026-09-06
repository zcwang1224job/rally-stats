// Mirrors AllCourtsBootstrapResponse in apps/api/app/domains/group/schemas.py.

export interface AllCourtsCourtSummary {
  court_id: string;
  name: string;
}

export interface AllCourtsBootstrapResponse {
  group_id: string;
  all_courts_link_version: number;
  group_disbanded: boolean;
  courts: AllCourtsCourtSummary[];
}
