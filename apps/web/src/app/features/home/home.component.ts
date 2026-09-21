import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { IconComponent, IconName } from '../../shared/icon/icon.component';
import { AuthService } from '../auth/auth.service';

interface Feature {
  key: 'scoring' | 'rotation' | 'stats';
  icon: IconName;
}

/** 041-group-share-cards US4: where a share card's QR code lands — what
 * the app is, and a clear way in. The card's `?ref=` parameter is left
 * alone: it is only there for server logs, so this page never reads it
 * (FR-025) and looks the same with or without it. It never redirects a
 * signed-in member either; it just points them to their own page (FR-026). */
@Component({
  selector: 'app-home',
  imports: [TranslatePipe, RouterLink, IconComponent],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  readonly loggedIn = inject(AuthService).loggedIn;

  readonly features: readonly Feature[] = [
    { key: 'scoring', icon: 'monitor' },
    { key: 'rotation', icon: 'swap' },
    { key: 'stats', icon: 'user' },
  ];
}
