# Parser KP (Production-ready scaffold)

Production-ready каркас сервиса переподбора оборудования:
- модульный monolith на FastAPI
- PostgreSQL + Alembic migrations
- Redis + RQ worker для async jobs
- file storage abstraction (`app/services/storage.py`)
- простая SPA (`web/`) для демонстрации ключевых экранов

## Что реализовано

- Auth: login / refresh
- Requests: create / list / get
- Files: upload
- Parsing: start / status (background task)
- Matching: start / status (background task)
- Results: get / manual review update
- Export: create / status + download link
- History: audit logs list
- Admin CRUD:
  - product catalog
  - analog mappings
  - matching rules

## Структура backend

```text
app/
  core/              # config, security, error standard
  db/                # engine/session/base
  models/            # SQLAlchemy entities
  modules/
    auth/            # login/refresh
    requests/        # request lifecycle
    files/           # upload ingestion
    parsing/         # parse start/status
    matching/        # matching start/status
    results/         # results + manual review
    export/          # export jobs + links
    history/         # audit history
    admin/           # catalog/analogs/rules CRUD
  jobs/              # RQ queue + task handlers
  services/          # storage/service-level helpers
  shared/            # shared helpers (pagination)
alembic/             # migrations
web/                 # frontend demo
```

## Запуск через Docker Compose (рекомендуется)

```bash
docker compose up --build
```

Поднимутся сервисы:
- `api` (FastAPI)
- `worker` (RQ worker)
- `db` (PostgreSQL)
- `redis`

Alembic миграции применяются автоматически в `api` и `worker` командах.

После `docker compose up --build` откройте в браузере:
- UI: <http://127.0.0.1/>
- API docs: <http://127.0.0.1/docs>

### Публичный сервер (VPS)

На машине с публичным IP интерфейс и API доступны по `http://<публичный-IP>/` (порт 80). Откройте порт 80 в security group облака / `sudo ufw allow 80/tcp` при использовании UFW.

```bash
sudo apt update && sudo apt install -y git
git clone <URL-вашего-репозитория> parser_kp && cd parser_kp
cp .env.example .env
```

Отредактируйте `.env` для продакшена: задайте длинный случайный `SECRET_KEY`, выставьте `SEED_DEMO_USERS=false`. Админка и `/api/v1/admin/*` доступны пользователям с флагом **`is_admin` в БД** (см. `create_user --admin`) и/или email из **`ADMIN_EMAILS`** (через запятую). При желании смените пароль PostgreSQL в `docker-compose.yml` (сервис `db`) и в `DATABASE_URL`.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

В `docker-compose.yml` сервис `api` уже публикует **`80:8000`** (интерфейс на стандартном HTTP-порту).

Создайте первого пользователя (логин по email/паролю в UI сохраняется):

```bash
docker compose exec api python -m app.cli.create_user --email you@example.com --password 'ВашНадёжныйПароль' --name 'Admin' --admin
```

Флаг **`--admin`** выставляет в таблице `users` поле **`is_admin = true`** (вкладка админки и админ-API без правки `ADMIN_EMAILS`). Альтернатива: добавить email в `ADMIN_EMAILS` в `.env` и перезапустить API.

Для уже созданного пользователя без `--admin`:

```sql
UPDATE users SET is_admin = true WHERE lower(email) = 'you@example.com';
```

Локально при `SEED_DEMO_USERS=true` по-прежнему создаются учётные записи для разработки (см. `app/main.py`, функция `seed_data`); на публичном сервере держите `SEED_DEMO_USERS=false`.

## Локальный запуск без Docker (если PostgreSQL/Redis уже есть)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

В отдельном терминале для воркера:

```powershell
.\.venv\Scripts\python -m app.worker
```

Открыть:
- UI: <http://127.0.0.1:8000/>
- API docs: <http://127.0.0.1:8000/docs>

## Быстрый сценарий для пользователя

1. Войдите (email и пароль выдаёт администратор или создаются при локальной разработке с `SEED_DEMO_USERS=true`).
2. Перейдите к шагу загрузки КП.
3. Нажмите `Создать заявку и загрузить КП` (файл XLSX/XLS/CSV/PDF/DOCX/TXT) или создайте заявку из текста.
4. Запустите обработку (парсинг и сопоставление), проверьте таблицу результатов.
5. При необходимости выполните экспорт.

## Пользователи и роли

