"""
Выводит ВСЕ группы аккаунта с ID, типом и количеством участников.
Запуск: python scripts/list_groups.py

Скопируйте ID группы «приём заказов» → ORDER_SOURCE_GROUPS в .env
Скопируйте ID групп филиалов → telegram_group_id в scripts/init_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat


async def main() -> None:
    client = TelegramClient(
        settings.TELEGRAM_SESSION_NAME,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.start(phone=settings.TELEGRAM_PHONE)

    groups = []
    channels = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            if entity.broadcast:
                channels.append((dialog.id, "Канал", dialog.name))
            else:
                groups.append((dialog.id, "Супергруппа", dialog.name))
        elif isinstance(entity, Chat):
            groups.append((dialog.id, "Группа", dialog.name))

    print("\n" + "=" * 70)
    print("  ГРУППЫ (сюда относится 'приём заказов' и группы филиалов)")
    print("=" * 70)
    print(f"{'ID':<22} {'Тип':<14} Название")
    print("-" * 70)
    for gid, kind, name in groups:
        print(f"{gid:<22} {kind:<14} {name}")

    if channels:
        print("\n" + "=" * 70)
        print("  КАНАЛЫ")
        print("=" * 70)
        for gid, kind, name in channels:
            print(f"{gid:<22} {kind:<14} {name}")

    print("\n" + "=" * 70)
    print("Что делать с этими данными:\n")
    print("1. Найдите группу «приём заказов» и скопируйте её ID в .env:")
    print("   ORDER_SOURCE_GROUPS=<ID группы приёма>\n")
    print("2. Найдите группы филиалов и впишите их ID в scripts/init_db.py")
    print("   в поле telegram_group_id каждого филиала\n")
    print("3. Пересоздайте БД и перезапустите бота:")
    print("   del ragazzi.db  (или rm ragazzi.db)")
    print("   python scripts/init_db.py")
    print("   python main.py")
    print("=" * 70 + "\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
