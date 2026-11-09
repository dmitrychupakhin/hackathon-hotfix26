# Контракт backend ↔ AI

Этот файл — точка входа для backend-разработчика. Сервисная база URL локально `http://127.0.0.1:8010`, внутри deployment задаётся конфигурацией. Действующие схемы HTTP: `/docs` и `/openapi.json`. Коды/русские названия событий: [websocket-events.md](websocket-events.md).

## 1. Ответственность и создание БД

**Backend/deployment создаёт PostgreSQL database и применяет `ai/sql/001_ai_schema.sql`.** AI при старте только подключается, проверяет версию схемы и захватывает advisory lock единственного worker. При отсутствии DSN/схемы он не запускается; Django migrations и таблицы пользователей не изменяются.

AI и backend используют одну БД. Разделение записей:

| Объект | Кто записывает | Кто читает |
| --- | --- | --- |
| Django auth/profile | Backend | Backend; AI получает проверенный user ID и текст промпта через API |
| `ai.files` | Backend | AI и backend |
| `ai.objects` | AI через HTTP API | AI; backend может читать для своих задач |
| `ai.events` | Только AI | AI; backend может читать, но рекомендуем HTTP/WS для owner checks |

Backend не должен напрямую менять run/session/package JSON или писать события: порядок исполнения и seq гарантирует один AI worker. Общая БД не заменяет разграничение владельцев. Для отдельной application-роли пример прав после создания схемы (имя роли заменить deployment-значением):

```sql
GRANT USAGE ON SCHEMA ai TO ai_app;
GRANT SELECT ON ai.schema_version, ai.files TO ai_app;
-- PostgreSQL requires UPDATE privilege on at least one column for SELECT FOR SHARE.
-- AI does not update this field; permission is needed to lock a source revision.
GRANT UPDATE(updated_at) ON ai.files TO ai_app;
GRANT SELECT, INSERT, UPDATE ON ai.objects TO ai_app;
GRANT SELECT, INSERT ON ai.events TO ai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ai TO ai_app;
```

`UPDATE(updated_at)` для AI — техническое право PostgreSQL на блокировку строки `FOR SHARE`; код AI каталог не обновляет. SHA/версия/путь по этой роли изменяться не могут. Роль backend должна иметь INSERT/UPDATE/SELECT `ai.files`; SQL применяется владельцем схемы. DSN AI задаётся секретом `AI_DATABASE_URL`. По умолчанию никакие креды Django автоматически из БД не читаются.

## 2. Файл по ID

Backend сохраняет файл на volume и регистрирует текущую ревизию в `ai.files`:

| Колонка | Тип/правило |
| --- | --- |
| `owner` | Строковый ID пользователя из backend; совпадает с `X-User-ID` |
| `id` | Непрозрачный ID до128 символов `[A-Za-z0-9_-]`, первый символ буквенно-цифровой |
| `version` | Непустая версия до128 символов; менять при изменении содержимого |
| `updated_at` | PostgreSQL timestamptz, UTC |
| `filename` | Обычное имя с расширением, до200 символов, без пути |
| `relative_path` | Нормализованный POSIX-путь относительно `AI_SOURCE_ROOT`, без `..` и symlink |
| `sha256` | SHA-256 оригинальных байтов, 64 строчные hex-цифры |
| `media_type` | MIME, например `application/pdf` |

Пример (тестовые параметры, не реальные пользовательские данные):

```sql
INSERT INTO ai.files(owner,id,version,filename,relative_path,sha256,media_type)
VALUES ('user-123','file-456','v1','notice.pdf','user-123/file-456/v1/notice.pdf',
        '<64 lowercase hex characters>','application/pdf');
```

Файлы пишутся backend атомарно. Рекомендуется новый путь для каждой версии; нельзя переиспользовать `version`/SHA для изменённых байтов. AI перечитывает и проверяет фактический SHA даже при cache hit. Перед публикацией блокирует/перепроверяет строки каталога в транзакции. Неизменная версия при повторном импорте сохраняет document ID и package revision.

