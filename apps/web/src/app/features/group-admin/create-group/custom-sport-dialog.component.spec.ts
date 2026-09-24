import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { SportsService } from '../../../core/api/sports.service';
import { CustomSportDialogComponent } from './custom-sport-dialog.component';

function setup(create = vi.fn((body: unknown) => of({ id: 'cs-1', ...(body as object) }))) {
  TestBed.configureTestingModule({
    providers: [
      provideTranslateService({}),
      { provide: SportsService, useValue: { createCustomSport: create } },
    ],
  });
  const fixture = TestBed.createComponent(CustomSportDialogComponent);
  fixture.componentRef.setInput('headers', { Authorization: 'Bearer t' });
  fixture.detectChanges();
  return { fixture, component: fixture.componentInstance, create };
}

describe('CustomSportDialogComponent (043 US4)', () => {
  it('builds the request from the form: sizes, common rules and nouns', () => {
    const { component } = setup();
    component.form.patchValue({
      name: ' 躲避球 ',
      type_key: 'generic',
      singles: false,
      doubles: true,
      end_mode: 'manual',
      target_score: 1,
      allow_draw: true,
      score_steps: '1, 2',
      venue_noun: 'arena',
    });
    expect(component.body()).toEqual({
      name: '躲避球',
      type_key: 'generic',
      team_size_options: [2],
      defaults: {
        team_size: 2,
        end_mode: 'manual',
        target_score: 1,
        win_by: 1,
        cap_score: null,
        allow_draw: true,
        score_steps: [1, 2],
        type_params: {},
        nouns: { venue: 'arena', score: 'point', member: 'player' },
      },
    });
  });

  it('target mode never sends a draw, and keeps the lead and cap', () => {
    const { component } = setup();
    component.form.patchValue({ name: 'x', end_mode: 'target', target_score: 11, win_by: 2, cap_score: 15, allow_draw: true });
    const body = component.body();
    expect(typeof body).toBe('object');
    expect(body).toMatchObject({ defaults: { end_mode: 'target', win_by: 2, cap_score: 15, allow_draw: false } });
  });

  it('refuses no team size or bad steps before sending anything', () => {
    const { component, create } = setup();
    component.form.patchValue({ name: 'x', singles: false, doubles: false });
    expect(component.body()).toBe('createGroup.customSport.teamSizesRequired');
    component.form.patchValue({ singles: true, score_steps: '2,1' });
    expect(component.body()).toBe('createGroup.generic.invalid.score_steps');
    component.save();
    expect(create).not.toHaveBeenCalled();
  });

  it('saves with the member header and hands back the new activity', () => {
    const { component, create } = setup();
    let created: unknown = null;
    component.created.subscribe((sport) => (created = sport));
    component.form.patchValue({ name: '躲避球' });
    component.save();
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: '躲避球' }), {
      Authorization: 'Bearer t',
    });
    expect(created).toMatchObject({ id: 'cs-1', name: '躲避球' });
  });

  it('shows the server refusal (same name, limit)', () => {
    const { fixture, component } = setup(
      vi.fn(() => throwError(() => ({ i18nKey: 'errors.CUSTOM_SPORT_NAME_TAKEN' }))),
    );
    component.form.patchValue({ name: '躲避球' });
    component.save();
    fixture.detectChanges();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[data-testid="custom-sport-error"]')?.textContent,
    ).toContain('errors.CUSTOM_SPORT_NAME_TAKEN');
  });
});
