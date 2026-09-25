from datetime import datetime

from pydantic import BaseModel, Field, NaiveDatetime
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# Database model: each object represents one event in the table.
class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str]
    title: Mapped[str]
    description: Mapped[str | None]
    location: Mapped[str | None]
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]


# Custom request schema; id and owner_id are set by the server.
class EventInput(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    location: str | None = None
    starts_at: NaiveDatetime
    ends_at: NaiveDatetime
