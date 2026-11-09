# hackathon-hotfix26

## Локальный запуск

Нужны Docker Compose и Node.js 22.

```bash
cp .env.example .env
```

В `.env` задайте `APIMIRA_API_KEY` для запросов к AI и `AI_SERVICE_KEY` — общий ключ Django и AI (например, результат `openssl rand -hex 32`). Затем из корня проекта:

```bash
docker compose up -d --build
```

Приложение: http://localhost, Django API: http://localhost/api/docs/swagger/, AI API: http://localhost/ai/docs.

В Docker frontend собирается как production. Для разработки Next.js с обновлением при правках запустите в другом терминале:

```bash
cd frontend
npm ci
API_ORIGIN=http://127.0.0.1 npm run dev
```

Откройте http://localhost:3000. API и WebSocket идут через nginx на `localhost:80`. Django запускается через `runserver` и использует смонтированный `backend/`; AI запускается без автоматической перезагрузки.

Остановить контейнеры: `docker compose down`.
