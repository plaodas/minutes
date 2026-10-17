"""Delete service tokens that have been revoked for 30 days."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from minutes.db import session_scope
from minutes.models import ServiceToken

logger = logging.getLogger("minutes.service_token_retention")

REVOKED_TOKEN_RETENTION = timedelta(days=30)


def sweep_expired_service_tokens(now: datetime | None = None) -> None:
    """Delete revoked tokens whose revocation is older than 30 days."""
    moment = now or datetime.now(tz=timezone.utc)
    cutoff = moment - REVOKED_TOKEN_RETENTION
    try:
        with session_scope() as session:
            deleted = (
                session.query(ServiceToken)
                .filter(
                    ServiceToken.revoked.is_(True),
                    ServiceToken.revoked_at.is_not(None),
                    ServiceToken.revoked_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
        if deleted:
            logger.info("Removed %s revoked service tokens", deleted)
    except SQLAlchemyError:
        logger.exception("Failed to remove expired revoked service tokens")
