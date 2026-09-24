import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { RoundWinRatePoint } from '../../core/api/group-member-view.models';
import { RoundTrendChartComponent } from './round-trend-chart.component';

// No translations are loaded, so every string renders as its own i18n key.

function round(round_number: number, wins: number, losses: number): RoundWinRatePoint {
  return { round_number, wins, losses, win_rate: wins / (wins + losses) };
}

function setup(rounds: RoundWinRatePoint[]) {
  TestBed.configureTestingModule({
    imports: [RoundTrendChartComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(RoundTrendChartComponent);
  fixture.componentRef.setInput('rounds', rounds);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('RoundTrendChartComponent', () => {
  it('says there is nothing to draw when there are no rounds', () => {
    const root = setup([]);
    expect(root.textContent).toContain('member.matchHistory.charts.roundTrendEmpty');
    expect(root.querySelector('svg')).toBeNull();
  });

  it('draws one point per round on a fixed 0–100% axis', () => {
    const root = setup([round(1, 1, 1), round(2, 2, 0), round(3, 0, 2)]);
    const coordinates = root
      .querySelector('polyline')!
      .getAttribute('points')!
      .split(' ');
    expect(coordinates.length).toBe(3);
    expect(root.querySelector('.trend__axis--max')?.textContent).toBe('100%');
    expect(root.querySelector('.trend__axis--min')?.textContent).toBe('0%');
  });

  it('lists every round with its win rate and record in the table view', () => {
    const root = setup([round(1, 1, 1), round(2, 2, 0)]);
    const rows = Array.from(root.querySelectorAll('.trend__table tbody tr'));
    expect(rows.length).toBe(2);
    expect(rows[1].textContent).toContain('100%');
    expect(rows[1].textContent).toContain('2/2');
  });
});
