"""index foreign keys

Revision ID: 3912de8ceb6c
Revises: 476c536c7b0f
Create Date: 2026-09-08 23:00:00.000000

Postgres never auto-indexes the referencing side of a foreign key. None of
these columns had one, despite every "this group's roster/matches/courts",
"this member's invites/requests/notifications" query in the app filtering
or joining on them — invisible at this project's current scale, but each
one degrades to a sequential scan as its table grows. Plain (non-unique)
b-tree indexes, named to match what SQLAlchemy's `index=True` column
attribute generates by default (`ix_<table>_<column>`) so a future
`alembic revision --autogenerate` won't see a phantom diff.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3912de8ceb6c'
down_revision: str | None = '476c536c7b0f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: list[tuple[str, str, str]] = [
    ('ix_roster_entries_group_id', 'roster_entries', 'group_id'),
    ('ix_roster_entries_member_id', 'roster_entries', 'member_id'),
    ('ix_matches_group_id', 'matches', 'group_id'),
    ('ix_matches_court_id', 'matches', 'court_id'),
    ('ix_match_participants_match_id', 'match_participants', 'match_id'),
    ('ix_match_participants_roster_entry_id', 'match_participants', 'roster_entry_id'),
    ('ix_partnerships_group_id', 'partnerships', 'group_id'),
    ('ix_group_invites_group_id', 'group_invites', 'group_id'),
    ('ix_group_invites_inviter_member_id', 'group_invites', 'inviter_member_id'),
    ('ix_group_invites_invitee_member_id', 'group_invites', 'invitee_member_id'),
    ('ix_friend_requests_requester_id', 'friend_requests', 'requester_id'),
    ('ix_friend_requests_addressee_id', 'friend_requests', 'addressee_id'),
    ('ix_courts_group_id', 'courts', 'group_id'),
    ('ix_groups_created_by_member_id', 'groups', 'created_by_member_id'),
    ('ix_notifications_member_id', 'notifications', 'member_id'),
    ('ix_email_verification_tokens_member_id', 'email_verification_tokens', 'member_id'),
    ('ix_password_reset_tokens_member_id', 'password_reset_tokens', 'member_id'),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
