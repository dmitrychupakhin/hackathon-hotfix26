# WebSocket: коды событий и русские названия

Один envelope для run и импорта:

```json
{"seq":42,"run_id":"UUID ресурса","type":"harness.step","created_at":"2026-11-07T12:00:00+00:00","data":{}}
```

Поле `run_id` исторически так называется и в потоке file-import содержит import ID. Не смешивайте потоки: ключ курсора — `(тип ресурса, id)`.

## Подключение

- Run: `POST /api/v1/runs/{id}/ws-ticket` → `WS /api/v1/runs/{id}/ws?ticket=...&after=0`.
- Import: `POST /api/v1/file-imports/{id}/ws-ticket` → `WS /api/v1/file-imports/{id}/ws?ticket=...&after=0`.
- HTTP replay: соответствующий `GET .../{id}/events?after=...&limit=100`. Следующую страницу читать до пустой выдачи.
- Билет120с; новый при переподключении. Неправильный владелец/ресурс/тип/origin —close1008.
- Терминальный event затем close1000. При разрыве задача продолжает работать, отмена отдельным POST.
- Доставка может повториться при неверном курсоре клиента. Дедупликация поseq, шаг UI обновлять поstep_id.

Поток передаёт операционные шаги и готовые ответы. Непроверенные текстовые токены LLM по символам не стримятся.

## Чат через Django и браузер

В Django ID запуска чата и ID запуска AI различаются. Браузер получает билет через
`POST /api/chats/{chat_id}/runs/{django_run_id}/ws-ticket` и использует **возвращённый**
`path` (`/ai/api/v1/runs/{ai_run_id}/ws`), не строит его из Django ID. Сервисный ключ
остаётся на сервере. В production `/ai/.../ws` проксируется nginx с WebSocket Upgrade;
при прямом запуске Next на порту 3000 серверный `AI_ORIGIN` задаёт адрес AI для proxy.

Дополнительный owner-scoped replay доступен через
`GET /api/chats/{chat_id}/runs/{django_run_id}/events?after=0&limit=100`.
Пока AI ID ещё не назначен, возвращается `[]`. Этот HTTP endpoint использует ту же
авторизацию Django, что и чат. Если WS недоступен, интерфейс получает реальные
события через HTTP раз в 2 секунды. Это резервный транспорт, а не искусственный
таймер этапов. При исправном WS HTTP replay нужен при подключении и завершении.

WS и HTTP используют общий `seq`: повторные записи игнорируются, heartbeat его не
меняет. На переподключении выдаётся новый билет с последним `after`; после пяти
неудачных WS-подключений автоматические попытки WS прекращаются, HTTP продолжает
работать. При открытии существующего чата `latest_run` позволяет восстановить
наблюдение, включая этапы завершённого запуска. Перед остановкой по терминальному
статусу Django клиент дочитывает страницы журнала, чтобы не потерять последние
этапы, пришедшие между опросом статуса и закрытием WS.

Интерфейс не обязан показывать каждый вызов и повтор. Текущий чат группирует
`harness.step` по фазам. Чтение источников и решение критика — разные фазы:

| Фаза UI | `data.kind` |
| --- | --- |
| Подготовка | `chat_plan`, `prepare`, `context_reduction` |
| Поиск в источниках | `evidence_scan` |
| Ответ модели | `answer`, `plain`, `baseline`, `raw` |
| Инструменты | `tool` |
| Проверки кодом | `validation` |
| Независимая проверка источников | `verification_scan` |
| Проверка критиком | `semantic_review` |
| Исправление | `repair` |
| Результат | `result` |

Заголовок и состояние берутся из события, а не из предположения фронта. Все повторы
остаются в полном журнале. `running` — только статус запуска, отдельным WS-событием
он не является. До создания AI запуска подготовка исходных файлов на входе
`POST /chat-runs` ещё не входит в поток run; на этом этапе ticket может вернуть 409.

## Основной UI: harness.step

```json
{"schema_version":1,"step_id":"step-4","kind":"verification_scan","status":"started","title":"Независимый поиск подтверждений и опровержений","message":"Независимый поиск подтверждений и опровержений","package_id":"UUID","question_ids":["P01-05"],"details":{"call":9,"max_calls":48,"batch":2,"batches":4},"elapsed_seconds":null}
```

