import { SportTypeModule } from '../../sport-type-module';
import { FramesCreateFormFieldsComponent } from './frames-create-form-fields.component';
import {
  FrameListSectionComponent,
  FrameTrendSectionComponent,
  FramesDashboardSummarySectionComponent,
} from './frames-sections.component';
import {
  FramesAllCourtsBlockComponent,
  FramesControlPanelComponent,
  FramesCourtControlComponent,
  FramesScoreboardComponent,
} from './frames-surfaces.component';

/**
 * 043 US3: the frames sport type (billiards, darts, board games, esports) —
 * first to N frames, each frame only has a winner, optionally with an
 * in-frame score kept point by point. Loaded as its own chunk.
 */
export const FRAMES: SportTypeModule = {
  typeKey: 'frames',
  surfaces: {
    scoreboard: FramesScoreboardComponent,
    controlPanel: FramesControlPanelComponent,
    allCourtsBlock: FramesAllCourtsBlockComponent,
    courtControl: FramesCourtControlComponent,
    createFormFields: FramesCreateFormFieldsComponent,
  },
  sectionKinds: {
    'frames.frame_list': FrameListSectionComponent,
    'frames.frame_trend': FrameTrendSectionComponent,
    'frames.dashboard_summary': FramesDashboardSummarySectionComponent,
  },
};
