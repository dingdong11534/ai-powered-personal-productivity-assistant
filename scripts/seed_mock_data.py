"""Seed script for mock reminders, schedules, and habits/hobbies.

Creates 5 entries each for:
- Reminders
- Schedule items
- Habits / Hobbies
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.storage.database import SessionLocal, create_all_tables
from app.storage.models import Habit, HabitFrequency, Reminder, ScheduleItem, User


def seed_mock_data() -> None:
    create_all_tables()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        kunal = db.query(User).filter(User.username == "kunal").first()
        kunal_id = kunal.id if kunal else None

        # 1. 5 Mock Reminders
        mock_reminders = [
            ("Drink a large glass of water and do 5 min of desk stretches", now + timedelta(hours=1)),
            ("Prepare slide deck for quarterly project review", now + timedelta(hours=3)),
            ("Submit feedback on API documentation draft", now + timedelta(days=1, hours=2)),
            ("Check plant soil moisture and water ferns", now + timedelta(days=1, hours=6)),
            ("Review weekly budget and categorize recent expenses", now + timedelta(days=2)),
        ]

        existing_reminder_messages = {r.message for r in db.query(Reminder).all()}
        for msg, remind_at in mock_reminders:
            if msg not in existing_reminder_messages:
                db.add(Reminder(message=msg, remind_at=remind_at, user_id=kunal_id))

        # 2. 5 Mock Schedule Items
        mock_schedules = [
            ("Team Sync & Daily Standup Meeting", now + timedelta(hours=2), now + timedelta(hours=2, minutes=30)),
            ("Deep Work: Backend Refactoring & Architecture", now + timedelta(hours=3), now + timedelta(hours=5)),
            ("Productivity Assistant Demo & Milestone Review", now + timedelta(days=1, hours=4), now + timedelta(days=1, hours=5, minutes=30)),
            ("Weekly Planning & Task Prioritization", now + timedelta(days=2, hours=1), now + timedelta(days=2, hours=2)),
            ("System Design & Cloud Deployment Workshop", now + timedelta(days=3, hours=5), now + timedelta(days=3, hours=6, minutes=30)),
        ]

        existing_schedule_titles = {s.title for s in db.query(ScheduleItem).all()}
        for title, starts_at, ends_at in mock_schedules:
            if title not in existing_schedule_titles:
                db.add(ScheduleItem(title=title, starts_at=starts_at, ends_at=ends_at, user_id=kunal_id))

        # 3. 5 Mock Habits / Hobbies
        mock_habits = [
            ("Morning Meditation & Mindfulness", HabitFrequency.DAILY, 1),
            ("Read 30 minutes of Sci-Fi / Non-Fiction", HabitFrequency.DAILY, 1),
            ("Guitar Practice & Chord Drills", HabitFrequency.WEEKLY, 3),
            ("Running or 5km Outdoor Jog", HabitFrequency.WEEKLY, 3),
            ("Digital Painting & Sketching", HabitFrequency.WEEKLY, 2),
        ]

        existing_habit_names = {h.name for h in db.query(Habit).all()}
        for name, freq, target in mock_habits:
            if name not in existing_habit_names:
                db.add(Habit(name=name, frequency=freq, target_count=target, user_id=kunal_id))

        db.commit()
        print("Successfully seeded mock data!")
        print(f"Total Reminders: {db.query(Reminder).count()}")
        print(f"Total Schedules: {db.query(ScheduleItem).count()}")
        print(f"Total Habits: {db.query(Habit).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_mock_data()
