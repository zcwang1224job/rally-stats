import { Routes } from '@angular/router';

// 6 lazy-loaded feature route groups per specs/architecture.md §4
// (首頁/開團與管理/嘎團/會員/計分板/控制板). Only group-admin (001) has real
// feature components so far; the rest are placeholders until their specs land.
export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/home/home.component').then((m) => m.HomeComponent),
  },
  {
    path: 'groups/new',
    loadComponent: () =>
      import('./features/group-admin/create-group/create-group.component').then(
        (m) => m.CreateGroupComponent,
      ),
    data: { navShell: false },
  },
  {
    path: 'groups/reauth',
    loadComponent: () =>
      import('./features/group-admin/reauth/reauth.component').then((m) => m.ReauthComponent),
    data: { navShell: false },
  },
  {
    path: 'groups/:groupId/admin',
    loadComponent: () =>
      import('./features/group-admin/admin-page/admin-page.component').then(
        (m) => m.AdminPageComponent,
      ),
  },
  {
    path: 'groups',
    loadComponent: () =>
      import('./features/group-join/group-list/group-list.component').then(
        (m) => m.GroupListComponent,
      ),
  },
  {
    path: 'groups/:groupId/join',
    loadComponent: () =>
      import('./features/group-join/join-flow/join-flow.component').then(
        (m) => m.JoinFlowComponent,
      ),
    data: { navShell: false },
  },
  {
    path: 'join/:token',
    loadComponent: () =>
      import('./features/group-join/group-join.component').then((m) => m.GroupJoinComponent),
    data: { navShell: false },
  },
  {
    path: 'groups/:groupId/member-view',
    loadComponent: () =>
      import('./features/group-member-view/group-member-view.component').then(
        (m) => m.GroupMemberViewComponent,
      ),
  },
  {
    path: 'member',
    loadComponent: () =>
      import('./features/member/member.component').then((m) => m.MemberComponent),
  },
  {
    path: 'member/settings',
    loadComponent: () =>
      import('./features/member/settings/settings.component').then((m) => m.SettingsComponent),
  },
  {
    path: 'member/match-history',
    loadComponent: () =>
      import('./features/member/match-history/match-history.component').then(
        (m) => m.MatchHistoryComponent,
      ),
  },
  {
    path: 'member/my-groups',
    loadComponent: () =>
      import('./features/member/my-groups/my-groups.component').then(
        (m) => m.MyGroupsComponent,
      ),
  },
  {
    path: 'member/my-groups/:groupId',
    loadComponent: () =>
      import('./features/member/my-groups/group-history/group-history.component').then(
        (m) => m.GroupHistoryComponent,
      ),
  },
  {
    path: 'notifications',
    loadComponent: () =>
      import('./features/notifications/notification-list/notification-list.component').then(
        (m) => m.NotificationListComponent,
      ),
  },
  {
    path: 'group-invites/:inviteId',
    loadComponent: () =>
      import('./features/group-invites/group-invite-detail/group-invite-detail.component').then(
        (m) => m.GroupInviteDetailComponent,
      ),
  },
  {
    path: 'friends',
    loadComponent: () =>
      import('./features/friends/friend-list/friend-list.component').then(
        (m) => m.FriendListComponent,
      ),
  },
  {
    path: 'friends/add',
    loadComponent: () =>
      import('./features/friends/friend-add/friend-add.component').then(
        (m) => m.FriendAddComponent,
      ),
  },
  {
    path: 'friends/requests',
    loadComponent: () =>
      import('./features/friends/friend-requests/friend-requests.component').then(
        (m) => m.FriendRequestsComponent,
      ),
  },
  {
    path: 'auth/register',
    loadComponent: () =>
      import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'auth/login',
    loadComponent: () =>
      import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'auth/verify-email/:token',
    loadComponent: () =>
      import('./features/auth/verify-email/verify-email.component').then(
        (m) => m.VerifyEmailComponent,
      ),
  },
  {
    path: 'auth/forgot-password',
    loadComponent: () =>
      import('./features/auth/forgot-password/forgot-password.component').then(
        (m) => m.ForgotPasswordComponent,
      ),
  },
  {
    path: 'auth/reset-password/:token',
    loadComponent: () =>
      import('./features/auth/reset-password/reset-password.component').then(
        (m) => m.ResetPasswordComponent,
      ),
  },
  {
    path: 'scoreboard/:courtToken',
    loadComponent: () =>
      import('./features/scoreboard/scoreboard.component').then((m) => m.ScoreboardComponent),
    data: { navShell: false },
  },
  {
    path: 'control/all/:allCourtsToken',
    loadComponent: () =>
      import('./features/control-panel/all-courts/all-courts-control-panel.component').then(
        (m) => m.AllCourtsControlPanelComponent,
      ),
    data: { navShell: false },
  },
  {
    path: 'control/:courtToken',
    loadComponent: () =>
      import('./features/control-panel/control-panel.component').then(
        (m) => m.ControlPanelComponent,
      ),
    data: { navShell: false },
  },
  { path: '**', redirectTo: '' },
];
