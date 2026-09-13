# Оценка готовности модулей

Снимок на **13 сентября 2026**, ветка `main` (`310ef11`). Цель документа — зафиксировать, что уже можно считать рабочим продуктовым путём, а что ещё нужно дописать, прежде чем расширять функциональность.

Объём: ~27k строк Python (`app/`), ~15k строк TypeScript (`web/src`), ~1.6k строк тестов. Версия пакета: `0.1.0`.

## Шкала

| Статус | Значение |
|--------|----------|
| **Готов** | Рабочий путь, можно опираться при дописывании соседних модулей |
| **Частично** | Код есть, но дыры в конфиге, UI, провайдере или покрытии |
| **Сломан** | Заявлено в конфиге/доках, в рантайме упадёт или не подключится |
| **Заглушка** | Намеренно mock/legacy, не продакшен-путь |
| **Отсутствует** | Схема или клиент есть, реализации нет |
| **Deprecated** | Полная реализация, но продукт от неё уходит |

---

## Краткий вердикт

Продуктовый путь **проект → загрузка источников → очередь обработки → сущности → PR-отчёт** уже собран и используется во фронтенде. Это рабочий MVP, не скелет.

Главный разрыв не в «пустых папках», а в **незавершённом переносе с batches на projects**:

- бэкенд проекта умеет очередь, dashboard API, portrait/strategy/full-report, public-link;
- UI проекта показывает только KPI, отчёт, цитаты, сущности и счётчики очереди;
- богатая аналитика (графики, message lab, сравнение сегментов, interview units, экспорты, portrait/strategy) живёт в `BatchDetailPage` (~4k строк), который **снят с роутера**.

Пока этот разрыв не закрыт, дописывать новые «фичи отчёта» рискованно: половина уже написанного не видна пользователю.

---

## Карта продукта

```
Upload → project queue → [audio] ASR → chunk → extract → aggregate
  → (очередь простаивает) portrait / PR strategy / full report / smart report
```

| Слой | Путь | Состояние |
|-------|------|-----------|
| HTTP API | `app/api/routes/` + `app/api/v1/` | Готов по research-домену; legacy рядом |
| Сервисы | `app/services/` | Готов по ядру; дыры в ASR/embeddings/external |
| Репозитории / модели | `app/repositories/`, `app/models/` | Готов; часть таблиц — transitional/legacy |
| Workers | `app/workers/tasks/` | Готов (project queue + pipeline) |
| Frontend | `web/src/pages/ProjectDetailPage.tsx` | Готов как MVP; аналитика не перенесена |
| Тесты | `tests/` | Частично: очереди, hardening, smoke; мало e2e LLM/ASR |

---

## Backend по модулям

### 1. Проекты и источники — **Готов**

CRUD проектов, загрузка текста/docx/аудио (single + bulk), raw notes, лимиты размера, список источников.

- Сервисы: `ProjectService`, `IngestionService`, `SourceQueryService`
- Роуты: `research_projects.py`, `research_sources.py`, `project_analysis.py` (`bulk-upload`)
- UI: вкладка «Данные» + bulk upload на карточке анализа

Можно считать базой для всего остального.

### 2. Очередь обработки проекта — **Готов** (бэкенд) / **Частично** (UI)

`PROJECT_QUEUE_ENABLED` (default true), `PROJECT_QUEUE_CONCURRENCY` (1–8). Drainer: `process_project_processing_queue`. API: `POST /projects/{id}/process`, `GET /projects/{id}/processing-queue` (есть per-source список).

UI показывает только **pending / processing / completed**. Таблица по источникам и recover-pipeline есть на бэкенде (`POST .../documents/recover-pipeline`), во фронте не выведены.

### 3. Транскрипция — **Частично**, с **сломанным** Gemini и нарезкой аудио

Провайдеры:

| Provider | Файл | В factory | Default |
|----------|------|-----------|---------|
| `mock` | `transcription/mock_provider.py` | да | код: **mock** |
| `openai` | `openai_provider.py` | да | `.env.example`: openai |
| `whisper_local` | `whisper_local_provider.py` | да | |
| `http` | `http_provider.py` | да | |
| `gemini` | `gemini_provider.py` (~230 строк, реальный REST) | **нет** | Settings Literal допускает `gemini` |

`get_transcription_provider()` в `app/services/transcription/factory.py` на `gemini` бросает `ValueError`. Провайдер написан, но не подключён.

Нарезка длинного аудио (`audio_segment_split_service.py`) читает поля, которых **нет в `Settings`**:

- `audio_transcription_chunk_seconds`
- `audio_transcription_chunk_overlap_seconds`
- `effective_audio_transcription_chunk_seconds`

Они есть в `.env.example`, но не объявлены в `settings.py`. Путь chunked ASR упадёт с `AttributeError`.

`TRANSCRIPTION_MAX_SEGMENT_BYTES` в Settings есть. Есть отдельный Gemini fast-path по длительности.

**Дописать в первую очередь:** factory + поля Settings. Без этого заявленный audio-путь ненадёжен.

### 4. Чанкинг — **Готов**

