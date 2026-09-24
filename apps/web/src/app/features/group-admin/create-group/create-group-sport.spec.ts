import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { SportsService } from '../../../core/api/sports.service';
import { SportsCatalogResponse } from '../../../core/api/sport.models';
import { AuthService } from '../../auth/auth.service';
import { GroupJoinService } from '../../group-join/group-join.service';
import { GroupAdminService } from '../group-admin.service';
import { CreateGroupComponent } from './create-group.component';

const CATALOG: SportsCatalogResponse = {
  types: [],
  builtin: [
    {
      sport_key: 'badminton',
      type_key: 'net_rally',
      name_key: 'sports.badminton',
      icon: 'shuttle',
      team_size_options: [1, 2],
      defaults: {
        team_size: 1,
        end_mode: 'target',
        target_score: 21,
        win_by: 2,
        cap_score: 30,
        allow_draw: false,
        score_steps: [1],
        type_params: {},
        scoring_mode: '21pt',
      },
      nouns: { venue: 'court', score: 'point', member: 'player' },
    },
    {
      sport_key: 'table_tennis',
      type_key: 'net_rally',
      name_key: 'sports.table_tennis',
      icon: 'paddle',
      team_size_options: [1, 2],
      defaults: {
        team_size: 1,
        end_mode: 'target',
        target_score: 11,
        win_by: 2,
        cap_score: null,
        allow_draw: false,
        score_steps: [1],
        type_params: { modules: { serve_tracking: false, shot_placement: false } },
        scoring_mode: 'custom',
      },
      nouns: { venue: 'table', score: 'point', member: 'player' },
    },
    {
      sport_key: 'billiards',
      type_key: 'frames',
      name_key: 'sports.billiards',
      icon: 'billiards',
      team_size_options: [1],
      defaults: {
        team_size: 1,
        end_mode: 'target',
        target_score: 5,
        win_by: 1,
        cap_score: null,
        allow_draw: false,
        score_steps: [1],
        type_params: {},
        scoring_mode: 'custom',
      },
      nouns: { venue: 'table', score: 'frame', member: 'player' },
    },
    {
      sport_key: 'other',
      type_key: 'generic',
      name_key: 'sports.other',
      icon: 'other',
      team_size_options: [1, 2],
      defaults: {
        team_size: 1,
        end_mode: 'manual',
        target_score: 1,
        win_by: 1,
        cap_score: null,
        allow_draw: true,
        score_steps: [1],
        type_params: {},
        scoring_mode: 'custom',
      },
      nouns: { venue: 'venue', score: 'point', member: 'member' },
    },
  ],
  custom: [],
};