Начало/конец одной операции имеют одинаковыйstep_id. Статусы: `started` выполняется, `completed` завершён, `failed` ошибка/проверка не пройдена, `cancelled` отменён, `interrupted` прерван. Завершённый шаг содержитelapsed_seconds. Названия/сообщения формируютсякодом, без рассуждений модели и текста документов. Технические события могут содержать кандидаты/источники: их не нужно показывать как итоговый ответ.

| data.kind | Русское название |
| --- | --- |
| `prepare` | Подготовка документов и контекста |
| `chat_plan` | Подготовка независимых частей ответа |
| `evidence_scan` | Поиск доказательств в порции документов |
| `verification_scan` | Независимый поиск подтверждений и опровержений |
| `answer` | Формирование ответа или выбор инструментов |
| `plain` | Обычный ответ модели без дополнительных проверок |
| `baseline` | Ответ без дополнительных проверок |
| `raw` | Ответ на исходные вопросы |
| `tool` | Название по details.tool, таблица ниже |
| `validation` | Проверка цитат, чисел и полноты источников |
| `semantic_review` | Смысловая проверка ИИ-критиком |
| `repair` | Назначена попытка исправления |
| `context_reduction` | Уменьшение контекста и повторная подготовка |
| `result` | Сохранение результата вопроса |

| details.tool | Русское название |
| --- | --- |
| `list_documents` | Просмотр списка документов |
| `search_documents` | Поиск по документам |
| `read_document` | Чтение документа |
| `read_evidence` | Чтение исходного фрагмента |
| `find_amendments` | Поиск изменений извещения |
| `calculate` | Проверяемое вычисление |
| `submit_answers` | Передача кандидатов на проверку |

Details может содержатьcall/max_calls, batch/batches, failed_checks, rejected_question_ids, attempt/max_repairs, старое/новое окно, answer_status/origin. Repair завершён — только назначено исправление; следующие steps покажут фактическую генерацию. Completed у запроса к модели — получен ответ, а не доказана истинность. Failed проверки может продолжиться исправлением. Plain использует общий envelope harness.step, но не выполняет harness-проверок.

## Технические события run

| type | Русское значение |
| --- | --- |
| `run.queued` | Запуск в очереди |
| `run.started` | Запуск начат |
| `run.cancel_requested` | Запрошена отмена |
| `run.completed` | Запуск завершён |
| `run.failed` | Ошибка запуска |
| `run.cancelled` | Запуск отменён |
| `run.interrupted` | Запуск прерван остановкой/перезапуском |
| `package.started` | Начата обработка закупки или новая попытка контекста |
| `context.prepared` | Контекст подготовлен; фактические размеры чанков и покрытие |
| `context.batch_scanned` | Порция обработана; stage, номер порции, provisional_facts и coverage |
| `context.scan_invalid` | Результат сканера отклонён: стадия, порция, попытка, ID вопросов и безопасные коды ошибок |
| `context.scan_retry` | Повтор чтения сбойной порции для указанных вопросов; не новая генерация ответа |
| `context.reduced` | Окно уменьшено после context_length_exceeded |
| `context.reduction_exhausted` | Лимит уменьшения/минимальное окно достигнуты |
| `llm.started` | Запрос к модели начат; оценка входа, окно и резерв |
| `llm.finished` | Ответ получен; фактическийusage/finish_reason |
| `llm.failed` | Ошибка запроса к модели |
| `tool.started` | Инструмент начат |
| `tool.completed` | Инструмент выполнен |
| `tool.failed` | Инструмент отклонил запрос |
| `validation.started` | Начаты проверки кодом |
| `validation.finished` | Проверки завершены; смотреть passed |
| `validation.failed` | Кандидат отклонён кодом или критиком |
| `review.started` | Начата смысловая проверка |
| `review.finished` | Критик завершил проверку; смотреть passed |
| `review.retry` | Назначен один повтор запроса ИИ-проверки после транспортного сбоя: stage, attempt=2, max_attempts=2, error_code, progress с порцией |
| `repair.started` | Назначено исправление указанных вопросов |
| `answer.completed` | Сохранён окончательный результат вопроса |

