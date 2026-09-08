export interface BreadcrumbCrumb {
  labelKey: string;
  /** Omitted for the trail's last entry — that one is the current page
   * itself (rendered as plain text with `aria-current`, not a link). */
  path?: string;
}

/** Keyed by the matched route's `routeConfig.path` (the exact `path:`
 * string in app.routes.ts) — routes are flat, not nested, so there's no
 * `children` hierarchy Angular can derive a trail from automatically.
 * Routes with `data: { navShell: false }` never reach BreadcrumbComponent
 * (it's gated by the same `showNavShell()` signal as the top bar), so
 * they're intentionally absent here too — as of 2026-09-08 that's only
 * scoreboard/:courtToken, control/:courtToken, and
 * control/all/:allCourtsToken (full-screen courtside/projector displays;
 * every other route now shows the top bar and a trail here). */
export const BREADCRUMB_MAP: Record<string, BreadcrumbCrumb[]> = {
  groups: [{ labelKey: 'nav.home', path: '/' }, { labelKey: 'nav.groups' }],
  'groups/new': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'groupJoin.createGroup' },
  ],
  'groups/reauth': [{ labelKey: 'nav.home', path: '/' }, { labelKey: 'reauth.title' }],
  'groups/:groupId/join': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'breadcrumb.joinGroup' },
  ],
  'join/:token': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'breadcrumb.joinLink' },
  ],
  'guest-access/:token': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'breadcrumb.guestAccess' },
  ],
  'groups/:groupId/admin': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'breadcrumb.groupAdmin' },
  ],
  'groups/:groupId/member-view': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.groups', path: '/groups' },
    { labelKey: 'breadcrumb.groupMemberView' },
  ],
  member: [{ labelKey: 'nav.home', path: '/' }, { labelKey: 'nav.memberHome' }],
  'member/settings': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'member.settingsLink' },
  ],
  'member/match-history': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'nav.matchHistory' },
  ],
  'member/my-groups': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'myGroups.title' },
  ],
  'member/my-groups/:groupId': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'myGroups.title', path: '/member/my-groups' },
    { labelKey: 'breadcrumb.groupHistory' },
  ],
  notifications: [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'notifications.list.title' },
  ],
  'group-invites/:inviteId': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'notifications.list.title', path: '/notifications' },
    { labelKey: 'groupInvite.detailTitle' },
  ],
  friends: [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'friends.listTitle' },
  ],
  'friends/add': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'friends.listTitle', path: '/friends' },
    { labelKey: 'friends.addTitle' },
  ],
  'friends/requests': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'nav.memberHome', path: '/member' },
    { labelKey: 'friends.listTitle', path: '/friends' },
    { labelKey: 'friends.requestsTitle' },
  ],
  'auth/register': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'auth.registerTitle' },
  ],
  'auth/login': [{ labelKey: 'nav.home', path: '/' }, { labelKey: 'auth.loginTitle' }],
  'auth/verify-email/:token': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'auth.loginTitle', path: '/auth/login' },
    { labelKey: 'breadcrumb.verifyEmail' },
  ],
  'auth/forgot-password': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'auth.loginTitle', path: '/auth/login' },
    { labelKey: 'auth.forgotPasswordTitle' },
  ],
  'auth/reset-password/:token': [
    { labelKey: 'nav.home', path: '/' },
    { labelKey: 'auth.loginTitle', path: '/auth/login' },
    { labelKey: 'auth.resetPasswordTitle' },
  ],
};
