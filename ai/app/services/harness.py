import asyncio
import hashlib
import json
import re
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings
from app.domain import (
    Answer,
    AnswerStatus,
    CandidateBatch,
    Check,
    DomainError,
    Package,
    Question,
    RunCreate,
)
from app.infrastructure.llm import ApiMira, ChatModel, Usage, estimate_tokens
from app.services.chat_questions import ChatPlan, questions_from_plan
from app.services.citation_anchors import attach_plain_anchor
from app.services.context import compact_sources, source_batches
from app.services.documents import document_text_complete
from app.services.facts import FactLedger
from app.services.model_limits import MIN_CONTEXT_WINDOW
from app.services.tools import ToolBox, tool_schemas
from app.services.validation import unknown, validate

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
PROMPT_NAMES = ("baseline", "harness", "critic", "scan", "plain", "chat", "chat_plan")
TRANSIENT_REVIEW_ERRORS = {
    "provider_timeout",
    "upstream_timeout",
    "provider_unreachable",
    "service_unavailable",
}


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def prompt_versions():
    return {name: hashlib.sha256(prompt(name).encode()).hexdigest() for name in PROMPT_NAMES}


def resolve_prompts(system_prompt: str | None = None, mode="harness"):
    templates = {name: prompt(name) for name in PROMPT_NAMES}
    if system_prompt is not None:
        templates[mode] = system_prompt
    return templates


def json_output(text: str | None):
    if not text:
        raise ValueError("Empty model output")
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", value, re.S)
    if fenced:
        value = fenced.group(1)
    return json.loads(value)


