import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { AuthService } from '../../features/auth/auth.service';
import { LanguageSwitcherComponent } from './language-switcher.component';
import { LanguageService } from './language.service';

function setup(options: { languages?: string[]; current?: string } = {}) {
  const authServiceStub = {
    getSupportedLanguages: () => of({ languages: options.languages ?? ['zh-TW', 'en'] }),
  };
  const setLanguageCalls: string[] = [];
  const languageServiceStub = {
    current: () => options.current ?? 'zh-TW',
    setLanguage: (language: string) => setLanguageCalls.push(language),
  };

  TestBed.configureTestingModule({
    imports: [LanguageSwitcherComponent],
    providers: [
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
      { provide: LanguageService, useValue: languageServiceStub },
    ],
  });

  const fixture = TestBed.createComponent(LanguageSwitcherComponent);
  fixture.detectChanges();
  return { fixture, setLanguageCalls };
}

describe('LanguageSwitcherComponent', () => {
  it('renders one option per supported language with that language\'s own display-name key (FR-008)', () => {
    const { fixture } = setup({ languages: ['zh-TW', 'en'] });

    const options = Array.from<HTMLOptionElement>(
      fixture.nativeElement.querySelectorAll('option'),
    );
    expect(options.length).toBe(2);
    // No real translations are loaded under provideTranslateService({}), so
    // the `| translate` pipe echoes the raw key — asserting on the key
    // itself is how this repo's tests verify each option uses a DIFFERENT
    // key (not the same hardcoded label for every iteration).
    expect(options[0].textContent).toContain('languageNames.zh-TW');
    expect(options[1].textContent).toContain('languageNames.en');
    expect(options[0].textContent).not.toBe(options[1].textContent);
  });

  it('reflects the current language as the selected value', () => {
    const { fixture } = setup({ current: 'en' });

    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    expect(select.value).toBe('en');
  });

  it('calls LanguageService.setLanguage() when a different option is selected', () => {
    const { fixture, setLanguageCalls } = setup({ languages: ['zh-TW', 'en'], current: 'zh-TW' });

    const select = fixture.nativeElement.querySelector('select') as HTMLSelectElement;
    select.value = 'en';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(setLanguageCalls).toEqual(['en']);
  });
});
