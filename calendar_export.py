from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from icalendar import Calendar, Event as CalendarEvent
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_database
from models import Event

router = APIRouter()


# Export the current user's events as an ICS file
@router.get("/events.ics", response_class=Response)
def export_calendar(
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    statement = select(Event).where(Event.owner_id == user)
    events = db.scalars(statement).all()

    calendar = Calendar()
    calendar.add("prodid", "-//Simple Timetable API//EN")
    calendar.add("version", "2.0")

    for event in events:
        item = CalendarEvent()
        item.add("uid", event.id)
        item.add("dtstamp", datetime.now(timezone.utc))
        item.add("summary", event.title)
        item.add("dtstart", event.starts_at)
        item.add("dtend", event.ends_at)

        if event.description:
            item.add("description", event.description)
        if event.location:
            item.add("location", event.location)

        calendar.add_component(item)

    return Response(
        content=calendar.to_ical(),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="events.ics"'},
    )


