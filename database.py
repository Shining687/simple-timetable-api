from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session


# Keep this project's database separate from the original project's data.
DATABASE_URL = "sqlite:///./timetable.db"

engine = create_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"check_same_thread": False},
)

class Base(DeclarativeBase):
    pass


def get_database():
    # Each request gets its own session, which closes when the request ends.
    with Session(engine) as db:
        yield db
