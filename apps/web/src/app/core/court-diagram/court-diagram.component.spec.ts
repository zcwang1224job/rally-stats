import { TestBed } from '@angular/core/testing';
import { CourtDiagramComponent } from './court-diagram.component';

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
