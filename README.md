# 🍕 Ragazzi — система маршрутизации заказов

Автоматическая система маршрутизации заказов для сети пиццерий Ragazzi во Владивостоке.

## Архитектура

```
ragazzi_bot/
├── main.py                        # Точка входа (userbot + admin bot)
├── config.py                      # Настройки через pydantic-settings
├── database/
│   ├── models.py                  # SQLAlchemy модели
│   └── session.py                 # Сессии БД, init_db
├── parsers/
│   ├── base.py                    # Абстрактный парсер
│   ├── site_parser.py             # Парсер заказов с сайта
│   ├── app_parser.py              # Парсер заказов из приложения
│   └── registry.py                # Реестр парсеров (автодетект формата)
├── routing/
│   ├── geo_service.py             # Геокодирование + маршрутизация (2GIS/Яндекс)
│   └── router.py                  # Поиск ближайшего филиала с учётом пробок
├── services/
│   ├── branch_service.py          # CRUD филиалов
│   ├── order_service.py           # CRUD заказов, статистика
│   ├── duplicate_service.py       # Защита от дублей
│   └── notification_service.py    # Отправка уведомлений
├── handlers/
│   ├── userbot/
│   │   └── order_handler.py       # Чтение групп, pipeline обработки
│   └── admin_bot/
│       ├── admin_handler.py       # Aiogram роутер (меню, кнопки, FSM)
│       ├── keyboards.py           # Inline клавиатуры
│       └── states.py              # FSM состояния
├── utils/
│   ├── formatters.py              # Форматирование заказов в единый шаблон
│   ├── validators.py              # Валидация телефонов, адресов
│   └── logger.py                  # Loguru setup
└── scripts/
    └── init_db.py                 # Инициализация БД + seed филиалов
```

## Как запустить

### 1. Установить зависимости

```bash
pip install -r requirements.txt
```

### 2. Создать файл `.env`

```bash
cp .env.example .env
# Заполните все значения в .env
```

**Обязательные параметры:**
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — получить на [my.telegram.org](https://my.telegram.org)
- `TELEGRAM_PHONE` — номер аккаунта-юзербота
- `TELEGRAM_BOT_TOKEN` — токен бота для админ-панели (`@BotFather`)
- `ORDER_SOURCE_GROUPS` — ID групп откуда читать заказы
- `ADMIN_IDS` — Telegram ID администраторов
- `MANAGER_IDS` — Telegram ID менеджеров
- `TWOGIS_API_KEY` — ключ 2GIS API (получить на [dev.2gis.com](https://dev.2gis.com))

### 3. Инициализировать базу данных и заполнить филиалы

```bash
python scripts/init_db.py
```

> Отредактируйте `scripts/init_db.py` — замените `telegram_group_id` на реальные ID групп филиалов, и при необходимости скорректируйте адреса и координаты.

### 4. Запустить

```bash
python main.py
```

При первом запуске Telethon попросит ввести код подтверждения (как при входе в Telegram).

---

## Архитектурные решения

### Два Telegram-клиента в одном процессе

| Клиент | Тип | Назначение |
|--------|-----|-----------|
| Telethon userbot | Аккаунт пользователя | Читать сообщения из групп (бот не может быть добавлен в группы без прав) |
| aiogram Bot | Обычный бот | Интерактивная админ-панель с кнопками и FSM |

### Pipeline обработки заказа

```
Новое сообщение в группе
  ↓ asyncio.Queue (буфер 200 сообщений)
  ↓ N воркеров (по умолчанию 3)
  ↓ ParserRegistry.parse() → автодетект формата
  ↓ OrderService.create_from_parsed() → сохранение в БД
  ↓ DuplicateService.check_and_record() → проверка дубля
  ↓ Router.route():
      Самовывоз → поиск филиала по имени
      Доставка  → геокодирование → проверка зоны → ближайший активный филиал
  ↓ NotificationService.send_to_branch() → отправка в группу филиала
  ↓ NotificationService.notify_manager_group() → копия менеджерам
```

### Зона доставки
- Центр: Владивосток (43.1155, 131.8855)
- Максимальный радиус: 50 км
- Де-Фриз (~25 км) — **допустимо**
- Уссурийск (~100 км) — **недопустимо**

### Защита от дублей
Дубль определяется по совпадению номера заказа в окне `DUPLICATE_WINDOW_MINUTES` (по умолчанию 60 мин).

### Geo API
- **Основной**: 2GIS (отличное покрытие Владивостока, маршрутизация с пробками)
- **Резервный**: Яндекс.Карты (если указан `YANDEX_MAPS_API_KEY`)
- **Фоллбэк**: оценка по прямой линии (30 км/ч) если API недоступен

---

## Управление через Telegram

Отправьте `/start` боту-администратору. Доступно только пользователям из `ADMIN_IDS` и `MANAGER_IDS`.

| Раздел | Доступ | Действия |
|--------|--------|---------|
| 🏪 Филиалы | Admin | Включить/выключить, просмотр, добавление |
| 📊 Статистика | Manager | Статистика за сегодня |
| 📋 Последние заказы | Manager | Последние 10 заказов |
| ⚠️ Проблемные | Manager | Просмотр + ручное распределение |
| 🔁 Дубликаты | Manager | Список дублей |
| ⚖️ Нагрузка | Manager | Заказов по филиалам сегодня |
| 📤 Ручное распределение | Manager | Отправить проблемный заказ в выбранный филиал |

---

## Расширение системы

### Добавить новый формат заказов

1. Создайте `parsers/my_parser.py` — наследуйте от `BaseParser`
2. Реализуйте `can_parse()` и `parse()`
3. Зарегистрируйте в `parsers/registry.py` → `build_registry()`

### Добавить новый филиал

Через Telegram-бот (кнопка "Добавить филиал") или через `scripts/init_db.py`.

### Изменить зону доставки

В `.env`:
```env
DELIVERY_CENTER_LAT=43.1155
DELIVERY_CENTER_LON=131.8855
DELIVERY_MAX_RADIUS_KM=50.0
```
