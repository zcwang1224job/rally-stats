import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { MatchupRecord } from '../api/group-member-view.models';
import { MatchupRecordsComponent } from './matchup-records.component';

// No translations are loaded, so every string renders as its own i18n key.

function matchupFixture(overrides: Partial<MatchupRecord> = {}): MatchupRecord {
  return {
    player_key: 'm:1',
    member_id: '1',
    nickname: '阿哲',
    matches: 10,
    wins: 6,
    losses: 4,
    win_rate: 0.6,
    avg_margin: 2.5,
    low_sample: false,
    ...overrides,
  };
}

const ROWS: MatchupRecord[] = [
  matchupFixture({ player_key: 'm:often', nickname: '常客', matches: 12, wins: 6, losses: 6, win_rate: 0.5, avg_margin: -1.2 }),
  matchupFixture({ player_key: 'm:good', nickname: '好搭', matches: 8, wins: 7, losses: 1, win_rate: 0.875, avg_margin: 0.4 }),
  matchupFixture({ player_key: 'r:new', member_id: null, nickname: '路人', matches: 2, wins: 0, losses: 2, win_rate: 0, avg_margin: 6, low_sample: true }),
];

function setup(inputs: Record<string, unknown>): ComponentFixture<MatchupRecordsComponent> {
  TestBed.configureTestingModule({
    imports: [MatchupRecordsComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(MatchupRecordsComponent);
  for (const [name, value] of Object.entries({ role: 'partner', records: ROWS, ...inputs })) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function order(root: HTMLElement): string[] {
  return Array.from(root.querySelectorAll<HTMLElement>('.matchups__item')).map(
    (row) => row.dataset['player']!,
  );
}

function text(node: Element | null): string {
  return node?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('MatchupRecordsComponent — rows (US2)', () => {
  it('lists each player with record, win rate and a signed average margin', () => {
    const root: HTMLElement = setup({}).nativeElement;
    const first = root.querySelector('[data-player="m:often"]')!;

    expect(text(root.querySelector('summary'))).toBe('member.matchHistory.matchups.partnerTitle');
    expect(text(first.querySelector('[data-rate]'))).toBe('50%');
    expect(text(first.querySelector('[data-margin]'))).toBe('member.matchHistory.matchups.margin −1.2');
    expect(text(root.querySelector('[data-player="m:good"] [data-margin]'))).toContain('+0.4');
  });

  it('is open by default, as the ranking it replaces always was', () => {
    const root: HTMLElement = setup({}).nativeElement;
    expect(root.querySelector<HTMLDetailsElement>('details')!.open).toBe(true);
  });

  it('flags a player with few matches but still lists them (FR-024)', () => {
    const root: HTMLElement = setup({}).nativeElement;
    expect(root.querySelector('[data-player="r:new"] [data-low-sample]')).not.toBeNull();
    expect(root.querySelector('[data-player="m:often"] [data-low-sample]')).toBeNull();
  });

  it('gives every row an anchor that is unique even when a player is in both tables', () => {
    const partner: HTMLElement = setup({}).nativeElement;
    expect(partner.querySelector('#matchup-partner-m\\:often')).not.toBeNull();
    TestBed.resetTestingModule();
    const opponent: HTMLElement = setup({ role: 'opponent' }).nativeElement;
    expect(opponent.querySelector('#matchup-opponent-m\\:often')).not.toBeNull();
    expect(text(opponent.querySelector('summary'))).toBe('member.matchHistory.matchups.opponentTitle');
  });
});

describe('MatchupRecordsComponent — sorting is presentation only', () => {
  it('keeps the order it was given by default, and re-sorts on request', () => {
    const fixture = setup({});
    const root: HTMLElement = fixture.nativeElement;
    expect(order(root)).toEqual(['m:often', 'm:good', 'r:new']);

    root.querySelector<HTMLButtonElement>('[data-sort="win_rate"]')!.click();
    fixture.detectChanges();
    expect(order(root)).toEqual(['m:good', 'm:often', 'r:new']);
    expect(root.querySelector('[data-sort="win_rate"]')!.getAttribute('aria-pressed')).toBe('true');
    expect(root.querySelector('[data-sort="matches"]')!.getAttribute('aria-pressed')).toBe('false');

    root.querySelector<HTMLButtonElement>('[data-sort="avg_margin"]')!.click();
    fixture.detectChanges();
    expect(order(root)).toEqual(['r:new', 'm:good', 'm:often']);
  });

  it('never changes who is highlighted', () => {
    const fixture = setup({ mostPlayedKey: 'm:often', standoutKey: 'm:good' });
    const root: HTMLElement = fixture.nativeElement;
    const before = text(root.querySelector('[data-highlights]'));

    root.querySelector<HTMLButtonElement>('[data-sort="avg_margin"]')!.click();
    fixture.detectChanges();

    expect(text(root.querySelector('[data-highlights]'))).toBe(before);
  });
});

describe('MatchupRecordsComponent — highlights come from the backend', () => {
  it('names the players whose keys it was given', () => {
    const root: HTMLElement = setup({ mostPlayedKey: 'm:often', standoutKey: 'm:good' }).nativeElement;
    const items = Array.from(root.querySelectorAll('[data-highlights] li')).map(text);
    expect(items[0]).toContain('member.matchHistory.matchups.highlights.partnerMost');
    expect(items[0]).toContain('常客');
    expect(items[1]).toContain('member.matchHistory.matchups.highlights.partnerStandout');
    expect(items[1]).toContain('好搭');
  });

  it('shows no highlight block when nobody qualified', () => {
    const root: HTMLElement = setup({}).nativeElement;
    expect(root.querySelector('[data-highlights]')).toBeNull();
  });
});

describe('MatchupRecordsComponent — clickable or not', () => {
  it('makes each row a button and emits the record on the member\'s own page', () => {
    const fixture = setup({});
    const picked: MatchupRecord[] = [];
    fixture.componentInstance.picked.subscribe((record) => picked.push(record));

    const button = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[data-player="m:good"] button',
    )!;
    expect(button.getAttribute('type')).toBe('button');
    button.click();

    expect(picked.map((record) => record.player_key)).toEqual(['m:good']);
  });

  it('renders plain rows on a friend\'s page (FR-037)', () => {
    const root: HTMLElement = setup({ clickable: false }).nativeElement;
    expect(root.querySelector('.matchups__item button')).toBeNull();
    expect(root.querySelectorAll('.matchups__item .matchup').length).toBe(3);
  });
});

describe('MatchupRecordsComponent — nothing to list', () => {
  it('explains instead of showing an empty table (FR-026)', () => {
    const root: HTMLElement = setup({
      records: [],
      emptyKey: 'member.matchHistory.matchups.noDoubles',
    }).nativeElement;
    expect(text(root.querySelector('[data-empty]'))).toBe('member.matchHistory.matchups.noDoubles');
    expect(root.querySelector('.matchups__list')).toBeNull();
    expect(root.querySelector('.matchups__sort')).toBeNull();
  });
});

// A host page can run its sections as an accordion; anywhere else (a
// friend's records) the table starts open as before.
describe('MatchupRecordsComponent — open state', () => {
  it('starts open by default', () => {
    const fixture = setup({});
    expect((fixture.nativeElement as HTMLElement).querySelector('details')!.open).toBe(true);
  });

  it('follows the `open` input and reports the reader\'s own toggles', () => {
    const fixture = setup({ open: false });
    const details = (fixture.nativeElement as HTMLElement).querySelector('details')!;
    const changes: boolean[] = [];
    fixture.componentInstance.openChange.subscribe((open) => changes.push(open));
    expect(details.open).toBe(false);

    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    expect(details.open).toBe(true);

    details.open = false;
    details.dispatchEvent(new Event('toggle'));
    expect(changes).toEqual([false]);
  });
});
