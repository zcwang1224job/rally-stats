import { Component, OnInit, inject, signal } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { AuthService } from '../../features/auth/auth.service';
import { LanguageService } from './language.service';

/** 024-add-english-language FR-003/FR-003a/FR-008: the one reusable
 * switcher — embedded once in the nav shell (covers every route with a nav
 * shell) and once standalone on each of the three nav-shell-less routes
 * (scoreboard, control-panel, all-courts-control-panel), so none of them
 * duplicate this markup or the display-name lookup. Display names come
 * from the `languageNames.*` i18n keys (one per supported language code) —
 * a frontend-only cosmetic map, never a second source of truth for which
 * languages exist (that's `SUPPORTED_LANGUAGES` via `getSupportedLanguages()`). */
@Component({
  selector: 'app-language-switcher',
  imports: [TranslatePipe],
  templateUrl: './language-switcher.component.html',
  styleUrl: './language-switcher.component.scss',
})
export class LanguageSwitcherComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly languageService = inject(LanguageService);

  readonly current = this.languageService.current;
  readonly languages = signal<string[]>([]);

  ngOnInit(): void {
    this.auth.getSupportedLanguages().subscribe({
      next: (response) => this.languages.set(response.languages),
    });
  }

  onChange(language: string): void {
    this.languageService.setLanguage(language);
  }
}
