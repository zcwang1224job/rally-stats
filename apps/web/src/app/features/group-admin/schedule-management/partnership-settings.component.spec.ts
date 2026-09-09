import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { ScheduleService } from './schedule.service';
import { PartnershipSettingsComponent } from './partnership-settings.component';
import { PartnershipsResponse, TemporaryPairingsResponse } from './schedule.models';

const EMPTY_PARTNERSHIPS: PartnershipsResponse = {
  partnerships: [
    {
      partnership_id: 'pship-1',
      player_a: { roster_entry_id: 'formal-a', nickname: '正式甲' },
      player_b: { roster_entry_id: 'formal-b', nickname: '正式乙' },
    },
  ],
  unpaired: [
    { roster_entry_id: 'p1', nickname: 'P1' },
    { roster_entry_id: 'p2', nickname: 'P2' },
    { roster_entry_id: 'p3', nickname: 'P3' },
    { roster_entry_id: 'p4', nickname: 'P4' },
  ],
};

const PREVIEW_RESPONSE: TemporaryPairingsResponse = {
  pairings: [
    {
      player_a: { roster_entry_id: 'p1', nickname: 'P1' },
      player_b: { roster_entry_id: 'p2', nickname: 'P2' },
    },
    {
      player_a: { roster_entry_id: 'p3', nickname: 'P3' },
      player_b: { roster_entry_id: 'p4', nickname: 'P4' },
    },
  ],
};

function setup(
  partnerSource: 'manual' | 'auto' = 'manual',
  initial: PartnershipsResponse = EMPTY_PARTNERSHIPS,
) {
  let previewCalls = 0;
  const dissolveCalls: string[] = [];

  TestBed.configureTestingModule({
    imports: [PartnershipSettingsComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: ScheduleService,
        useValue: {
          getPartnerships: () => of(initial),
          previewRandomPairing: () => {
            previewCalls += 1;
            return of(PREVIEW_RESPONSE);
          },
          dissolvePartnership: (_groupId: string, rosterEntryId: string) => {
            dissolveCalls.push(rosterEntryId);
            return of({ partnerships: [], unpaired: initial.partnerships[0]
              ? [initial.partnerships[0].player_a, initial.partnerships[0].player_b]
              : [] } as PartnershipsResponse);
          },
        },
      },
    ],
  });

  const fixture = TestBed.createComponent(PartnershipSettingsComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.componentRef.setInput('partnerSource', partnerSource);
  fixture.detectChanges();
  return {
    fixture,
    component: fixture.componentInstance,
    getPreviewCalls: () => previewCalls,
    getDissolveCalls: () => dissolveCalls,
  };
}

describe('PartnershipSettingsComponent — 017-fixed-partner-autofill', () => {
  it('shows the randomize-remaining button in manual mode with unpaired members', () => {
    const { fixture } = setup('manual');
    const buttons = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as Element[];
    const button = buttons.find((el) => el.textContent?.includes('randomizeRemainingButton'));
    expect(button).toBeTruthy();
  });

  it('hides the randomize-remaining button in auto mode (US3)', () => {
    const { fixture } = setup('auto');
    const buttons = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as Element[];
    const button = buttons.find((el) => el.textContent?.includes('randomizeRemainingButton'));
    expect(button).toBeFalsy();
  });

  it('renders the temporary pairing list with a non-color (icon/text) badge after preview (FR-008)', () => {
    const { fixture, component } = setup('manual');
    component.previewRandomPairing();
    fixture.detectChanges();

    expect(component.temporaryPairs().length).toBe(2);
    const badges = fixture.nativeElement.querySelectorAll('.status-badge--temporary');
    expect(badges.length).toBe(2);
    // The distinguishing signal is baked into the text itself (icon + i18n
    // key), never color alone — constitution principle VII.
    for (const badge of Array.from(badges) as Element[]) {
      expect(badge.textContent?.trim().length).toBeGreaterThan(0);
    }
  });

  it('swapping two temporary-pairing members re-pairs them and emits the updated list (FR-006)', () => {
    const { component } = setup('manual');
    component.previewRandomPairing();

    const emitted: unknown[] = [];
    component.temporaryPairingsChange.subscribe((pairings) => emitted.push(pairings));

    // p1 was originally paired with p2, p3 with p4 — reassign p1+p3.
    component.pickTemporary('p1');
    component.pickTemporary('p3');

    const pairs = component.temporaryPairs();
    const hasNewPair = pairs.some(
      (pair) =>
        new Set([pair.player_a.roster_entry_id, pair.player_b.roster_entry_id]).has('p1') &&
        new Set([pair.player_a.roster_entry_id, pair.player_b.roster_entry_id]).has('p3'),
    );
    expect(hasNewPair).toBe(true);
    // p2 and p4 fall out of a pair — they become "unpaired within this
    // temporary set" and get auto-filled server-side (FR-002), never
    // silently dropped from the visible list.
    const unpairedIds = component.temporaryUnpaired().map((m) => m.roster_entry_id);
    expect(unpairedIds.sort()).toEqual(['p2', 'p4']);
    expect(emitted.length).toBeGreaterThan(0);

    // SC-003: reassigning one pair takes exactly 2 clicks — the same
    // step-count as the existing formal-partnership "點兩人互換" flow.
  });

  it('selecting a formally-paired member id has no effect on the temporary pairing draft (FR-006 scope restriction)', () => {
    const { component } = setup('manual');
    component.previewRandomPairing();
    const before = component.temporaryPairs();

    // 'formal-a' is a formally-paired member, never part of temporaryMembers
    // — pickTemporary() is never wired to their button in the template, but
    // even if invoked directly it must be a no-op (member not found).
    component.pickTemporary('formal-a');
    component.pickTemporary('p1');

    expect(component.temporaryPairs()).toEqual(before);
  });

  it('does not show any temporary pairing UI before preview is triggered', () => {
    const { fixture } = setup('manual');
    expect(fixture.nativeElement.querySelector('.temporary-pairing-list')).toBeNull();
  });

  it('highlights the first-picked formal-partnership member before the second click', () => {
    const { fixture, component } = setup('manual');

    component.pick('formal-a');
    fixture.detectChanges();

    const buttons = Array.from(fixture.nativeElement.querySelectorAll('.pair-list button')) as
      HTMLButtonElement[];
    const selected = buttons.find((el) => el.classList.contains('is-selected'));
    expect(selected?.textContent).toContain('正式甲');
    expect(selected?.getAttribute('aria-pressed')).toBe('true');
  });

  it('dissolves the only remaining pair via the explicit split button (last-two-people edge case)', () => {
    const lastTwo: PartnershipsResponse = {
      partnerships: [
        {
          partnership_id: 'pship-1',
          player_a: { roster_entry_id: 'formal-a', nickname: '正式甲' },
          player_b: { roster_entry_id: 'formal-b', nickname: '正式乙' },
        },
      ],
      unpaired: [],
    };
    const { fixture, getDissolveCalls, component } = setup('manual', lastTwo);

    const dissolveButton = Array.from(
      fixture.nativeElement.querySelectorAll('.btn--dissolve'),
    )[0] as HTMLButtonElement;
    expect(dissolveButton).toBeTruthy();
    dissolveButton.click();
    fixture.detectChanges();

    expect(getDissolveCalls()).toEqual(['formal-a']);
    expect(component.partnerships()?.partnerships).toEqual([]);
    expect(component.partnerships()?.unpaired.length).toBe(2);
  });
});
