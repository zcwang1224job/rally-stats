"""more system_config defaults

Revision ID: 8a1f2c9d4e6b
Revises: f3a1c9d4e7b2
Create Date: 2026-09-11 00:00:00.000000

Seeds additional shared parameters (previously hardcoded module constants)
into system_config, per the same key/value/description shape as
75776930b757's max_group_members/default_timezone rows.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8a1f2c9d4e6b'
down_revision: Union[str, None] = 'f3a1c9d4e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KEYS = (
    "verification_token_ttl_hours",
    "resend_verification_cooldown_minutes",
    "password_reset_token_ttl_hours",
    "default_group_name_suffix",
    "default_court_name",
    "default_page_size",
)


def upgrade() -> None:
    op.execute(
        "INSERT INTO system_config (key, value, description) VALUES "
        "('verification_token_ttl_hours', '24', 'Email 驗證連結有效期限（小時）'), "
        "('resend_verification_cooldown_minutes', '5', '重寄驗證信冷卻時間（分鐘）'), "
        "('password_reset_token_ttl_hours', '1', '忘記密碼重設連結有效期限（小時）'), "
        "('default_group_name_suffix', '的羽球團', '建團未輸入團名時的預設後綴'), "
        "('default_court_name', '球場一', '建團自動建立的預設球場名稱'), "
        "('default_page_size', '20', '列表類 API 的預設分頁筆數') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    keys = ", ".join(f"'{key}'" for key in _KEYS)
    op.execute(f"DELETE FROM system_config WHERE key IN ({keys})")
