"""Outbound email — the ONLY place the backend sends mail.

Two backends, selected by `settings.email_backend`: `SesEmailSender` (Amazon
SES, production) and `LoggingEmailSender` (writes to the application log,
local/test default). Send failures are logged and MUST NOT fail the caller's
request — the triggering action (registration, forgot-password) has already
succeeded via its own DB transaction; email delivery is best-effort, exactly
like Ably's `publish()` (see app/core/realtime.py). Recovery paths already
exist for the user (resend verification, re-trigger forgot-password).
"""

import logging
from typing import Protocol

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send_email(self, to: str, subject: str, body: str) -> None: ...


class SesEmailSender:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client("ses", region_name=settings.ses_region)
        self._from_address = settings.ses_from_address

    async def send_email(self, to: str, subject: str, body: str) -> None:
        try:
            self._client.send_email(
                Source=self._from_address,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                },
            )
        except (BotoCoreError, ClientError):
            logger.exception("SES send_email failed for to=%s subject=%s", to, subject)


class LoggingEmailSender:
    """Local/test default — no real delivery. Tests can capture what "was
    sent" by reading the log, or by monkeypatching `send_email` directly."""

    async def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("LoggingEmailSender: to=%s subject=%s body=%s", to, subject, body)


_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is None:
        settings = get_settings()
        _sender = SesEmailSender() if settings.email_backend == "ses" else LoggingEmailSender()
    return _sender


async def send_email(to: str, subject: str, body: str) -> None:
    await get_email_sender().send_email(to, subject, body)
