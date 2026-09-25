from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Event


def check_event_time(
    db: Session,
    user: str,
    starts_at: datetime,
    ends_at: datetime,
    exclude_event_id: int | None = None,
):
    # Check whether ends_time > starts_time
    if ends_at <= starts_at:
        raise HTTPException(status_code=422, detail="End time must be later than start time")

    # Check for time overlap
    statement = select(Event).where(
        Event.owner_id == user,
        Event.starts_at < ends_at,
        Event.ends_at > starts_at,
    )
    # An update must not conflict with the event being updated.
    if exclude_event_id is not None:
        statement = statement.where(Event.id != exclude_event_id)

    existing_event = db.scalars(statement.limit(1)).first()
    if existing_event is not None:
        raise HTTPException(
            status_code=409,
            detail="This time overlaps with an existing event",
        )
