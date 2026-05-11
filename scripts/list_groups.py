"""Выводит список всех групп и каналов, в которых состоит юзербот.
Запустить: python scripts/list_groups.py
Скопировать нужный ID в .env → ORDER_SOURCE_GROUPS
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from telethon import TelegramClient
from telethon.tl.types import (
    Channel, Chat,
    InputPeerChannel, InputPeerChat,
)


async def main() -> None:
    client = TelegramClient(
        settings.TELEGRAM_SESSION_NAME,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.start(phone=settings.TELEGRAM_PHONE)

    print("\n" + "=" * 60)
    print("  Группы и каналы аккаунта")
    print("=" * 60)
    print(f"{'ID':<20} {'Тип':<12} Название")
    print("-" * 60)

    groups = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            kind = "Канал" if getattr(entity, "broadcast", False) else "Группа"
            groups.append((dialog.id, kind, dialog.name))

    groups.sort(key=lambda x: x[1])  # sort by type
    for gid, kind, name in groups:
        print(f"{gid:<20} {kind:<12} {name}")

    print("=" * 60)
    print("\nСкопируйте ID нужной группы(групп) в .env:")
    print("ORDER_SOURCE_GROUPS=-100xxxxxxxxxx,-100yyyyyyyyyy")
    print()

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