- Вход в UI и API по email и паролю без изменений.
- Админские возможности (вкладка в UI и `/api/v1/admin/*`) если у пользователя **`users.is_admin = true`** в БД и/или email указан в **`ADMIN_EMAILS`** в `.env`.
- На публичном сервере задайте `SEED_DEMO_USERS=false` и создавайте пользователей: `python -m app.cli.create_user ... --admin` (в Docker: `docker compose exec api python -m app.cli.create_user ...`).

## Статусы заявки

- `uploaded`
- `parsed`
- `needs_review`
- `completed`

## Async jobs

- `parsing_task(request_id)`
- `matching_task(request_id, threshold)`
- `export_task(request_id, export_id)`

Очередь: Redis/RQ (`app/jobs/queue.py`), worker: `python -m app.worker`.

Если Redis недоступен, endpoints запуска задач выполняют fallback в синхронном режиме и возвращают `status=completed_sync`.

## Векторный индекс каталога (Qdrant)

- Инкрементальная индексация каталога выполняется при:
  - `POST /api/v1/admin/catalog/products`
  - `PUT /api/v1/admin/catalog/products/{product_id}`
  - `DELETE /api/v1/admin/catalog/products/{product_id}` (деактивация + удаление из индекса)
  - `POST /api/v1/admin/catalog/import`
- Полная переиндексация:
  - API: `POST /api/v1/admin/catalog/reindex`
  - CLI: `python -m app.cli.reindex_catalog`

По умолчанию используется мультиязычная embedding-модель: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

## Словарь правил сопоставления (ключевые фразы)

Словарь правил-фильтров для кандидатов каталога доступен через админ API и UI:
- `GET /api/v1/admin/matching/catalog-rules`
- `POST /api/v1/admin/matching/catalog-rules`
- `PUT /api/v1/admin/matching/catalog-rules/{rule_id}`
- `DELETE /api/v1/admin/matching/catalog-rules/{rule_id}`

Правила сохраняются в `storage/catalog_match_rules.json`.

Текущее правило:
- если позиция КП содержит одновременно `счетчик` и `присоединител*`, то кандидаты из каталога должны содержать `КМЧ` в названии.

Это помогает избегать подбора обычного счетчика вместо комплекта/исполнения с присоединителями.

## Импорт каталога и соответствий

### 1) Импорт каталога
- Endpoint: `POST /api/v1/admin/catalog/import`
- Формат файла: `.csv` или `.xlsx`
- Обязательные колонки: `sku`, `name`, `brand`
- Опциональные: `category`, `is_active`, `attrs_json`

Пример CSV:
```csv
sku,name,brand,category,is_active,attrs_json
TEST-001,Test Pump A,TestBrand,Pumps,true,"{""power_kw"":1.1}"
```

### 2) Импорт соответствий с конкурентами
- Endpoint: `POST /api/v1/admin/competitor-mappings/import`
- Формат файла: `.csv` или `.xlsx`
- Обязательные колонки: `our_sku`, `competitor_brand`, `competitor_name`
- Опциональные: `competitor_sku`, `match_type`, `confidence`, `source`, `is_active`

Пример CSV:
```csv
our_sku,competitor_brand,competitor_name,competitor_sku,match_type,confidence,source,is_active
TEST-001,CompetitorX,Pump X,CX-100,analog,0.86,import,true
```

### 3) Реальный parsing файлов
- `CSV/XLSX/XLS`: извлечение строк по колонкам (`name/наименование`, `article/артикул`, `brand/бренд`, `quantity/количество`)
- `PDF`: baseline extraction + попытка разбиения табличных строк по разделителям (tab/много пробелов/`;`) + OCR fallback для сканов (если установлен локальный tesseract)
- `DOCX`: разбор таблиц документа, fallback на абзацы
- `DOC`: best-effort через `antiword` или `soffice --convert-to txt` (если установлены в системе)
- `TXT`: построчный парсинг

Оба import endpoint возвращают детальный отчёт по ошибкам строк в поле `errors` (до 100 записей), а также сохраняют отчёт в БД.

## Отчёты импорта и выгрузка

- API:
  - `GET /api/v1/admin/import-reports`
  - `GET /api/v1/admin/import-reports/{report_id}`
  - `GET /api/v1/admin/import-reports/{report_id}/export`
- UI: вкладка **Ошибки импорта** с просмотром деталей и выгрузкой CSV

## Шаблоны импорта

- `GET /api/v1/admin/templates/catalog`
- `GET /api/v1/admin/templates/competitor-mappings`
