"""Run with python smoke_test.py. Uses a temporary database only."""

from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlalchemy import create_engine

import database
from main import app


def main():
    original_engine = database.engine
    with TemporaryDirectory() as folder:
        path = Path(folder) / "test.db"
        database.engine = create_engine(
            f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
        )
        try:
            alice = {"Authorization": "Bearer alice-dev-token"}
            bob = {"Authorization": "Bearer bob-dev-token"}
            data = {
                "title": "Discussion", "location": "Library",
                "starts_at": "2026-09-24T14:00:00",
                "ends_at": "2026-09-24T15:00:00",
            }
            with TestClient(app) as client:
                assert client.get("/events").status_code in (401, 403)
                assert client.get("/events", headers={"Authorization": "Bearer wrong"}).status_code == 401
                result = client.post("/events", json=data, headers=alice)
                assert result.status_code == 201, result.text
                saved = result.json()
                assert saved["starts_at"] == data["starts_at"]
                assert saved["owner_id"] == "alice"
                url = f"/events/{saved['id']}"
                assert len(client.get("/events", headers=alice).json()) == 1
                assert client.get("/events", headers=bob).json() == []
                assert client.get(url, headers=bob).status_code == 404
                assert client.put(url, json=data, headers=bob).status_code == 404
                assert client.delete(url, headers=bob).status_code == 404

                # Export must preserve local times and user isolation.
                assert client.get("/events.ics").status_code in (401, 403)
                assert client.get("/events.ics", headers={"Authorization": "Bearer wrong"}).status_code == 401
                assert Calendar.from_ical(client.get("/events.ics", headers=bob).content).walk("VEVENT") == []
                export_data = dict(data, description="\u8bfe\u7a0b, notes;\n" + "\u4e2d\u6587" * 60)
                assert client.put(url, json=export_data, headers=alice).status_code == 200
                before_export = client.get(url, headers=alice).json()
                exported = client.get("/events.ics", headers=alice)
                assert exported.status_code == 200
                assert exported.headers["content-type"].startswith("text/calendar")
                assert "events.ics" in exported.headers["content-disposition"]
                items = Calendar.from_ical(exported.content).walk("VEVENT")
                assert len(items) == 1
                item = items[0]
                assert item.decoded("dtstart") == datetime.fromisoformat(data["starts_at"])
                assert item.decoded("dtend") == datetime.fromisoformat(data["ends_at"])
                assert str(item["summary"]) == data["title"]
                assert str(item["description"]) == export_data["description"]
                assert str(item["location"]) == data["location"]
                repeated = Calendar.from_ical(client.get("/events.ics", headers=alice).content).walk("VEVENT")
                assert repeated[0]["uid"] == item["uid"]
                assert client.get(url, headers=alice).json() == before_export

                for end in ("2026-09-24T14:00:00", "2026-09-24T13:00:00"):
                    invalid = dict(data, ends_at=end)
                    assert client.post("/events", json=invalid, headers=alice).status_code == 422
                    assert client.put(url, json=invalid, headers=alice).status_code == 422
                assert client.put(url, json={"title": "Incomplete"}, headers=alice).status_code == 422
                assert client.post("/events", json=dict(data, title=""), headers=alice).status_code == 422
                assert client.post("/events", json=dict(data, starts_at=data["starts_at"] + "Z"), headers=alice).status_code == 422
                assert client.get(url, headers=alice).json()["location"] == "Library"

                # Reject overlapping creations without inserting or changing any records.
                before_create = client.get("/events", headers=alice).json()
                for start, end in [
                    ("13:30", "14:30"),
                    ("14:30", "15:30"),
                    ("14:10", "14:50"),
                    ("13:00", "16:00"),
                    ("14:00", "15:00"),
                ]:
                    conflict = dict(
                        data,
                        starts_at=f"2026-09-24T{start}:00",
                        ends_at=f"2026-09-24T{end}:00",
                    )
                    result = client.post("/events", json=conflict, headers=alice)
                    assert result.status_code == 409, (start, end, result.text)
                    assert client.get("/events", headers=alice).json() == before_create

                # An event ending exactly when the existing event starts is allowed.
                earlier = dict(data, starts_at="2026-09-24T13:00:00", ends_at="2026-09-24T14:00:00")
                result = client.post("/events", json=earlier, headers=alice)
                assert result.status_code == 201, result.text
                assert client.delete(f"/events/{result.json()['id']}", headers=alice).status_code == 204

                # Adjacent events are allowed; overlapping updates must not change the record.
                adjacent = dict(data, starts_at="2026-09-24T15:00:00", ends_at="2026-09-24T16:00:00")
                result = client.post("/events", json=adjacent, headers=alice)
                assert result.status_code == 201, result.text
                adjacent_url = f"/events/{result.json()['id']}"
                before_update = client.get(url, headers=alice).json()
                for start, end in [
                    ("14:30", "15:30"),
                    ("15:30", "16:30"),
                    ("15:10", "15:50"),
                    ("14:00", "17:00"),
                    ("15:00", "16:00"),
                ]:
                    conflict = dict(
                        data, title="Rejected",
                        starts_at=f"2026-09-24T{start}:00",
                        ends_at=f"2026-09-24T{end}:00",
                    )
                    result = client.put(url, json=conflict, headers=alice)
                    assert result.status_code == 409, (start, end, result.text)
                    assert client.get(url, headers=alice).json() == before_update

                # Move to a different time touching either end of the adjacent event.
                for start, end in [("16:00", "17:00"), ("13:00", "15:00")]:
                    moved = dict(
                        data,
                        starts_at=f"2026-09-24T{start}:00",
                        ends_at=f"2026-09-24T{end}:00",
                    )
                    result = client.put(url, json=moved, headers=alice)
                    assert result.status_code == 200, result.text
                    stored = client.get(url, headers=alice).json()
                    assert stored["starts_at"] == moved["starts_at"]
                    assert stored["ends_at"] == moved["ends_at"]
                assert client.put(url, json=data, headers=alice).status_code == 200

                # Another user's overlapping event must not block an update.
                assert client.post("/events", json=data, headers=bob).status_code == 201
                updated = dict(data, title="New title")
                del updated["location"]
                result = client.put(url, json=updated, headers=alice)
                assert result.status_code == 200, result.text
                assert result.json()["location"] is None
                assert client.delete(adjacent_url, headers=alice).status_code == 204

                # Search titles by substring, preserving ownership and literal wildcard characters.
                search_data = dict(data, title="Team Meeting 100%_ready")
                assert client.put(url, json=search_data, headers=alice).status_code == 200
                for keyword in ("meeting", "MEETING", " meeting ", "%", "_", "100%_"):
                    result = client.get("/events", params={"keyword": keyword}, headers=alice)
                    assert result.status_code == 200, result.text
                    assert [event["id"] for event in result.json()] == [saved["id"]]
                for keyword in ("missing", "Library", "100_ready"):
                    assert client.get("/events", params={"keyword": keyword}, headers=alice).json() == []
                assert client.get("/events", params={"keyword": "meeting"}, headers=bob).json() == []
                for keyword in ("%", "_"):
                    assert client.get("/events", params={"keyword": keyword}, headers=bob).json() == []
                for keyword in ("", "   "):
                    assert client.get("/events", params={"keyword": keyword}, headers=alice).json() == client.get("/events", headers=alice).json()
                assert client.put(url, json=updated, headers=alice).status_code == 200

                # A conflict on the last occurrence must leave the entire batch unsaved.
                weekly = dict(data, title="Weekly meeting", starts_at="2026-10-02T14:00:00", ends_at="2026-10-02T15:00:00")
                blocker = dict(weekly, starts_at="2026-10-16T14:00:00", ends_at="2026-10-16T15:00:00")
                result = client.post("/events", json=blocker, headers=alice)
                assert result.status_code == 201, result.text
                blocker_url = f"/events/{result.json()['id']}"
                before_weekly = client.get("/events", headers=alice).json()
                weekly_url = "/events/weekly?repeat_count=3"
                assert client.post(weekly_url, json=weekly).status_code in (401, 403)
                assert client.post(weekly_url, json=weekly, headers=alice).status_code == 409
                assert client.get("/events", headers=alice).json() == before_weekly
                for count in (0, 21):
                    assert client.post("/events/weekly", params={"repeat_count": count}, json=weekly, headers=alice).status_code == 422
                for end in ("2026-10-02T13:00:00", "2026-10-02T14:00:00", "2026-10-10T15:00:00"):
                    assert client.post(weekly_url, json=dict(weekly, ends_at=end), headers=alice).status_code == 422
                assert client.get("/events", headers=alice).json() == before_weekly
                assert client.delete(blocker_url, headers=alice).status_code == 204

                # The same times belong to different users and may be generated independently.
                for headers, owner in ((alice, "alice"), (bob, "bob")):
                    result = client.post(weekly_url, json=weekly, headers=headers)
                    assert result.status_code == 201, result.text
                    occurrences = result.json()
                    assert len(occurrences) == 3
                    assert len({event["id"] for event in occurrences}) == 3
                    for event, day in zip(occurrences, ("02", "09", "16")):
                        assert event["owner_id"] == owner
                        assert event["starts_at"] == f"2026-10-{day}T14:00:00"
                        assert event["ends_at"] == f"2026-10-{day}T15:00:00"
                        assert event["title"] == weekly["title"]
                        assert client.get(f"/events/{event['id']}", headers=headers).json() == event
                    for event in occurrences:
                        assert client.delete(f"/events/{event['id']}", headers=headers).status_code == 204

            # Close connections and restart the app to verify persistence on disk.
            database.engine.dispose()
            with TestClient(app) as client:
                assert client.get(url, headers=alice).json()["title"] == "New title"
                assert client.delete(url, headers=alice).status_code == 204
                assert client.get(url, headers=alice).status_code == 404
                assert client.delete(url, headers=alice).status_code == 404
                assert client.get("/events", headers=alice).json() == []
            print("PASS: CRUD, persistence, ownership, basic validation, create/update conflicts and boundaries, ICS export, keyword search, weekly events")
        finally:
            database.engine.dispose()
            database.engine = original_engine


if __name__ == "__main__":
    main()