describe('CreateGroupComponent — activity (043)', () => {
  function setup() {
    let payload: Record<string, unknown> | null = null;
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: SportsService, useValue: { getCatalog: () => of(CATALOG) } },
        {
          provide: GroupAdminService,
          useValue: {
            createGroup: (body: Record<string, unknown>) => {
              payload = body;
              return of({ group_id: 'g1', group_number: 1, admin_pin: '1', admin_token: 't', current_member_count: 1, roster_entry_id: 'r', guest_session_token: null });
            },
            setAdminToken: () => undefined,
            setLastCreatedGroupId: () => undefined,
          },
        },
        { provide: AuthService, useValue: { isLoggedIn: () => false } },
        {
          provide: GroupJoinService,
          useValue: {
            getActiveGuestGroupId: () => null,
            setActiveGuestGroupId: () => undefined,
            setGuestSessionToken: () => undefined,
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    component.form.patchValue({ creator_nickname: '小華' });
    component.onTurnstileVerified('tok');
    return { fixture, component, sent: () => payload };
  }

  it('lists the catalogue first, with badminton selected', () => {
    const { fixture } = setup();
    const cards = fixture.nativeElement.querySelectorAll('.activity-card');
    expect(cards.length).toBe(4);
    const selected = fixture.nativeElement.querySelector('[data-sport="badminton"]');
    expect(selected.getAttribute('aria-pressed')).toBe('true');
    expect(fixture.nativeElement.querySelector('[data-section="generic-scoring"]')).toBeNull();
  });

  it('badminton submits exactly as before, plus the sport and team size', () => {
    const { component, sent } = setup();
    component.submit();
    const body = sent()!;
    expect(body['match_mode']).toBe('singles');
    expect(body['scoring_mode']).toBe('21pt');
    expect(body['sport']).toEqual({ sport_key: 'badminton' });
    expect(body['team_size']).toBe(1);
    expect(body['target_score']).toBeUndefined();
  });

  it('table tennis brings in its defaults and sends the common parameters', () => {
    const { fixture, component, sent } = setup();
    component.selectSport('table_tennis');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-section="generic-scoring"]')).not.toBeNull();
    expect(component.form.controls.has_cap.value).toBe(false);
    component.submit();
    const body = sent()!;
    expect(body['sport']).toEqual({ sport_key: 'table_tennis' });
    expect(body['scoring_mode']).toBe('custom');
    expect(body['target_score']).toBe(11);
    expect(body['cap_score']).toBeNull();
    expect(body['win_by']).toBe(2);
    expect(body['score_steps']).toEqual([1]);
  });

  it('billiards offers only one per team', () => {
    const { fixture, component } = setup();
    component.selectSport('billiards');
    fixture.detectChanges();
    const options = fixture.nativeElement.querySelectorAll('select[formcontrolname="match_mode"] option');
    expect(options.length).toBe(1);
    expect(component.form.controls.match_mode.value).toBe('singles');
  });

  it('"other" needs a name, and sends it', () => {
    const { component, sent } = setup();
    component.selectSport('other');
    component.submit();
    expect(sent()).toBeNull();
    component.form.patchValue({ other_name: '趣味賽', score_steps: '1,2' });
    component.submit();
    const body = sent()!;
    expect(body['sport']).toEqual({ sport_key: 'other', name: '趣味賽' });
    expect(body['end_mode']).toBe('manual');
    expect(body['allow_draw']).toBe(true);
    expect(body['score_steps']).toEqual([1, 2]);
  });

  it('invalid common parameters block the submit', () => {
    const { component, sent } = setup();
    component.selectSport('table_tennis');
    component.form.patchValue({ score_steps: '2,1' });
    component.submit();
    expect(sent()).toBeNull();
    expect(component.form.errors?.['genericScoringInvalid']).toBe('score_steps');
  });
});

describe('CreateGroupComponent — my custom activities (043 US4)', () => {
  const MINE = {
    id: 'cs-1',
    name: '躲避球',
    type_key: 'generic' as const,
    team_size_options: [2],
    defaults: {
      team_size: 2,
      end_mode: 'manual' as const,
      target_score: 1,
      win_by: 1,
      cap_score: null,
      allow_draw: true,
      score_steps: [1],
      type_params: {},
    },
    created_at: '2026-09-24T00:00:00Z',
  };

  function memberSetup(loggedIn: boolean) {
    const getCatalog = vi.fn(() => of({ ...CATALOG, custom: loggedIn ? [MINE] : [] }));
    const deleteCustomSport = vi.fn(() => of(undefined));
    TestBed.configureTestingModule({
      imports: [CreateGroupComponent],
      providers: [
        provideRouter([]),
        provideTranslateService({}),
        { provide: SportsService, useValue: { getCatalog, deleteCustomSport } },
        { provide: GroupAdminService, useValue: { setAdminToken: () => undefined } },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => loggedIn,
            getAccessToken: () => 'tok',
            getMe: () => of({ member_id: 'm1', nickname: '小華' }),
          },
        },
        {
          provide: GroupJoinService,
          useValue: {
            getActiveGuestGroupId: () => null,
            setActiveGuestGroupId: () => undefined,
            setGuestSessionToken: () => undefined,
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(CreateGroupComponent);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, getCatalog, deleteCustomSport };
  }

  it('a guest sees no "add custom activity"', () => {
    const { fixture } = memberSetup(false);
    expect(fixture.nativeElement.querySelector('[data-action="add-custom-sport"]')).toBeNull();
  });

  it('a member picks, adds and deletes their own activities', () => {
    const { fixture, component, getCatalog, deleteCustomSport } = memberSetup(true);
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-action="add-custom-sport"]')).not.toBeNull();
    expect(el.querySelector('[data-sport="custom:cs-1"]')).not.toBeNull();

    component.onCustomSportCreated({ ...MINE, id: 'cs-1' });
    expect(getCatalog).toHaveBeenLastCalledWith({ Authorization: 'Bearer tok' }, true);
    expect(component.isSelected('custom:cs-1')).toBe(true);

    component.askDeleteCustomSport(MINE);
    component.confirmDeleteCustomSport();
    expect(deleteCustomSport).toHaveBeenCalledWith('cs-1', { Authorization: 'Bearer tok' });
    // The deleted activity was the one picked: back to badminton.
    expect(component.isSelected('badminton')).toBe(true);
  });
});

