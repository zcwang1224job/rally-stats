import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import en from '../../../assets/i18n/en.json';
import zhTW from '../../../assets/i18n/zh-TW.json';
import { AuthService } from '../auth/auth.service';
import { HomeComponent } from './home.component';

/** 041-group-share-cards US4: where a share card's QR code lands. */
async function setup(loggedIn: boolean, url = '/') {
  TestBed.configureTestingModule({
    providers: [
      provideTranslateService({}),
      provideRouter([{ path: '', component: HomeComponent }]),
      { provide: AuthService, useValue: { loggedIn: signal(loggedIn) } },
    ],
  });
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl(url, HomeComponent);
  harness.detectChanges();
  return { harness, root: harness.routeNativeElement as HTMLElement };
}

function links(root: HTMLElement): { href: string | null; text: string }[] {
  return Array.from(root.querySelectorAll('a')).map((a) => ({
    href: a.getAttribute('href'),
    text: a.textContent?.trim() ?? '',
  }));
}

describe('HomeComponent — what it says (041 US4, FR-024)', () => {
  it('shows the name, the same tagline as the cards, and three features', async () => {
    const { root } = await setup(false);

    expect(root.querySelector('h1')?.textContent).toContain('home.title');
    expect(root.textContent).toContain('shareCard.tagline');
    const features = root.querySelectorAll('.home__feature');
    expect(features.length).toBe(3);
    for (const feature of Array.from(features)) {
      expect(feature.querySelector('h2')?.textContent?.trim()).toMatch(/^home\.features\.\w+\.title$/);
      expect(feature.querySelector('p')?.textContent?.trim()).toMatch(/^home\.features\.\w+\.body$/);
    }
  });

  it('switches its words with the language', async () => {
    const { harness, root } = await setup(false);
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.setTranslation('zh-TW', zhTW);

    translate.use('en');
    harness.detectChanges();
    expect(root.textContent).toContain(en.shareCard.tagline);

    translate.use('zh-TW');
    harness.detectChanges();
    expect(root.textContent).toContain(zhTW.shareCard.tagline);
  });
});

describe('HomeComponent — where it leads (041 FR-024, FR-026)', () => {
  it('offers sign-up first and log-in second to a visitor', async () => {
    const { root } = await setup(false);

    expect(links(root)).toEqual([
      { href: '/auth/register', text: 'home.cta.start' },
      { href: '/auth/login', text: 'home.cta.login' },
    ]);
  });

  it('offers a member their own page, without sending them anywhere by itself', async () => {
    const navigate = vi.spyOn(Router.prototype, 'navigate');
    const navigateByUrl = vi.spyOn(Router.prototype, 'navigateByUrl');
    const { root } = await setup(true);
    const initialNavigations = navigateByUrl.mock.calls.length;

    expect(links(root)).toEqual([{ href: '/member', text: 'home.cta.member' }]);
    expect(navigate).not.toHaveBeenCalled();
    // Only the test's own navigation to "/" — the page adds none.
    expect(navigateByUrl.mock.calls.length).toBe(initialNavigations);
    navigate.mockRestore();
    navigateByUrl.mockRestore();
  });
});

describe('HomeComponent — the card’s ref parameter (041 FR-025)', () => {
  it('looks exactly the same with or without it, and never shows it', async () => {
    const plain = (await setup(false)).root.textContent;
    TestBed.resetTestingModule();

    for (const url of ['/?ref=card-rank', '/?ref=%3Cscript%3E', '/?foo=bar']) {
      const { root } = await setup(false, url);
      expect(root.textContent, url).toBe(plain);
      expect(root.textContent).not.toMatch(/card-rank|script|foo/);
      TestBed.resetTestingModule();
    }
  });
});

describe('home language keys (041 FR-030)', () => {
  interface Tree {
    [key: string]: string | Tree;
  }
  function leaves(tree: Tree, prefix = ''): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(tree)) {
      const path = prefix ? `${prefix}.${key}` : key;
      Object.assign(out, typeof value === 'string' ? { [path]: value } : leaves(value, path));
    }
    return out;
  }

  it('has the same, non-empty keys in zh-TW and en', () => {
    const zh = leaves((zhTW as unknown as { home: Tree }).home);
    const eng = leaves((en as unknown as { home: Tree }).home);

    expect(Object.keys(eng).sort()).toEqual(Object.keys(zh).sort());
    for (const value of [...Object.values(zh), ...Object.values(eng)]) {
      expect(value.trim().length).toBeGreaterThan(0);
    }
  });
});