Фиксированные окна (`ChunkingService`) и семантический OpenAI (`OpenAISemanticChunkingService`) с fallback на fixed. Стратегия передаётся в задаче (`fixed` / `openai`), глобального `CHUNKING_STRATEGY` в Settings нет (CLAUDE.md здесь устарел).

`CHUNK_SEMANTIC_MIN_CHARS` есть в `.env.example`, в `Settings` не объявлен.

Эмбеддинги чанков **не заполняются** (`embedding=None` в `ProcessingOrchestratorService`) — см. §9.

### 5. Извлечение сущностей — **Готов** (с тихим mock-fallback)

`RESEARCH_EXTRACTION_PROVIDER`: `gpt` | `mock`. Если нет `OPENAI_API_KEY`, factory молча уходит в mock. Сервис дополнительно режет текст на предложения, если GPT вернул ≤1 сущность.

Для локальной разработки это удобно; для оценки качества отчётов опасно: пайплайн «зелёный», а сущности — эвристики.

### 6. Агрегация и summary — **Готов**

Дедуп + `aggregation_snapshots` + `research_summaries`. Summary: `gpt` с fallback на deterministic.

### 7. PR-отчёт / smart report / readiness — **Готов** (нужен API-ключ)

Крупный реальный слой: `ResearchReportGenerationService`, gating (`data_readiness_service`, `PR_REPORT_*`), compact input (`smart_report_input_builder`), regenerate без сноса предыдущего отчёта.

UI проекта: generate / regenerate, `ResearchReportView`, цитаты из отчёта.

### 8. Portrait, PR strategy, full-report, public link — **Готов на API**, **Отсутствует в UI проекта**

Есть:

- `GET /projects/{id}/audience-portrait`
- `GET /projects/{id}/pr-strategy`
- `GET /projects/{id}/full-report`
- `POST /projects/{id}/public-link`
- `GET /report/public/{token}`

Клиент `web/src/api/api.ts` эти методы уже содержит. На страницах проекта **не вызываются**. Публичной страницы отчёта во фронте нет.

На batches те же артефакты были в `BatchDetailPage`.

### 9. Эмбеддинги / векторный поиск — **Отсутствует** (схема есть)

- Колонка `text_chunks.embedding` + HNSW (миграция `0011`)
- FTS GIN на транскриптах и чанках — есть
- Ни одного вызова embedding-модели в research-пути
- Legacy insights пишут **нулевой вектор** (`embedding_model="stub-zeros"`)

Документ `docs/transcript_storage.md` описывает retrieval как будто embeddings уже часть контракта. Это следующий крупный модуль, не hotfix.

### 10. Interview units (CustDev) — **Частично**

Сплит и persist есть (`interview_unit_split_service`, `interview_units_sync`, вызывается из full pipeline). Список API: **только** `GET /batches/{id}/interview-units`. Вкладки «units» на проекте — это **сущности**, не интервью.

`custdev_report_bundle.py` сам себя описывает как «narrative stubs, trend heuristics». Message lab в бандле: `"Heuristic placeholder; use Message Lab POST."`

### 11. Message lab, сравнение сегментов, экспорты дашборда — **Deprecated-путь (batches)**

Реализовано на `/batches/*`: message-lab, compare, CSV/SVG/PNG/zip, Excel/PPT отчёта. На project API **не вынесено**, в live UI **недоступно**.

Это готовый код, который нужно **перенести**, а не писать с нуля.

### 12. Внешний desk research — **Заглушка**

`EXTERNAL_RESEARCH_PROVIDER` default `mock` (детерминированные RU-статьи). HTTP-провайдер — тонкая обёртка POST на внешний URL. Вкладка «external» на проекте читает `external_articles_json` **из уже готового отчёта**, отдельного запуска поиска нет.

### 13. Хранилище файлов — **Частично**

Только `LocalFileStorage`. Нет S3/GCS. Для текущего Docker-деплоя достаточно.

### 14. Auth / мультитенантность — **Отсутствует**

Нет JWT, API-key, пользователей, ownership-проверок. CORS по умолчанию `*`. Public report — единственная осознанная «открытая» точка (token).

Для внутреннего MVP это ок; для любого внешнего стенда — блокер.

### 15. Legacy materials / insights / dashboard v1 — **Заглушка / demo**

`/materials`, `/insights`, `/dashboard/aggregates`. Regex-extraction, stub insight. UI всё ещё в навигации (Materials, Analytics). Путать с research-аналитикой нельзя.

### 16. Batches API — **Deprecated, но полный**

Роутер помечен `deprecated=True`, UI-роут редиректит на проект. Код и тесты очереди batches живы. Не удалять, пока не перенесены аналитика, interview units, message lab, экспорты.

---

## Frontend по экранам

| Экран | Роут | Состояние |
|-------|------|-----------|
| Home | `/` | Готов (health/ready) |
| Projects list | `/projects` | Готов |
| Project workspace | `/projects/:id` | **Готов как MVP** (отчёт, данные, ручная обработка, цитаты, external из отчёта, сущности) |
| Document / audio detail | `/sources/...` | Готов (короткий poll 90 с) |
| Batch workspace | код есть, роут снят | **Orphan** — самая полная аналитика |
| Transcription sink | `TranscriptionPage.tsx` | **Orphan**, не в навигаторе |
| Materials / Analytics | `/materials`, `/analytics` | Legacy demo |

