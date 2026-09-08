import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  it('renders the title, with no navigation content — cleared pending a redesign', () => {
    TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [provideTranslateService({})],
    });
    const fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('h1')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('a').length).toBe(0);
  });
});
