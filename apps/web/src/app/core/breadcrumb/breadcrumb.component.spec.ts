import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { BreadcrumbComponent } from './breadcrumb.component';

function setup(routeConfigPath: string | undefined) {
  TestBed.configureTestingModule({
    imports: [BreadcrumbComponent],
    providers: [
      provideRouter([]),
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            firstChild: {
              firstChild: null,
              routeConfig: { path: routeConfigPath },
            },
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(BreadcrumbComponent);
  fixture.detectChanges();
  return fixture;
}

describe('BreadcrumbComponent', () => {
  it('renders every ancestor as a link and the current page as plain aria-current text', () => {
    const fixture = setup('member/settings');

    const links = fixture.nativeElement.querySelectorAll('a');
    const current = fixture.nativeElement.querySelector('[aria-current="page"]');

    expect(links.length).toBe(2);
    expect(links[0].getAttribute('href')).toBe('/');
    expect(links[1].getAttribute('href')).toBe('/member');
    expect(current).not.toBeNull();
    expect(current.tagName).toBe('SPAN');
    expect(fixture.nativeElement.querySelectorAll('li').length).toBe(3);
  });

  it('renders nothing for a route with no entry in BREADCRUMB_MAP (e.g. a navShell:false page)', () => {
    const fixture = setup('scoreboard/:courtToken');

    expect(fixture.nativeElement.querySelector('nav')).toBeNull();
  });

  it('renders nothing for the home route (no ancestor, deliberately absent from the map)', () => {
    const fixture = setup('');

    expect(fixture.nativeElement.querySelector('nav')).toBeNull();
  });
});
