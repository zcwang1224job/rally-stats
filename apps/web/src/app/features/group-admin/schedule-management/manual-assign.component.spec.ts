import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { ManualAssignComponent } from './manual-assign.component';
import { RosterScheduleStatus } from './schedule.models';
import { ScheduleService } from './schedule.service';

// No translations are loaded, so every string renders as its own i18n key.

function row(id: string, overrides: Partial<RosterScheduleStatus> = {}): RosterScheduleStatus {
  return {
    roster_entry_id: id,
    nickname: id.toUpperCase(),
    status: 'active',
    wait_count: 0,
    currently_playing: false,
    is_creator: false,
    is_guest: true,
    ...overrides,
  };
}

function setup(roster: RosterScheduleStatus[], manualAssign = () => of({})) {
  TestBed.configureTestingModule({
    imports: [ManualAssignComponent],
    providers: [
      provideTranslateService({}),
      { provide: ScheduleService, useValue: { manualAssign } },
    ],
  });
  const fixture = TestBed.createComponent(ManualAssignComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.componentRef.setInput('courtId', 'c1');
  fixture.componentRef.setInput('matchMode', 'singles');
  fixture.componentRef.setInput('roster', roster);
  fixture.detectChanges();
  return fixture;
}

describe('ManualAssignComponent', () => {
  it('leaves out players on another court', () => {
    const fixture = setup([row('a'), row('b', { currently_playing: true })]);

    expect(fixture.nativeElement.querySelectorAll('.roster-picker li').length).toBe(1);
  });

  // 037-rest-ready-toggle FR-029
  it('marks a resting player but still lists them', () => {
    const fixture = setup([row('a', { resting: true }), row('b')]);

    const items = fixture.nativeElement.querySelectorAll('.roster-picker li');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('scheduleManagement.restingSuffix');
    expect(items[1].textContent).not.toContain('scheduleManagement.restingSuffix');
  });

  it('lets the admin put a resting player on court', () => {
    const sent: unknown[][] = [];
    const fixture = setup([row('a', { resting: true }), row('b')], ((...args: unknown[]) => {
      sent.push(args);
      return of({});
    }) as never);
    const items = fixture.nativeElement.querySelectorAll('.roster-picker li');

    (items[0].querySelectorAll('button')[0] as HTMLButtonElement).click();
    (items[1].querySelectorAll('button')[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('.manual-assign > .btn') as HTMLButtonElement).click();

    expect(sent).toEqual([['g1', 'c1', ['a', 'b'], { a: 'A', b: 'B' }]]);
  });
});