Для ошибки сканера сохраняются `context.scan_invalid` и, если бюджет позволяет, `context.scan_retry`: максимум две попытки одной порции для конкретного вопроса. Поля — `stage` (`evidence_scan` или `verification_scan`), `batch`, `batches`, `attempt`, `question_ids`; у ошибки также `issues=[{id,reason}]`, у повтора `max_attempts=2`. Коды `reason`: `invalid_json`, `invalid_selections`, `unexpected_question_ids`, `missing_question`, `duplicate_question`, `invalid_span_ids`, `foreign_span_ids`, `invalid_facts`. В этих событиях нет исходного текста, произвольного ответа модели или неизвестных ID, возвращённых моделью. Это диагностические события, а не новые этапы подтверждения. Неполное независимое покрытие отражается в `coverage.failed_question_ids`; неподтверждённые вопросы не выдаются как проверенные.

В `answer.completed.data.answer` содержатся status, answer, evidence, calculation, checks и optional `clarification_question` для запроса уточнения при status «не знаю». В `run.completed` — терминальный статус/метрики; полные ответы читать GET run. Осторожный fallback — корректный результат, а не ошибка процесса.

При большом наборе `context.evidence_compacted` означает «Подготовлены компактные доказательства»: точные исходные выдержки и предварительные факты уплотнены для следующего запроса, оригиналы сохранены. Поля — `original_selected_blocks`, `source_excerpts`, `provisional_facts`, `coverage`, `reason`. Это не положительный вердикт. UI получает соответствующий `harness.step` с `kind=evidence_scan`; подробности — [large-context.md](large-context.md). Во время сравнения Django проектирует эти же публичные этапы в `progress.run_states[mode].step`, не пересылая сырой текст инструментов. Поле `metrics_final=false` отличает число начатых запросов/учтённый usage от итоговых метрик.

Событие также содержит `data.question={id,package_id,text}`, `question_index` (с нуля), `question_count`. Для нескольких вопросов не заменяйте ответ предыдущего пункта новым событием: накапливайте по `answer.id`, сортируйте по `question_index`, повторные seq игнорируйте. Отдельный fallback не отменяет принятые ответы. В `/chat-runs` с документами независимые части выделяет модель из полного сообщения; код проверяет отсутствие потерь текста, а не угадывает вопросы по строкам. Для нескольких частей IDs имеют вид `{message_id}.q01`, `.q02`, …; одна часть сохраняет message_id. Техническое `chat.planned` содержит `data.units` после сохранения плана; `chat.plan_rejected` — номер неудачной попытки (максимум две). До `chat.planned` количество частей ещё неизвестно, `run.queued.questions=1` означает входное сообщение. Готовые сообщения Django содержат `answer_payload.parts` и привязку `citation_ids` для каждого пункта; общие лимиты запуска на число пунктов не умножаются. `chat_plan` — стадия `llm.started/finished` и kind публичного `harness.step`; исходный текст в публичные шаги не попадает.

## События импорта файлов

| type | Русское название | Данные |
| --- | --- | --- |
| `file_import.queued` | Импорт в очереди | total |
| `file_import.started` | Импорт начат | total |
| `file.started` | Чтение и проверка исходника | file_id, name, version |
| `file.cache_hit` | Готовая TXT-копия найдена | file_id, version, partial, characters |
| `file.text_extracted` | Текст извлечён и сохранён | file_id, version, partial, characters |
| `file.ready` | Файл подготовлен | file_id, processed, total |
| `file_import.completed` | Все файлы опубликованы в закупке | status, processed, total |
| `file_import.failed` | Ошибка импорта | error, processed, total |
| `file_import.cancelled` | Импорт отменён | error, processed, total |
| `file_import.interrupted` | Импорт прерван | status/reason/error |

file.ready означает готовность артефакта в кеше, а не публикацию части пакета. Начинать вопросы нужно послеfile_import.completed. При неудаче позднего файла пакет остаётся прежним. Partial артефакт не доказывает отсутствие сведений; предупреждения есть в metadata документа.

## Служебные сообщения и прогресс

`heartbeat` каждые15с: `{"type":"heartbeat","cursor":42}`. Строка клиента `ping` получает `{"type":"pong","cursor":42}`. Эти сообщения не имеютseq и не сохраняются; курсор не продвигается поheartbeat.

Не вычисляйте общий процент по числу текущихLLM-вызовов: tools, критик и repair добавляют шаги динамически. Показывайте завершённые вопросы X/N, текущую стадию, порцию X/Y и запрос X/max_calls. При run.interrupted оставшиеся started UI-шаги помечаются прерванными: при аварийном завершении процесса отдельных closing events может не быть.

Сроки и лимиты: [README](../README.md#окно-модели-попытки-и-время), фактическая конфигурация `/api/v1/info`.
