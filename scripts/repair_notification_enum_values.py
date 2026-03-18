from __future__ import annotations

import argparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models.enums import NotificationChannel, NotificationStatus, NotificationType


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair legacy uppercase notification enum values.")
    parser.add_argument("--apply", action="store_true", help="Actually update rows. Without this flag the script only reports counts.")
    return parser.parse_args()


def repair_notification_enum_values(session: Session, *, apply: bool = False) -> dict[str, int]:
    mappings = {
        "notification_type": {member.name: member.value for member in NotificationType},
        "channel": {member.name: member.value for member in NotificationChannel},
        "status": {member.name: member.value for member in NotificationStatus},
    }
    result: dict[str, int] = {"applied": int(apply)}

    for column, replacement_map in mappings.items():
        count = 0
        for old_value in replacement_map:
            count += session.execute(
                text(f"SELECT COUNT(*) FROM notifications WHERE {column} = :value"),
                {"value": old_value},
            ).scalar_one()
        result[column] = count

        if not apply or count == 0:
            continue

        for old_value, new_value in replacement_map.items():
            session.execute(
                text(f"UPDATE notifications SET {column} = :new_value WHERE {column} = :old_value"),
                {"old_value": old_value, "new_value": new_value},
            )

    return result


def main() -> None:
    args = parse_args()
    with session_scope() as session:
        result = repair_notification_enum_values(session, apply=args.apply)
    print(result)
    if not args.apply:
        print("Dry run only. Re-run with --apply to update legacy enum values in notifications.")


if __name__ == "__main__":
    main()