`web/src/api/schema.d.ts` **устарел** (~30 paths, без project-analysis / queue / smart-report). Скрипт называется `npm run codegen`, не `generate-api` (так в CLAUDE.md). Живые типы — в рукописном `api.ts` / `types.ts`.

---

## Документация vs код

Расхождения, которые мешают планировать работу:

| Источник | Факт |
|----------|------|
| CLAUDE.md: `TRANSCRIPTION_PROVIDER` | Реально `RESEARCH_TRANSCRIPTION_PROVIDER` |
| CLAUDE.md: `CHUNKING_STRATEGY` env | Стратегия — аргумент задачи, не Settings |
| CLAUDE.md: `npm run generate-api` | `npm run codegen` |
| README описывает skeleton + legacy pipeline | Research/PR-домен уже основной продукт |
| `.env.example` vs `Settings()` | Gemini, audio chunk seconds, semantic min chars — drift |
| `docs/transcript_storage.md` про batches как основной группировщик | Product path — project queue |

---

## Тесты

Покрыто хорошо: очереди проекта/batch, bulk upload, docx, semantic fallback, concurrency, PR grounding/lexicon/readiness, upload hardening, smoke «не 500».

Почти нет: Gemini/factory, chunked ASR + Settings, запись embeddings, live report generation, public-link UI, contract OpenAPI, auth (его нет).

---

## Приоритеты дописания

Порядок — чтобы не начинать с «интересного», пока сломан заявленный путь и спрятана уже написанная аналитика.

### P0 — починить заявленное, иначе audio/Gemini нельзя отдавать

1. Включить `gemini` в `get_transcription_provider()`.
2. Добавить в `Settings` поля нарезки аудио (`AUDIO_TRANSCRIPTION_CHUNK_SECONDS`, overlap, `effective_*`) и `CHUNK_SEMANTIC_MIN_CHARS`, если код их читает.
3. Свести default провайдера ASR: код `mock`, `.env.example` `openai`.
4. Тест: factory принимает все Literal-значения; split_audio не ходит в отсутствующие атрибуты.

### P1 — закрыть разрыв project vs batch (главный объём дописывания)

Перенести на проект (API + UI), не писать заново:

1. Детальная очередь: список `processing-queue.sources`, recover застрявших документов.
2. Дашборд проекта: сейчас 3 KPI, бэкенд `build_project_dashboard` уже отдаёт полный payload — вывести виджеты из `BatchDashboardResearchWidgets`.
3. Audience portrait / PR strategy / full-report на вкладке отчёта.
4. Public link + страница `/report/:token`.
5. Interview units: `GET /projects/{id}/interview-units` + вкладка (сейчас «units» = сущности).
6. Message lab и сравнение сегментов — project-scoped эндпоинты (сейчас только `/batches/{id}/...`).
7. Экспорты dashboard/report (CSV/PNG/zip/xlsx/ppt) с project id.

Это тот набор, после которого продукт перестаёт выглядеть как «отчёт + загрузка» и становится аналитическим кабинетом.

### P2 — качество пайплайна и данные

1. Сервис эмбеддингов для `text_chunks` + простой retrieval endpoint (схема и индекс уже есть).
2. Реальный `EXTERNAL_RESEARCH_PROVIDER=http` + ручной запуск с вкладки, не только статьи внутри LLM-отчёта.
3. Регенерация OpenAPI (`schema.d.ts`) и выравнивание CLAUDE.md / README.
4. Poll на source-страницах до завершения, а не жёсткие 90 с.

### P3 — платформа (когда появится внешний доступ)

1. Auth (хотя бы API key / single-user token) и закрытый CORS.
2. Object storage вместо local disk.
3. Выпил или прятание legacy Materials/Analytics из навигации.
4. Постепенный вывод `/batches` после завершения P1.

---

## Что не начинать сейчас

- Новый batch-UX: путь сознательно выключен.
- Переписывание PR-отчёта с нуля: генератор уже большой и работает при наличии ключа.
- RAG/чат по корпусу: пока чанки без embeddings это пустая фича.
- Удаление batches/materials: ещё держат аналитику и demo.

---

## Ориентир «готово к следующему этапу»

Можно переходить от «дописать модули» к новым продуктам, когда:

- [ ] Gemini и audio-chunk Settings работают и покрыты тестом
- [ ] Пользователь на `/projects/:id` видит очередь по файлам, дашборд, portrait/strategy и ссылку на публичный отчёт
- [ ] Message lab и interview units доступны без batch URL
- [ ] Legacy Materials/Analytics убраны из основной навигации (или явно помечены как demo)
- [ ] OpenAPI-типы фронта совпадают с текущими роутами

До этого новые модули лучше класть **на project API + ProjectDetailPage**, а не в `research_batches.py` / `BatchDetailPage.tsx`.
