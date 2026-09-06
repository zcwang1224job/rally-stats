import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { AuthService } from '../auth/auth.service';
import { GroupAdminService } from '../group-admin/group-admin.service';

@Component({
  selector: 'app-home',
  imports: [RouterLink, TranslatePipe],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
})
export class HomeComponent {
  private readonly auth = inject(AuthService);
  private readonly groupAdmin = inject(GroupAdminService);
  readonly loggedIn = this.auth.loggedIn;
  // Guest-only shortcut (create-group.component.ts only sets this for an
  // anonymous creation, never a logged-in member's — they get 我的團
  // instead, FR-017) straight back to that specific group's admin page,
  // skipping the manual group-number+PIN reauth entirely.
  readonly lastCreatedGroupId = this.groupAdmin.getLastCreatedGroupId();
}