Для Docker: папка backend на хосте указывается `AI_SOURCE_DIR`, монтируется `/source:ro`. AI работает с локальной копией и `extracted.txt` в частном `/data/files`. Произвольные URL и пути из HTTP-запроса не принимаются. Если backend использует объектное хранилище, ему нужен адаптер предоставления версии в общем volume; готового S3-адаптера здесь нет.

## 3. Последовательность HTTP

Все запросы ниже имеют префикс `/api/v1` и заголовки:

```http
X-AI-Service-Key: <server-to-server secret>
X-User-ID: user-123
Content-Type: application/json
```

1. `POST /packages` с `{"code":"P01","name":"Закупка"}` → `201`, сохранить `package_id`.
2. `POST /packages/{package_id}/documents/by-id` с `{"file_ids":["file-456"]}` → `202`, сохранить `import_id`.
3. Подключить поток импорта или читать `GET /file-imports/{import_id}`. Дождаться `completed`; ошибка/partial должны быть видны пользователю. Импорт публикует пакет целиком, не по одному файлу. При ошибке второго файла первый может уже быть готов в кеше, но пакет останется прежним.
4. `POST /sessions` с `{"package_id":"...","title":"Закупка"}` → `201`, сохранить `session_id`.
5. `POST /sessions/{session_id}/messages` → `202`, сохранить `run_id`:

```json
{
  "mode": "harness",
  "text": "Сколько рублей составит обеспечение исполнения контракта?",
  "question_id": "P01-05",
  "model": "openai/gpt-6-luna",
  "system_prompt": "Общие инструкции из профиля пользователя",
  "options": {"context":"auto","semantic_review":true,"max_repairs":1,"max_calls":48,"timeout_seconds":600}
}
```

Для обычного запроса меняется только `mode` на `plain`. Оба режима возвращают одинаковую оболочку run, но plain не выполняет проверки/tools/критика/repair. Не включайте в общий профиль обязательные вызовы tools: они доступны только в harness. Null/отсутствующий prompt использует встроенный prompt выбранного режима. В чате остаются все сообщения; в модель передаётся краткое состояние и привязки источников.

6. Подключить поток run либо читать `GET /runs/{run_id}`. Итог — `result.answers`; полные доказательства/проверки внутри каждого ответа, аудит фрагментов — `result.evidence_audit`.
7. Для пакетной обработки использовать `POST /runs` с `questions:[{id,package_id,text}]` или `POST /datasets/{id}/runs`. Для сравнения режимов лучше отдельные runs на одном наборе: последовательные сообщения одного чата имеют разную историю и не являются одинаковым входом.

`Idempotency-Key` используется в runs/messages/dataset runs. Тот же ключ с иным mode/prompt/вопросом —409. По file import идемпотентного HTTP-ключа нет; новый job может использовать уже готовый кеш и не менять источник.

## 4. Ответы и отображение

Статус run: `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`. Completed не обещает верные ответы на все вопросы: возможен честный отказ.

Статус каждого ответа: `ответ`, `расхождение`, `нет в документах`, `не знаю`. `quote`/`file` — основное доказательство для CSV, `evidence` — все исходные фрагменты с координатами/хешами/страницами, `calculation` — операция и операнды, `checks` — результаты кода/критика. `origin=fallback` и `reason` отличают отказ сервиса. Если вопрос неоднозначен, harness может вернуть status «не знаю» с `clarification_question`: покажите этот уточняющий вопрос вместо пустого ответа. `checks=[]` в plain не означает подтверждение факта.

`run.context_budget`, `prompt_hashes`, `source_revisions`, `GET /runs/{id}/inputs` фиксируют фактический вход. Изменение файлов или профиля применяется к следующему run. При изменении документа сначала повторить by-ID import; AI не перечитывает каталог сам в каждом вопросе. Изменённые версии не подменяют старые snapshots; UI может пометить старый ответ как основанный на прежнем источнике.

