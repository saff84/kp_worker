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

1. Войдите под `operator@local / operator123`.
2. Перейдите во вкладку `1. Загрузка КП`.
3. Нажмите `Создать заявку и загрузить КП` (выберите файл КП в формате XLSX/XLS/CSV/PDF/DOCX/TXT).
4. Перейдите во вкладку `3. Сопоставление` и запустите:
   - `Запустить парсинг`
   - `Запустить сопоставление`
5. Нажмите `Загрузить результаты`, вручную подтвердите/отклоните спорные позиции.
6. Нажмите `Экспорт` для выгрузки результата.

## Демо-логины

- `operator@local` / `operator123`
- `admin@local` / `admin123`

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
