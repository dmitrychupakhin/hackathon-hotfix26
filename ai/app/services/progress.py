"""Public operational steps, without prompts, document text or model reasoning."""

import time


class Progress:
    def __init__(self, emit):
        self.emit = emit
        self.counter = 0
        self.package_id = None
        self.active = {}

    async def start(self, key, kind, title, *, question_ids=None, details=None):
        self.counter += 1
        step = {
            "schema_version": 1,
            "step_id": f"step-{self.counter}",
            "kind": kind,
            "status": "started",
            "title": title,
            "message": title,
            "package_id": self.package_id,
            "question_ids": question_ids or [],
            "details": details or {},
            "elapsed_seconds": None,
        }
        self.active[key] = (step, time.monotonic())
        await self.emit("harness.step", step)

    async def finish(self, key, *, status="completed", message=None, details=None):
        item = self.active.pop(key, None)
        if item is None:
            return
        step, started = item
        await self.emit(
            "harness.step",
            {
                **step,
                "status": status,
                "message": message or step["title"],
                "details": {**step["details"], **(details or {})},
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )

    async def handle(self, event, data):
        if event == "package.started":
            await self.finish("prepare", status="failed", message="Подготовка не завершена")
            self.package_id = data["package_id"]
            await self.start(
                "prepare",
                "prepare",
                "Подготовка документов и контекста",
                details={"questions": data["questions"]},
            )
        elif event == "context.prepared":
            await self.finish("prepare", message="Контекст подготовлен", details=data)
        elif event == "context.evidence_compacted":
            key = f"compact:{self.counter}"
            await self.start(
                key, "evidence_scan", "Подготовлены компактные доказательства", details=data
            )
            await self.finish(
                key,
                message="Дословные выдержки подготовлены; оригиналы и конкурирующие значения сохранены",
            )
        elif event == "context.reduced":
            # Abandon review/preparation from the rejected attempt before rebuilding it.
            await self.finish(
                "review", status="failed", message="Контекст критика превышает окно модели"
            )
            await self.finish(
                "prepare", status="failed", message="Требуется подготовить меньшие порции"
            )
            await self.start(
                "context_reduction",
                "context_reduction",
                "Уменьшение контекста и повторная подготовка",
                details=data,
            )
            await self.finish(
                "context_reduction",
                message="Лимит уменьшен минимум вдвое; исходники будут обработаны заново меньшими порциями",
            )
        elif event == "context.reduction_exhausted":
            await self.finish(
                "review", status="failed", message="Проверка остановлена из-за лимита контекста"
            )
            await self.finish(
                "prepare",
                status="failed",
                message="Контекст не удалось подготовить в пределах лимитов",
            )
            await self.start(
                "context_reduction",
                "context_reduction",
                "Лимит уменьшения контекста исчерпан",
                details=data,
            )
            await self.finish(
                "context_reduction",
                status="failed",
                message="Неподтверждённые ответы останутся «не знаю»",
            )
        elif event == "llm.started" and data["stage"] != "semantic_review":
            titles = {
                "answer": "Формирование ответа или выбор инструментов",
                "plain": "Обычный ответ модели без дополнительных проверок",
                "baseline": "Ответ без дополнительных проверок",
                "raw": "Ответ на исходные вопросы",
                "evidence_scan": "Поиск доказательств в порции документов",
                "verification_scan": "Независимый поиск подтверждений и опровержений",
                "chat_plan": "Подготовка независимых частей ответа",
            }
            await self.start(
                f"llm:{data['call']}",
                data["stage"],
                titles.get(data["stage"], "Запрос к модели"),
                details={
                    "call": data["call"],
                    "max_calls": data["max_calls"],
                    **(data.get("progress") or {}),
                },
            )
        elif event == "llm.finished":
            good = data["finish_reason"] in {"stop", "tool_calls"}
            await self.finish(
                f"llm:{data['call']}",
                status="completed" if good else "failed",
                message="Ответ модели получен; это ещё не подтверждение его правильности"
                if good
                else "Модель не вернула полный ответ",
            )
        elif event == "llm.failed":
            await self.finish(
                f"llm:{data['call']}",
                status="failed",
                message="Запрос к модели не выполнен",
                details={"error_code": data["error_code"]},
            )
        elif event == "tool.started":
            titles = {
                "list_documents": "Просмотр списка документов",
                "read_document": "Чтение документа",
                "read_evidence": "Чтение исходного фрагмента",
                "search_documents": "Поиск по документам",
                "find_amendments": "Поиск изменений извещения",
                "calculate": "Проверяемое вычисление",
                "submit_answers": "Передача кандидатов на проверку",
            }
            await self.start(
                "tool",
                "tool",
                titles.get(data["name"], "Вызов инструмента"),
                details={"tool": data["name"]},
            )
        elif event in {"tool.completed", "tool.failed"}:
            await self.finish(
                "tool",
                status="failed" if event == "tool.failed" else "completed",
                message="Инструмент отклонил запрос"
                if event == "tool.failed"
                else "Инструмент выполнен",
            )
        elif event == "validation.started":
            await self.start(
                "validation",
                "validation",
                "Проверка цитат, чисел и полноты источников",
                question_ids=[data["id"]],
            )
        elif event == "validation.finished":
            await self.finish(
                "validation",
                status="completed" if data["passed"] else "failed",
                message="Проверки кодом пройдены"
                if data["passed"]
                else "Проверки кодом выявили ошибки",
                details={"failed_checks": data["failed_checks"]},
            )
        elif event == "review.started":
            await self.start(
                "review",
                "semantic_review",
                "Смысловая проверка ИИ-критиком",
                question_ids=data["question_ids"],
            )
        elif event == "review.finished":
            await self.finish(
                "review",
                status="completed" if data["passed"] else "failed",
                message="Критик подтвердил ответы"
                if data["passed"]
                else "Критик не подтвердил все ответы",
                details={"rejected_question_ids": data["rejected_question_ids"]},
            )
        elif event == "repair.started":
            await self.start(
                "repair",
                "repair",
                "Назначена попытка исправления",
                question_ids=data["question_ids"],
                details={"attempt": data["attempt"], "max_repairs": data["max_repairs"]},
            )
            await self.finish("repair", message="Ошибки переданы в следующий раунд генерации")
        elif event == "answer.completed":
            answer = data["answer"]
            await self.start(
                "result", "result", "Сохранение результата вопроса", question_ids=[answer["id"]]
            )
            await self.finish(
                "result",
                message="Нужно уточнить вопрос"
                if answer.get("clarification_question")
                else "Система воздержалась от ответа"
                if answer["status"] == "не знаю"
                else "Результат сохранён",
                details={"answer_status": answer["status"], "origin": answer["origin"]},
            )

    async def close(self, run_status, error=None):
        status = run_status if run_status in {"cancelled", "interrupted"} else "failed"
        for key in list(self.active):
            await self.finish(
                key,
                status=status,
                message={
                    "cancelled": "Шаг отменён",
                    "interrupted": "Шаг прерван остановкой сервиса",
                }.get(status, "Шаг не завершён"),
                details={"error_code": (error or {}).get("code", "step_incomplete")},
            )