## 5. WebSocket, отмена и время

Backend получает `POST /runs/{id}/ws-ticket` или `/file-imports/{id}/ws-ticket`, передаёт браузеру только `ticket` и `path`. Браузер подключается к `path?ticket=...&after=lastSeq`; сервисный ключ в браузер не попадает. Origin должен быть в `AI_ALLOWED_ORIGINS`.

Билет действует120с и привязан к владельцу, ID и типу ресурса. Import-ticket не подходит run. После переподключения нужен новый билет. Сохраняемые события имеют монотонный `seq`; heartbeat/pong не сохраняются. При разрыве вычисление продолжается. Отмена — отдельный POST `/runs/{id}/cancel` или `/file-imports/{id}/cancel`.

Импорт:300с на job, парсер:45с/файл, универсальный run по умолчанию:600с включая очередь, один HTTP-вызов модели:180с. Адаптер `/chat-runs` для документов задаёт `timeout_seconds` из `AI_RUN_TIMEOUT_SECONDS` (по умолчанию 1200с, не более 3600с); чат без документов ограничен 600с и серверным потолком. Общие лимиты48calls/8rounds/1repair/5contextreductions. Не прошивайте числа в UI: `/info` сообщает конфигурацию, конкретный run содержит options и metrics. Атомарная публикация и ограниченная очистка worker могут закончиться после запроса отмены; терминальный статус приходит событием.

## 6. Оценка результата

После terminal run можно передать `POST /runs/{id}/evaluate`:

```json
{"reference_answers":[{"id":"P01-05","package":"P01","status":"ответ","kind":"num","expected":[90000],"type":"расчёт"}]}
```

Эталоны должны соответствовать всем вопросам run. Они доступны только оценщику и не включаются в генерацию. Формат организаторов — `answers_public.json`; автоматического импорта произвольного CSV эталонов нет.

Для before/after получить два evaluation ID, передать `POST /comparisons` с `before_evaluation_id`/`after_evaluation_id`. Одинаковые модель, вопросы, версии, история и gold обязательны. Индекс доверия от−100до100; критик не заменяет эталонную оценку.

## 7. Ошибки и готовность интеграции

HTTP ошибка: `{"error":{"code":"...","message":"..."}}`; валидация FastAPI — `detail`. 401 — сервисная авторизация,404 — отсутствует/чужой ресурс,409 — конфликт состояния,413 — размер,422 — формат/бюджет,429 — очередь,503 — недоступность. Ошибки после202 находятся в job/run.error и терминальном событии.

Backend нужно реализовать: создание БД и SQL, регистрацию source records/volume, профильные prompt и authheaders, привязку package/session/run/import IDs в UI, передачу WS-билетов, обработку статусов/partial/версий и отдельную оценку. AI-часть не меняет backend-код и не создаёт PostgreSQL database автоматически.


## Defaults модели и провайдера

Во всех runs/messages/dataset-runs поддержаны optional `model` и `base_url`. Отсутствие/null берёт `APIMIRA_MODEL` и `APIMIRA_BASE_URL` из окружения. В текущей стандартной конфигурации это `openai/gpt-6-luna` и `https://apimira.com/v1`; Swagger показывает эффективные defaults сервера. Явный ID модели отправляется настроенному провайдеру; список моделей для фронтенда хранится в Django. Явный адрес проверяется по `AI_ALLOWED_BASE_URLS`, посторонний адрес даёт 422 до запроса модели. Секрет APIMIRA_API_KEY остаётся на сервере; в base_url ключ/query не допускаются. `GET /info` сообщает default-значения и доступные метаданные провайдера, `run.model/base_url` — фактически использованные. Разные провайдеры не сравниваются как честный before/after. Короткий список шести Model IDs приведён в README и examples поля model в Swagger.