class Harness:
    def __init__(
        self, model: ChatModel, settings: Settings, request: RunCreate, emit, cancel: asyncio.Event
    ):
        self.model = model
        self.settings = settings
        self.request = request
        self.emit = emit
        self.cancel = cancel
        self.usage = Usage()
        self.accepted: dict[str, Answer] = {}
        self.raw_outputs: list[dict] = []
        self.templates = resolve_prompts(request.system_prompt, request.mode)
        self.context_window = settings.context_window
        self.context_reductions = 0
        self.repair_attempts: dict[str, int] = {}
        self.answer_rounds: dict[str, int] = {}
        self.fact_ledger = FactLedger()
        self.scan_coverage = {}
        # Enabled only by the authenticated chat adapter, never by comparisons.
        self.chat_return_code_checked = False
        self.package_audits = {}
        self._audit_package = None
        self._audit_tools = None
        self._audit_attempt = None
        self._audit_window = None

    def audit_state(self):
        """Detached evidence/coverage history for every source planning attempt."""
        if self._audit_package is not None:
            package = self._audit_package
            entry = self.package_audits[package.id]
            entry["attempts"][self._audit_attempt] = {
                "attempt": self._audit_attempt + 1,
                "context_window_tokens": self._audit_window,
                "fact_ledger": self.fact_ledger.as_list(),
                "coverage": json.loads(json.dumps(self.scan_coverage)),
                "original_blocks": len(self._audit_tools.spans),
                "blocks_read": len(self._audit_tools.seen),
                "read_complete": self._audit_tools.complete_coverage,
                "accepted_question_ids": [
                    q.id
                    for q in self.request.questions
                    if q.package_id == package.id and q.id in self.accepted
                ],
            }
        return json.loads(json.dumps(self.package_audits, ensure_ascii=False))

    @property
    def output_limit(self):
        return min(
            self.request.options.max_output_tokens or self.settings.max_output_tokens,
            self.settings.max_output_tokens,
            max(256, self.context_window // 4),
        )

    def fits(self, messages, tools=None):
        estimate = estimate_tokens(messages) + (len(json.dumps(tools)) // 2 if tools else 0)
        return estimate + self.output_limit < self.context_window

    async def reduce_context(self, failed_input_estimate):
        # Both the prior ceiling and the rejected input estimate shrink by at least 2x.
        reduced = min(self.context_window // 2, failed_input_estimate // 2)
        if (
            self.context_reductions >= self.settings.max_context_reductions
            or reduced < MIN_CONTEXT_WINDOW
        ):
            await self.emit(
                "context.reduction_exhausted",
                {
                    "context_window_tokens": self.context_window,
                    "attempt": self.context_reductions,
                    "max_attempts": self.settings.max_context_reductions,
                    "min_context_window_tokens": MIN_CONTEXT_WINDOW,
                    "reason": "context_retry_exhausted",
                },
            )
            raise DomainError(
                "context_retry_exhausted",
                "Context reduction budget or minimum useful window reached",
                422,
            )
        previous = self.context_window
        self.context_window = reduced
        self.context_reductions += 1
        await self.emit(
            "context.reduced",
            {
                "previous_context_window_tokens": previous,
                "context_window_tokens": reduced,
                "failed_input_estimate": failed_input_estimate,
                "attempt": self.context_reductions,
                "max_attempts": self.settings.max_context_reductions,
                "reason": "context_length_exceeded",
            },
        )
        raise DomainError(
            "context_replan_required",
            "Rebuild context from original sources using the smaller budget",
            422,
        )

    async def invoke(
        self, messages, *, tools=None, stage="answer", progress=None, output_limit=None
    ):
        if self.cancel.is_set():
            raise asyncio.CancelledError
        remaining_calls = min(self.request.options.max_calls, self.settings.max_model_calls) - max(
            self.usage.calls, self.usage.transport_attempts
        )
        if remaining_calls <= 0:
            raise DomainError("call_budget_exhausted", "Model call budget exhausted", 422)
        estimate = estimate_tokens(messages) + (len(json.dumps(tools)) // 2 if tools else 0)
        reserved_output = min(self.output_limit, output_limit or self.output_limit)
        if estimate + reserved_output >= self.context_window:
            raise DomainError(
                "context_budget_exceeded",
                "Estimated context and reserved output exceed the configured model window",
                422,
            )
        self.usage.calls += 1
        await self.emit(
            "llm.started",
            {
                "stage": stage,
                "call": self.usage.calls,
                "max_calls": min(self.request.options.max_calls, self.settings.max_model_calls),
                "progress": progress,
                "estimated_input_tokens": estimate,
                "reserved_output_tokens": reserved_output,
                "context_window_tokens": self.context_window,
                "estimate_method": "characters_divided_by_two_plus_margin",
            },
        )
        try:
            reply = await self.model.complete(
                model=self.request.model or self.settings.model,
                messages=messages,
                max_tokens=reserved_output,
                tools=tools,
                base_url=self.request.base_url or self.settings.base_url,
                **(
                    {"transport_attempt_limit": remaining_calls}
                    if isinstance(self.model, ApiMira)
                    else {}
                ),
            )
        except asyncio.CancelledError as exc:
            self.usage.transport_attempts += getattr(exc, "transport_attempts", 0)
            self.usage.missing_usage_calls += 1
            raise
        except Exception as exc:
            self.usage.transport_attempts += getattr(exc, "transport_attempts", 0)
            self.usage.missing_usage_calls += 1
            await self.emit(
                "llm.failed",
                {
                    "call": self.usage.calls,
                    "stage": stage,
                    "error_code": exc.code if isinstance(exc, DomainError) else "provider_error",
                },
            )
            if (
                isinstance(exc, DomainError)
                and exc.code == "context_length_exceeded"
                and self.request.mode == "harness"
                and self.request.options.context != "full"
            ):
                await self.reduce_context(estimate)
            raise
        self.usage.add(reply)
        self.raw_outputs.append(
            {
                "stage": stage,
                "message": reply.message,
                "finish_reason": reply.finish_reason,
                "model": reply.model,
            }
        )
        await self.emit(
            "llm.finished",
            {
                "stage": stage,
                "call": self.usage.calls,
                "finish_reason": reply.finish_reason,
                "usage": reply.usage,
            },
        )
        if self.cancel.is_set():
            raise asyncio.CancelledError
        if reply.finish_reason == "length":
            raise DomainError("output_truncated", "Model output hit the response-token limit", 422)
        if reply.finish_reason not in {"stop", "tool_calls"}:
            raise DomainError("model_refusal", "Model did not produce a usable completion", 422)
        return reply

    async def accept(self, answer: Answer):
        self.accepted[answer.id] = answer
        question = next(q for q in self.request.questions if q.id == answer.id)
        await self.emit(
            "answer.completed",
            {
                "answer": answer.model_dump(mode="json"),
                "question": question.model_dump(mode="json"),
                "question_index": self.request.questions.index(question),
                "question_count": len(self.request.questions),
            },
        )

    async def plan_chat(self, original: Question):
        messages = [
            {"role": "system", "content": self.templates["chat_plan"]},
            {"role": "user", "content": original.text},
        ]
        for attempt in range(2):
            reply = await self.invoke(messages, stage="chat_plan")
            try:
                plan = ChatPlan.model_validate(json_output(reply.message.get("content")))
                return questions_from_plan(original.id, original.package_id, original.text, plan)
            except (ValidationError, ValueError, DomainError):
                await self.emit("chat.plan_rejected", {"attempt": attempt + 1})
                if attempt:
                    raise DomainError(
                        "invalid_chat_plan",
                        "Could not preserve the complete message in independently checkable units",
                        422,
                    ) from None
                # Keep the sole user message intact on retry. Replaying a bad plan,
                # an unsolicited tool call or a corrective user message can make
                # the model partition that text instead of the actual request.
                messages[0]["content"] += (
                    "\nThe prior partition was rejected. Partition ONLY the raw user message. "
                    'Return {"parts":[...]} preserving all its non-whitespace characters '
                    "exactly once, in order. Do not copy this instruction or invent IDs."
                )

    async def execute(self, packages: list[Package], history: list[dict] | None = None):
        if self.request.mode in {"plain", "raw", "baseline"}:
            # Same isolation/grouping as harness: exactly one direct generation
            # per procurement. Never mix unrelated procurements in one prompt.
            for package in packages:
                questions = [q for q in self.request.questions if q.package_id == package.id]
                if questions:
                    await self._baseline([package], history, questions=questions)
        else:
            for package in packages:
                questions = [q for q in self.request.questions if q.package_id == package.id]
                while pending := [q for q in questions if q.id not in self.accepted]:
                    await self.emit(
                        "package.started",
                        {"package_id": package.id, "code": package.code, "questions": len(pending)},
                    )
                    try:
                        await self._solve(package, pending, history or [])
                        break
                    except DomainError as exc:
                        if exc.code == "context_replan_required":
                            continue
                        if exc.code == "context_retry_exhausted":
                            for q in pending:
                                if q.id not in self.accepted:
                                    await self.accept(unknown(q.id, exc.code))
                            break
                        raise
        return self.results()

    def results(self, fallback_reason="No accepted answer"):
        return [
            self.accepted.get(q.id) or unknown(q.id, fallback_reason)
            for q in self.request.questions
        ]

    async def _baseline(self, packages, history=None, *, questions=None):
        questions = self.request.questions if questions is None else questions
        content = {
            "documents": [
                {"package_id": p.id, "file": d.name, "text": d.text}
                for p in packages
                for d in p.documents
            ],
            "questions": [q.model_dump() for q in questions],
        }
        if self.request.mode == "plain" and history:
            content["previous_dialogue_for_reference_only"] = history[-6:]
        text = json.dumps(content, ensure_ascii=False)
        if self.request.mode in {"baseline", "plain"}:
            instructions = (
                self.templates["chat"] if not content["documents"] else self.templates["baseline"]
            )
            text = instructions + "\n\n" + text
        messages = [{"role": "user", "content": text}]
        if self.request.mode == "plain":
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": self.templates["chat"]
                    if not content["documents"]
                    else self.templates["plain"],
                },
            )
        # Direct modes make one call and only parse the common submission format.
        reply = await self.invoke(messages, stage=self.request.mode)
        if self.request.mode == "raw":
            extracted = dict(
                re.findall(
                    r"^-\s+(?:\*\*)?([\w.-]+):(?:\*\*)?\s*(.*)$",
                    reply.message.get("content") or "",
                    re.M,
                )
            )
            for q in questions:
                await self.accept(
                    Answer(
                        id=q.id,
                        status=None,
                        answer=extracted.get(q.id, ""),
                        origin="raw",
                        reason="Raw output has no inferred status or evidence; inspect raw_outputs.",
                    )
                )
            return
        try:
            rows = json_output(reply.message.get("content"))["answers"]
            ids = [row["id"] for row in rows]
            if len(ids) != len(set(ids)) or set(ids) != {q.id for q in questions}:
                raise ValueError("Question IDs do not match")
            parsed = []
            for row in rows:
                if set(row) != {"id", "status", "answer", "quote", "file"} or any(
                    not isinstance(v, str) for v in row.values()
                ):
                    raise ValueError("Invalid answer fields")
                parsed.append(Answer(**row))
        except (ValueError, KeyError, TypeError):
            raise DomainError(
                "plain_format_invalid"
                if self.request.mode == "plain"
                else "baseline_format_invalid",
                "Direct model output did not satisfy the submission schema; raw output is preserved",
                422,
            ) from None
        for answer in parsed:
            if self.request.mode == "plain":
                package_id = next(q.package_id for q in self.request.questions if q.id == answer.id)
                answer = attach_plain_anchor(answer, packages, package_id)
            await self.accept(answer)

    @staticmethod
    def _scan_rows(reply, question_ids, spans, stage):
        """Validate each selection atomically, retaining no unanchored findings."""
        try:
            rows = json_output(reply.message.get("content"))["selections"]
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows
            ):
                return {}, dict.fromkeys(question_ids, "invalid_selections")
        except (ValueError, KeyError, TypeError):
            return {}, dict.fromkeys(question_ids, "invalid_json")
        if any(row["id"] not in question_ids for row in rows):
            return {}, dict.fromkeys(question_ids, "unexpected_question_ids")
        valid, errors = {}, {}
        for qid in question_ids:
            matches = [row for row in rows if row["id"] == qid]
            if len(matches) != 1:
                errors[qid] = "missing_question" if not matches else "duplicate_question"
                continue
            row = matches[0]
            refs = row.get("span_ids")
            if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
                errors[qid] = "invalid_span_ids"
                continue
            if not set(refs) <= spans.keys():
                errors[qid] = "foreign_span_ids"
                continue
            ledger = FactLedger()
            try:
                ledger.add_selection(row, spans, stage=stage)
            except (DomainError, ValueError, KeyError, TypeError):
                errors[qid] = "invalid_facts"
                continue
            valid[qid] = (row, ledger)
        return valid, errors

    async def invoke_review(self, messages, *, stage, **kwargs):
        """Retry one transient review request, preserving its exact input/checkpoint."""
        for attempt in range(2):
            try:
                return await self.invoke(messages, stage=stage, **kwargs)
            except DomainError as exc:
                if attempt or exc.code not in TRANSIENT_REVIEW_ERRORS:
                    raise
                await self.emit(
                    "review.retry",
                    {
                        "stage": stage,
                        "attempt": 2,
                        "max_attempts": 2,
                        "error_code": exc.code,
                        "progress": kwargs.get("progress"),
                    },
                )
                await asyncio.sleep(1)

    async def _scan(self, tools, questions, *, proposed=None, history=None):
        sources = [
            {
                "span_id": s.id,
                "file": s.file,
                "text": s.text,
                "document_id": s.document_id,
                "source_hash": s.source_hash,
                "start": s.start,
                "end": s.end,
            }
            for s in tools.spans.values()
        ]
        base = {"questions": [q.model_dump() for q in questions]}
        if proposed is not None:
            # The independent scanner needs claims, not the generator's global
            # citations/checks. Those IDs may belong to other batches and copy
            # large source excerpts into every request. The final critic still
            # receives the unchanged full answers and evidence in _review.
            proposed = [
                {key: answer[key] for key in ("id", "status", "answer") if key in answer}
                for answer in proposed
            ]
            base["proposed"] = proposed
        if history:
            base["previous_dialogue_for_reference_only"] = history[-6:]

        def messages(blocks, pending=None, errors=None):
            body = {**base, "sources": blocks}
            if pending is not None:
                body["questions"] = [q.model_dump() for q in questions if q.id in pending]
                if proposed is not None:
                    body["proposed"] = [a for a in proposed if a["id"] in pending]
            if errors:
                body["scan_retry"] = {
                    "errors": [{"id": qid, "reason": reason} for qid, reason in errors.items()],
                    "expected_question_ids": list(pending),
                    "allowed_span_ids": [s["span_id"] for s in blocks],
                    "instruction": "Return only these question IDs. Use only source IDs from THIS batch, never references copied from proposed answers or history. Preserve exact source quotes.",
                }
            result = [
                {"role": "system", "content": self.templates["scan"]},
                {
                    "role": "user",
                    "content": json.dumps(
                        body, ensure_ascii=False, **({"separators": (",", ":")} if errors else {})
                    ),
                },
            ]
            if errors and estimate_tokens(result) + 256 >= self.context_window:
                # IDs are already explicit in questions/sources. Remove only
                # redundant diagnostics if they crowd out the same originals.
                body["scan_retry"].pop("allowed_span_ids", None)
                body["scan_retry"].pop("expected_question_ids", None)
                result[1]["content"] = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
            return result

        batches = source_batches(sources, lambda blocks: self.fits(messages(blocks)))
        remaining = (
            min(self.request.options.max_calls, self.settings.max_model_calls) - self.usage.calls
        )
        if len(batches) + 1 > remaining:
            raise DomainError(
                "call_budget_exhausted",
                "Not enough calls for a complete source scan and synthesis",
                422,
            )
        selected = set()
        selected_by_question = {q.id: set() for q in questions}
        ids = [q.id for q in questions]
        self._scan_failures = {}
        scan_ledger = FactLedger()
        stage = "verification_scan" if proposed is not None else "evidence_scan"
        self.scan_coverage[stage] = {
            "batches_total": len(batches),
            "batches_completed": 0,
            "blocks_total": len(sources),
            "blocks_completed": 0,
            "complete": False,
        }
        covered = set()
        for index, blocks in enumerate(batches):
            pending = [qid for qid in ids if qid not in self._scan_failures]
            if not pending:
                break
            available = {s["span_id"]: tools.spans[s["span_id"]] for s in blocks}
            accepted_rows, errors = {}, {}
            for attempt in range(1, 3):
                if attempt > 1:
                    await self.emit(
                        "context.scan_retry",
                        {
                            "stage": stage,
                            "batch": index + 1,
                            "batches": len(batches),
                            "attempt": attempt,
                            "max_attempts": 2,
                            "question_ids": pending,
                        },
                    )
                scan_messages = messages(blocks, pending, errors)
                # Correction metadata consumes part of the former output
                # reserve, never original source text. invoke still enforces
                # both the full input budget and the 256-token output minimum.
                retry_output = max(256, self.context_window - estimate_tokens(scan_messages) - 1)
                invoke = self.invoke_review if proposed is not None else self.invoke
                reply = await invoke(
                    scan_messages,
                    stage=stage,
                    progress={"batch": index + 1, "batches": len(batches), "attempt": attempt},
                    output_limit=retry_output if attempt > 1 else None,
                )
                valid, errors = self._scan_rows(reply, pending, available, stage)
                accepted_rows.update(valid)
                if not errors:
                    break
                await self.emit(
                    "context.scan_invalid",
                    {
                        "stage": stage,
                        "batch": index + 1,
                        "batches": len(batches),
                        "attempt": attempt,
                        "question_ids": list(errors),
                        "issues": [{"id": qid, "reason": reason} for qid, reason in errors.items()],
                    },
                )
                pending = list(errors)
            if errors:
                self._scan_failures.update(errors)
                if proposed is None:
                    raise DomainError(
                        "scan_format_invalid",
                        "Source scan still contains invalid selections after targeted retry",
                        422,
                    )
            for qid, (row, ledger) in accepted_rows.items():
                refs = set(row["span_ids"]) | {
                    ref["span_id"] for fact in row.get("facts", []) for ref in fact["evidence"]
                }
                selected.update(refs)
                selected_by_question[qid].update(refs)
                scan_ledger.merge(ledger)
            self.fact_ledger.merge(scan_ledger)
            tools.seen.update(s["span_id"] for s in blocks)
            covered.update(s["span_id"] for s in blocks)
            self.scan_coverage[stage].update(
                batches_completed=index + 1,
                blocks_completed=len(covered),
                complete=index + 1 == len(batches)
                and len(covered) == len(sources)
                and not self._scan_failures,
                failed_question_ids=list(self._scan_failures),
            )
            await self.emit(
                "context.batch_scanned",
                {
                    "stage": stage,
                    "batch": index + 1,
                    "batches": len(batches),
                    "blocks": len(blocks),
                    "provisional_facts": len(scan_ledger.as_list()),
                    "coverage": self.scan_coverage[stage].copy(),
                },
            )
        self.scan_coverage[stage]["complete"] = (
            len(covered) == len(sources) and not self._scan_failures
        )
        self.fact_ledger.merge(scan_ledger)
        self._selected_by_question = selected_by_question
        return [s for s in sources if s["span_id"] in selected]

    def _compact_body(self, body, question_ids):
        facts = self.fact_ledger.as_list(question_ids)
        return {
            **body,
            "sources": compact_sources(body["sources"], facts),
            "fact_ledger": self.fact_ledger.compact_list(question_ids),
            "source_mode": "exact_excerpts_after_complete_scan; selection_can_miss_evidence",
        }

    async def _review(self, package, tools, candidates, answers, questions, history=None):
        unavailable = {}
        source = [
            {
                "span_id": s.id,
                "file": s.file,
                "text": s.text,
                "document_id": s.document_id,
                "source_hash": s.source_hash,
                "start": s.start,
                "end": s.end,
            }
            for s in tools.spans.values()
        ]
        body = {
            "questions": [q.model_dump() for q in questions if q.id in answers],
            "proposed": [a.model_dump(mode="json") for a in answers.values()],
            "documents_complete": all(document_text_complete(d) for d in package.documents),
            "sources": source,
            "fact_ledger": self.fact_ledger.as_list(set(answers)),
            "coverage": self.scan_coverage.copy(),
        }
        if history:
            body["previous_dialogue_for_reference_only"] = history[-6:]
        messages = [
            {"role": "system", "content": self.templates["critic"]},
            {"role": "user", "content": json.dumps(body, ensure_ascii=False)},
        ]
        if not self.fits(messages):
            # Independent pass over ALL originals, not just the generator's chosen citations.
            scanned = await self._scan(
                tools,
                [q for q in questions if q.id in answers],
                proposed=body["proposed"],
                history=history,
            )
            unavailable = {
                qid: Check(
                    code="review_unavailable",
                    message=f"scan_format_invalid:{reason}",
                    passed=False,
                    method="llm",
                )
                for qid, reason in self._scan_failures.items()
            }
            answers = {qid: answer for qid, answer in answers.items() if qid not in unavailable}
            if not answers:
                return unavailable
            body["questions"] = [q.model_dump() for q in questions if q.id in answers]
            body["proposed"] = [a.model_dump(mode="json") for a in answers.values()]
            selected = {s["span_id"] for s in scanned} | {
                ref.span_id for c in candidates for ref in c.evidence
            }
            body["sources"] = [s for s in source if s["span_id"] in selected]
            body["documents_complete"] = tools.complete_coverage
            body["fact_ledger"] = self.fact_ledger.as_list(set(answers))
            body["coverage"] = self.scan_coverage.copy()
            # A failed row affects its question only. The remaining questions
            # were checked against every batch; preserve the full audit separately.
            body["coverage"]["verification_scan"] = {
                **body["coverage"]["verification_scan"],
                "complete": True,
                "failed_question_ids": [],
                "question_ids": list(answers),
            }
            body["source_mode"] = (
                "original_excerpts_after_complete_independent_scan; selection_can_miss_evidence"
            )
            messages[1]["content"] = json.dumps(body, ensure_ascii=False)
            if not self.fits(messages):
                body = self._compact_body(body, set(answers))
                body["source_mode"] = (
                    "exact_excerpts_after_complete_independent_scan; selection_can_miss_evidence"
                )
                messages[1]["content"] = json.dumps(body, ensure_ascii=False)
        if not self.fits(messages) and len(answers) > 1:
            reviews = dict(unavailable)
            for qid, answer in answers.items():
                relevant = self._selected_by_question.get(qid, set()) | {
                    ref.span_id for c in candidates if c.id == qid for ref in c.evidence
                }
                part = self._compact_body(
                    {
                        **body,
                        "questions": [q.model_dump() for q in questions if q.id == qid],
                        "proposed": [answer.model_dump(mode="json")],
                        "sources": [s for s in source if s["span_id"] in relevant],
                    },
                    {qid},
                )
                part["source_mode"] = (
                    "exact_excerpts_after_complete_independent_scan; selection_can_miss_evidence"
                )
                messages[1]["content"] = json.dumps(part, ensure_ascii=False)
                if not self.fits(messages):
                    reviews[qid] = Check(
                        code="review_context_exhausted",
                        message="All distinct relevant findings exceed the review context budget",
                        passed=False,
                        method="llm",
                    )
                    continue
                try:
                    reply = await self.invoke_review(messages, stage="semantic_review")
                except DomainError as exc:
                    if exc.code in {"context_replan_required", "context_retry_exhausted"}:
                        raise
                    reviews[qid] = Check(
                        code="review_unavailable",
                        message=exc.code,
                        passed=False,
                        method="llm",
                    )
                else:
                    reviews.update(self._parse_reviews(reply, {qid}))
            return reviews
        reply = await self.invoke_review(messages, stage="semantic_review")
        return {**unavailable, **self._parse_reviews(reply, set(answers))}

    def _parse_reviews(self, reply, expected_ids):
        try:
            reviews = json_output(reply.message.get("content"))["reviews"]
            ids = [r["id"] for r in reviews]
            if len(ids) != len(set(ids)) or set(ids) != expected_ids:
                raise ValueError
            if any(
                r.get("verdict") not in {"supported", "revise", "unknown"}
                or not isinstance(r.get("reason"), str)
                for r in reviews
            ):
                raise ValueError
            return {
                r["id"]: Check(
                    code="semantic_review",
                    message=r["reason"],
                    passed=r["verdict"] == "supported",
                    method="llm",
                )
                for r in reviews
            }
        except (ValueError, KeyError, TypeError):
            return {
                qid: Check(
                    code="critic_format",
                    message="Semantic reviewer returned an invalid verdict",
                    passed=False,
                    method="llm",
                )
                for qid in expected_ids
            }

    async def _solve(self, package: Package, questions: list[Question], history):
        self.audit_state()
        self.fact_ledger = FactLedger()
        self.scan_coverage = {}
        # Source fragments shrink with the effective model budget too. Reserving
        # most of the window for prompts, schemas and synthesis avoids a single
        # configured large fragment making a smaller retry impossible. fits()
        # remains authoritative: even minimal chunks cannot fit oversized rules.
        effective_target = min(
            self.settings.chunk_target_tokens,
            max(256, (self.context_window - self.output_limit) // 4),
        )
        effective_overlap = min(self.settings.chunk_overlap_tokens, effective_target // 4)
        tools = ToolBox(
            package,
            target_tokens=effective_target,
            overlap_tokens=effective_overlap,
            max_read_tokens=max(256, (self.context_window - self.output_limit) // 3),
        )
        self._audit_package = package
        self._audit_tools = tools
        self._audit_window = self.context_window
        entry = self.package_audits.setdefault(
            package.id, {"revision": package.revision, "attempts": []}
        )
        self._audit_attempt = len(entry["attempts"])
        entry["attempts"].append({})
        metadata = {
            "package_id": package.id,
            "revision": package.revision,
            "documents": tools.index(),
            "questions": [q.model_dump() for q in questions],
        }
        full = tools.full_context()
        body = {**metadata, "sources": full}
        messages = [{"role": "system", "content": self.templates["harness"]}]
        if history:
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {"previous_dialogue_for_reference_only": history[-6:]}, ensure_ascii=False
                    ),
                }
            )
        initial = {"role": "user", "content": json.dumps(body, ensure_ascii=False)}
        schemas = tool_schemas(CandidateBatch.model_json_schema())
        fits = self.fits(messages + [initial], schemas)
        if self.request.options.context == "retrieval" or not fits:
            if self.request.options.context == "full":
                raise DomainError(
                    "context_budget_exceeded",
                    "Full package does not fit the configured context budget",
                    422,
                )
            tools.seen.clear()
            initial["content"] = json.dumps(metadata, ensure_ascii=False)
            if not fits and self.request.options.context == "auto":
                try:
                    selected = await self._scan(tools, questions, history=history)
                    scanned_body = {
                        **metadata,
                        "sources": selected,
                        "source_mode": "excerpts_after_complete_scan",
                        "fact_ledger": self.fact_ledger.as_list(),
                        "coverage": self.scan_coverage.copy(),
                    }
                    initial["content"] = json.dumps(scanned_body, ensure_ascii=False)
                    if not self.fits(messages + [initial], schemas):
                        scanned_body = self._compact_body(scanned_body, {q.id for q in questions})
                        initial["content"] = json.dumps(scanned_body, ensure_ascii=False)
                        await self.emit(
                            "context.evidence_compacted",
                            {
                                "original_selected_blocks": len(selected),
                                "source_excerpts": len(scanned_body["sources"]),
                                "provisional_facts": len(scanned_body["fact_ledger"]),
                                "coverage": self.scan_coverage.copy(),
                                "reason": "selected_evidence_exceeds_context",
                            },
                        )
                    if not self.fits(messages + [initial], schemas) and len(questions) > 1:
                        # All originals were already read. Synthesize each question
                        # with its own complete selection; never silently take top-K.
                        selections = self._selected_by_question.copy()
                        for question in questions:
                            ids = selections[question.id]
                            part = self._compact_body(
                                {
                                    **scanned_body,
                                    "questions": [question.model_dump()],
                                    "sources": [s for s in selected if s["span_id"] in ids],
                                },
                                {question.id},
                            )
                            part_messages = messages + [
                                {"role": "user", "content": json.dumps(part, ensure_ascii=False)}
                            ]
                            await self._answer_with_context(
                                package,
                                tools,
                                [question],
                                history,
                                part_messages,
                                schemas,
                                effective_target,
                                effective_overlap,
                            )
                        return
                except DomainError as exc:
                    if exc.code in {"context_replan_required", "context_retry_exhausted"}:
                        raise
                    for q in questions:
                        if q.id not in self.accepted:
                            await self.accept(unknown(q.id, exc.code))
                    return
        messages.append(initial)
        await self._answer_with_context(
            package,
            tools,
            questions,
            history,
            messages,
            schemas,
            effective_target,
            effective_overlap,
        )

    async def _answer_with_context(
        self,
        package,
        tools,
        questions,
        history,
        messages,
        schemas,
        effective_target,
        effective_overlap,
    ):
        await self.emit(
            "context.prepared",
            {
                "documents": len(package.documents),
                "blocks": len(tools.spans),
                "context": self.request.options.context,
                "chunk_target_tokens": effective_target,
                "chunk_overlap_tokens": effective_overlap,
                "configured_chunk_target_tokens": self.settings.chunk_target_tokens,
                "configured_chunk_overlap_tokens": self.settings.chunk_overlap_tokens,
                "token_estimate_method": "characters_divided_by_two",
                "provisional_facts": len(self.fact_ledger.as_list()),
                "coverage": self.scan_coverage.copy(),
            },
        )
        repairs = self.repair_attempts.get(package.id, 0)
        pending = {q.id for q in questions}
        last_errors: dict[str, list[Check]] = {}
        for _ in range(
            self.request.options.max_rounds_per_package - self.answer_rounds.get(package.id, 0)
        ):
            if not pending:
                return
            self.answer_rounds[package.id] = self.answer_rounds.get(package.id, 0) + 1
            try:
                reply = await self.invoke(messages, tools=schemas)
            except DomainError as exc:
                if exc.code in {
                    "call_budget_exhausted",
                    "context_budget_exceeded",
                    "context_length_exceeded",
                    "output_truncated",
                }:
                    for qid in pending:
                        await self.accept(unknown(qid, exc.code, last_errors.get(qid)))
                    return
                raise
            messages.append(reply.message)
            calls = reply.message.get("tool_calls") or []
            submissions = []
            for call in calls[:16]:
                tool_id = call.get("id", "")
                function = call.get("function") or {}
                name = function.get("name", "")
                result = {}
                await self.emit("tool.started", {"name": name})
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                    if not isinstance(arguments, dict):
                        raise ValueError
                    if name == "submit_answers":
                        submissions.append(arguments)
                        result = {"received": True, "validated": False}
                    else:
                        result = tools.call(name, arguments)
                    await self.emit(
                        "tool.completed", {"name": name, "arguments": arguments, "result": result}
                    )
                except (DomainError, ValueError, TypeError) as exc:
                    result = {
                        "error": exc.code
                        if isinstance(exc, DomainError)
                        else "invalid_tool_arguments"
                    }
                    await self.emit("tool.failed", {"name": name, **result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
            if len(calls) > 16:
                raise DomainError("tool_limit", "Too many tool calls in one model response", 422)
            if not calls:
                try:
                    submissions.append(json_output(reply.message.get("content")))
                except ValueError:
                    submissions.append({})
            if not submissions:
                continue
            errors = {}
            for submission in submissions:
                try:
                    batch = CandidateBatch.model_validate(submission)
                    ids = [c.id for c in batch.answers]
                    if len(ids) != len(set(ids)) or not set(ids) <= pending:
                        raise ValueError
                except (ValidationError, ValueError):
                    errors.update(
                        {
                            qid: [
                                Check(
                                    code="answer_schema",
                                    message="Submit valid unique IDs and evidence references",
                                    passed=False,
                                )
                            ]
                            for qid in pending
                        }
                    )
                    continue
                valid = {}
                for candidate in batch.answers:
                    await self.emit("validation.started", {"id": candidate.id})
                    answer, failures = validate(candidate, tools)
                    await self.emit(
                        "validation.finished",
                        {
                            "id": candidate.id,
                            "passed": not failures,
                            "failed_checks": [c.code for c in failures],
                        },
                    )
                    if failures:
                        errors[candidate.id] = failures
                        await self.emit(
                            "validation.failed",
                            {
                                "id": candidate.id,
                                "candidate": candidate.model_dump(mode="json"),
                                "checks": [c.model_dump() for c in failures],
                            },
                        )
                    elif candidate.status == AnswerStatus.UNKNOWN:
                        await self.accept(answer)
                        pending.discard(candidate.id)
                    else:
                        valid[candidate.id] = answer
                if valid and self.request.options.semantic_review:
                    await self.emit("review.started", {"question_ids": list(valid)})
                    try:
                        reviews = await self._review(
                            package, tools, batch.answers, valid, questions, history
                        )
                    except DomainError as exc:
                        if exc.code in {"context_replan_required", "context_retry_exhausted"}:
                            raise
                        reviews = {
                            qid: Check(
                                code="review_unavailable",
                                message=exc.code,
                                passed=False,
                                method="llm",
                            )
                            for qid in valid
                        }
                    await self.emit(
                        "review.finished",
                        {
                            "passed": all(r.passed for r in reviews.values()),
                            "rejected_question_ids": [
                                qid for qid, r in reviews.items() if not r.passed
                            ],
                        },
                    )
                    for qid, review in reviews.items():
                        valid[qid].checks.append(review)
                        if not review.passed:
                            errors[qid] = [review]
                            await self.emit(
                                "validation.failed",
                                {
                                    "id": qid,
                                    "candidate": valid[qid].model_dump(mode="json"),
                                    "checks": [review.model_dump()],
                                },
                            )
                            if review.code in {
                                "review_unavailable",
                                "review_context_exhausted",
                                "critic_format",
                            }:
                                # A failed verification is not evidence that the
                                # answer needs rewriting. Never spend generator
                                # repairs on transport/schema/budget failures.
                                answer = valid[qid]
                                if (
                                    self.chat_return_code_checked
                                    and review.code == "review_unavailable"
                                    and review.message in TRANSIENT_REVIEW_ERRORS
                                    and answer.status
                                    in {AnswerStatus.ANSWER, AnswerStatus.CONFLICT}
                                    and answer.evidence
                                ):
                                    answer.reason = "independent_review_incomplete"
                                    await self.accept(answer)
                                else:
                                    await self.accept(unknown(qid, review.message, [review]))
                                pending.discard(qid)
                for qid, answer in valid.items():
                    if qid not in errors:
                        await self.accept(answer)
                        pending.discard(qid)
            for qid in pending:
                errors.setdefault(
                    qid,
                    [
                        Check(
                            code="missing_answer", message="Question was not answered", passed=False
                        )
                    ],
                )
            if not pending:
                return
            last_errors.update(errors)
            if repairs >= self.request.options.max_repairs:
                break
            repairs += 1
            self.repair_attempts[package.id] = repairs
            await self.emit(
                "repair.started",
                {
                    "attempt": repairs,
                    "max_repairs": self.request.options.max_repairs,
                    "question_ids": sorted(pending),
                },
            )
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "repair_only": sorted(pending),
                            "errors": {
                                qid: [c.model_dump() for c in errors[qid]] for qid in pending
                            },
                            "instruction": "Repair only these answers using original evidence. Do not change accepted answers.",
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        for qid in pending:
            await self.accept(
                unknown(qid, "Verification or tool budget exhausted", last_errors.get(qid))
            )
