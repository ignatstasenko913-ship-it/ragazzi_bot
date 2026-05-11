"""
Инициализация БД и заполнение начальных данных о филиалах.

ПЕРЕД ЗАПУСКОМ:
1. Запустите python scripts/list_groups.py
2. Найдите ID каждой группы-филиала
3. Вставьте правильные ID в telegram_group_id ниже
4. Запустите: python scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.session import init_db, get_session
from database.models import Branch
from sqlalchemy import select

# ─────────────────────────────────────────────────────────────────────────────
# Заполните telegram_group_id реальными ID из list_groups.py
# Координаты взяты из реальных адресов филиалов Ragazzi во Владивостоке
# ─────────────────────────────────────────────────────────────────────────────
INITIAL_BRANCHES = [
    {
        "name": "RAGAZZI pizza shop (жк Восточный Луч)",
        "short_name": "Восточный Луч",
        "address": "Владивосток, Полк. Фесюна, 20",
        "lat": 43.168548,
        "lon": 131.960685,
        "telegram_group_id": "-4864426420",   # ← вставьте ID из list_groups.py
        "is_active": True,
    },
    {
        "name": "RAGAZZI pizza shop (Шилкинская)",
        "short_name": "Шилкинская",
        "address": "Владивосток, ул. Шилкинская",
        "lat": 43.117887,
        "lon": 131.921823,
        "telegram_group_id": "-1001000000002",  # ← вставьте ID из list_groups.py
        "is_active": True,
    },
    {
        "name": "RAGAZZI pizza shop (Сочинская)",
        "short_name": "Сочинская",
        "address": "Владивосток, ул. Сочинская",
        "lat": 43.082337,
        "lon": 131.957398,
        "telegram_group_id": "-1001000000003",  # ← вставьте ID из list_groups.py
        "is_active": True,
    },
    {
        "name": "RAGAZZI pizza shop (Набережная)",
        "short_name": "Набережная",
        "address": "Владивосток, ул. Набережная",
        "lat": 43.116662,
        "lon": 131.877737,
        "telegram_group_id": "-5001918677",    # ← вставьте ID из list_groups.py
        "is_active": True,
    },
]


async def main() -> None:
    print("Initializing database...")
    await init_db()
    print("Tables created.")

    async with get_session() as session:
        result = await session.execute(select(Branch))
        existing = list(result.scalars().all())
        if not existing:
            for b in INITIAL_BRANCHES:
                session.add(Branch(**b))
            print(f"Seeded {len(INITIAL_BRANCHES)} branches.")
        else:
            print(f"Branches already exist ({len(existing)}). Deleting and re-seeding...")
            for b in existing:
                await session.delete(b)
            await session.flush()
            for b in INITIAL_BRANCHES:
                session.add(Branch(**b))
            print(f"Re-seeded {len(INITIAL_BRANCHES)} branches.")

    print("\nFilial groups configured:")
    for b in INITIAL_BRANCHES:
        flag = "✓" if not b["telegram_group_id"].startswith("-10010000") else "⚠ ЗАМЕНИТЕ ID!"
        print(f"  {flag} {b['name']}: {b['telegram_group_id']}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
