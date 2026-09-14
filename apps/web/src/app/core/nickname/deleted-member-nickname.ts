/** 025-delete-account: mirrors the backend's
 * `DELETED_MEMBER_PLACEHOLDER_NICKNAME` constant (apps/api/app/domains/
 * member/service.py) — a fixed, language-neutral literal, not an i18n key
 * (see that constant's docstring for why: nicknames are user-generated
 * data, not UI chrome). Used by `NicknameComponent` to visually flag a
 * deleted account's placeholder wherever a nickname is rendered. */
export const DELETED_MEMBER_PLACEHOLDER_NICKNAME = 'Deleted User';
