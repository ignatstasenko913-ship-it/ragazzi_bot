"""One-time database bootstrap: create tables and seed initial branch data."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import init_db, get_session
from database.models import Branch, TelegramUser, UserRole
from sqlalchemy import select


INITIAL_BRANCHES = [
    {
        "name": "RAGAZZI pizza shop (жк Айвазовский)",
        "short_name": "жк Айвазовский",
        "address": "Владивосток, ул. Айвазовского",
        "lat": 43.2003,
        "lon": 131.9375,
        "telegram_group_id": "-1001000000001",  # ЗАМЕНИТЕ на реальный ID!
        "is_active": True,
    },
    {
        "name": "RAGAZZI pizza shop (жк Восточный Луч)",
        "short_name": "жк Восточный Луч",
        "address": "Владивосток, Полк. Фесюна, 20",
        "lat": 43.1548,
        "lon": 131.9389,
        "telegram_group_id": "-1001000000002",  # ЗАМЕНИТЕ на реальный ID!
        "is_active": True,
    },
    {
        "name": "RAGAZZI pizza shop (Центр)",
        "short_name": "Центр",
        "address": "Владивосток, ул. Светланская",
        "lat": 43.1155,
        "lon": 131.8855,
        "telegram_group_id": "-1001000000003",  # ЗАМЕНИТЕ на реальный ID!
        "is_active": True,
    },
]


async def main() -> None:
    print("Initializing database...")
    await init_db()
    print("Tables created.")

    async with get_session() as session:
        # Seed branches only if none exist
        result = await session.execute(select(Branch))
        existing = result.scalars().all()
        if not existing:
            for b in INITIAL_BRANCHES:
                branch = Branch(**b)
                session.add(branch)
            print(f"Seeded {len(INITIAL_BRANCHES)} branches.")
        else:
            print(f"Branches already exist ({len(existing)}), skipping seed.")

    print("Done. Edit scripts/init_db.py to update branch group IDs before first run.")


if __name__ == "__main__":
    asyncio.run(main())
