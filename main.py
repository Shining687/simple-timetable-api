from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

import database
from auth import get_current_user
from calendar_export import router as calendar_router
from database import Base, get_database
from event_checks import check_event_time
from models import Event, EventInput

'''creat database tables'''
@asynccontextmanager
async def create_tables(app: FastAPI):
    Base.metadata.create_all(database.engine)
    yield

'''create app'''
app = FastAPI(title="Simple Timetable API", lifespan=create_tables)
app.include_router(calendar_router)

# Create
@app.post("/events", status_code=201)
def create_event(
    data: EventInput,
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    check_event_time(db, user, data.starts_at, data.ends_at)
    
    event = Event(owner_id=user, **data.__dict__)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event

# Create a finite batch of weekly events.
@app.post("/events/weekly", status_code=201)
def create_weekly_events(
    data: EventInput,
    repeat_count: int = Query(default=4, ge=1, le=20),
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    # Prevent the generated weekly events from overlapping each other.
    if repeat_count > 1 and data.ends_at - data.starts_at > timedelta(weeks=1):
        raise HTTPException(
            status_code=422,
            detail="Weekly occurrences must not overlap each other",
        )

    events = []
    for i in range(repeat_count):
        offset = timedelta(weeks=i)
        starts_at = data.starts_at + offset
        ends_at = data.ends_at + offset

        check_event_time(db, user, starts_at, ends_at)

        event = Event(
            owner_id=user,
            title=data.title,
            description=data.description,
            location=data.location,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        events.append(event)

    db.add_all(events)
    db.commit()
    for event in events:
        db.refresh(event)
    return events


# Read events (by keywords)
@app.get("/events")
def list_events(
    keyword: str | None = None,
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    statement = select(Event).where(Event.owner_id == user)
    if keyword is not None and keyword.strip():
        statement = statement.where(
            Event.title.icontains(keyword.strip(), autoescape=True)
        )
    statement = statement.order_by(Event.starts_at, Event.id)
    select_event = db.scalars(statement).all()
    return select_event

# Read events by event_id
@app.get("/events/{event_id}")
def read_event(
    event_id: int,
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None or event.owner_id != user:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

# Update 
@app.put("/events/{event_id}")
def update_event(
    event_id: int,
    data: EventInput,
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None or event.owner_id != user:
        raise HTTPException(status_code=404, detail="Event not found")
    check_event_time(
        db, user, data.starts_at, data.ends_at, exclude_event_id=event_id
    )

    event.title = data.title
    event.description = data.description
    event.location = data.location
    event.starts_at = data.starts_at
    event.ends_at = data.ends_at

    db.commit()
    db.refresh(event)
    return event

# Delete
@app.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    db: Session = Depends(get_database),
    user: str = Depends(get_current_user),
):
    event = db.get(Event, event_id)
    if event is None or event.owner_id != user:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()
    return Response(status_code=204)
