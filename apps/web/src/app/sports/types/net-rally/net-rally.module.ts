import { AllCourtsCourtBlockComponent } from '../../../features/control-panel/all-courts/all-courts-court-block.component';
import { ControlPanelComponent } from '../../../features/control-panel/control-panel.component';
import { CourtControlComponent } from '../../../features/group-admin/schedule-management/court-control.component';
import { ScoreboardComponent } from '../../../features/scoreboard/scoreboard.component';
import { SportTypeModule } from '../../sport-type-module';

/**
 * 043: the net rally sport type (badminton, table tennis, pickleball, tennis
 * tie-break). Its surfaces are the scoring screens badminton has always
 * used — they stay where they are and this module points at them (plugin →
 * core is the allowed direction), so every existing spec keeps testing them
 * unchanged. They already hide serve stations and the shot-placement picker
 * when a match has no serve state / detailed scoring.
 *
 * Its detail-page and dashboard sections (`net_rally.match_detail`,
 * `net_rally.dashboard`) are the existing match-record dialog body and
 * player dashboard, which render them from the response's top-level fields.
 */
export const NET_RALLY: SportTypeModule = {
  typeKey: 'net_rally',
  surfaces: {
    scoreboard: ScoreboardComponent,
    controlPanel: ControlPanelComponent,
    allCourtsBlock: AllCourtsCourtBlockComponent,
    courtControl: CourtControlComponent,
    createFormFields: null,
  },
  sectionKinds: {},
};
