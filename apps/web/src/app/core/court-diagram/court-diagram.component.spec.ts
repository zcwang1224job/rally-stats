import { TestBed } from '@angular/core/testing';
import { CourtDiagramComponent, CourtMarker } from './court-diagram.component';

function setup(isSinglesMatch: boolean, landingX: number | null = null, landingY: number | null = null) {
  TestBed.configureTestingModule({ imports: [CourtDiagramComponent] });
  const fixture = TestBed.createComponent(CourtDiagramComponent);
  fixture.componentRef.setInput('isSinglesMatch', isSinglesMatch);
  fixture.componentRef.setInput('landingX', landingX);
  fixture.componentRef.setInput('landingY', landingY);
  fixture.detectChanges();
  return fixture;
}

describe('CourtDiagramComponent', () => {
  it('renders a landing marker at the given relative position when both coordinates are set', () => {
    const fixture = setup(false, 0.75, 0.25);

    const marker: HTMLElement = fixture.nativeElement.querySelector('.landing-marker');
    expect(marker).not.toBeNull();
    expect(marker.style.left).toBe('75%');
    expect(marker.style.top).toBe('25%');
  });

  it('renders no marker when coordinates are null', () => {
    const fixture = setup(false, null, null);

    expect(fixture.nativeElement.querySelector('.landing-marker')).toBeNull();
  });

  it('renders two out-of-play bands for a singles match', () => {
    const fixture = setup(true);
    expect(fixture.nativeElement.querySelectorAll('.out-of-play-band').length).toBe(2);
  });

  it('renders no out-of-play bands for a doubles match', () => {
    const fixture = setup(false);
    expect(fixture.nativeElement.querySelectorAll('.out-of-play-band').length).toBe(0);
  });
});

describe('CourtDiagramComponent — multiple markers (033)', () => {
  function setupMarkers(markers: CourtMarker[]) {
    const fixture = setup(false);
    fixture.componentRef.setInput('markers', markers);
    fixture.detectChanges();
    return fixture;
  }

  it('renders no distribution marker by default', () => {
    const fixture = setup(false, 0.5, 0.5);

    expect(fixture.nativeElement.querySelectorAll('.court-marker').length).toBe(0);
    // ...and the single landing marker is unaffected by the new input.
    expect(fixture.nativeElement.querySelectorAll('.landing-marker').length).toBe(1);
  });

  it('renders one marker per point, shaped by kind rather than by colour alone', () => {
    const fixture = setupMarkers([
      { x: 0.8, y: 0.2, kind: 'scored' },
      { x: 0.1, y: 0.9, kind: 'lost' },
      { x: 0.7, y: 0.4, kind: 'scored' },
    ]);

    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelectorAll('.court-marker').length).toBe(3);
    expect(root.querySelectorAll('.court-marker--scored').length).toBe(2);
    expect(root.querySelectorAll('.court-marker--lost').length).toBe(1);
    const lost: HTMLElement = root.querySelector('.court-marker--lost')!;
    expect(lost.style.left).toBe('10%');
    expect(lost.style.top).toBe('90%');
  });

  it('keeps an out-of-bounds point outside the box instead of clamping it', () => {
    const fixture = setupMarkers([{ x: 1.04, y: -0.12, kind: 'lost' }]);

    const marker: HTMLElement = fixture.nativeElement.querySelector('.court-marker');
    expect(marker.style.left).toBe('104%');
    expect(marker.style.top).toBe('-12%');
  });

  it('is not dense unless asked, and dense mode keeps both marker shapes (034)', () => {
    const fixture = setupMarkers([
      { x: 0.8, y: 0.2, kind: 'scored' },
      { x: 0.1, y: 0.9, kind: 'lost' },
    ]);
    const host: HTMLElement = fixture.nativeElement;
    expect(host.classList.contains('court--dense')).toBe(false);

    fixture.componentRef.setInput('dense', true);
    fixture.detectChanges();

    expect(host.classList.contains('court--dense')).toBe(true);
    expect(host.querySelectorAll('.court-marker--scored').length).toBe(1);
    expect(host.querySelectorAll('.court-marker--lost').length).toBe(1);
  });
});
