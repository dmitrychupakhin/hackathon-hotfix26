import re
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext

from app.domain import DomainError, Package
from app.services.documents import document_text_complete, spans_for


def decimal_value(text: str) -> Decimal:
    if len(str(text)) > 64:
        raise DomainError("invalid_number", "Number is too long", 422)
    try:
        result = Decimal(
            re.sub(r"[\s\u00a0\u202f]", "", str(text)).replace(",", ".").replace("−", "-")
        )
    except InvalidOperation:
        raise DomainError("invalid_number", "Invalid decimal operand", 422) from None
    if not result.is_finite() or abs(result) > Decimal("1e24"):
        raise DomainError("invalid_number", "Operand is not a finite bounded decimal", 422)
    return result


def calculate(operation: str, operands: list[str]) -> str:
    if not 2 <= len(operands) <= 8:
        raise DomainError("invalid_operands", "Provide 2 to 8 operands", 422)
    values = [decimal_value(value) for value in operands]
    with localcontext() as context:
        context.prec = 50
        if operation == "add":
            result = sum(values)
        elif operation == "multiply":
            result = Decimal(1)
            for value in values:
                result *= value
        elif operation in {"subtract", "divide", "percentage"} and len(values) == 2:
            a, b = values
            if operation == "subtract":
                result = a - b
            elif operation == "percentage":
                result = a * b / 100
            elif b == 0:
                raise DomainError("division_by_zero", "Division by zero", 422)
            else:
                result = a / b
        else:
            raise DomainError("invalid_operation", "Unsupported arithmetic operation", 422)
    return format(result, "f")


def tokens(text):
    return [t[:6] for t in re.findall(r"[\w]+", text.lower().replace("ё", "е")) if len(t) > 2]


class ToolBox:
    def __init__(
        self, package: Package, *, target_tokens=2000, overlap_tokens=200, max_read_tokens=None
    ):
        self.package = package
        self.spans = spans_for(package, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
        self.seen: set[str] = set()
        self.max_read_tokens = max_read_tokens

    def bounded(self, spans):
        if self.max_read_tokens is None:
            return list(spans)
        result = []
        used = 0
        for span in spans:
            cost = (len(span.text) + 1) // 2 + 100
            if used + cost > self.max_read_tokens:
                break
            result.append(span)
            used += cost
        return result

    @property
    def complete_coverage(self):
        return (
            bool(self.spans)
            and self.seen >= self.spans.keys()
            and all(document_text_complete(d) for d in self.package.documents)
        )

    def index(self):
        return [
            {
                "id": d.id,
                "file": d.name,
                "characters": len(d.text),
                "warning": d.warning,
                "blocks": sum(s.document_id == d.id for s in self.spans.values()),
            }
            for d in self.package.documents
        ]

    def full_context(self):
        self.seen.update(self.spans)
        return [{"span_id": s.id, "file": s.file, "text": s.text} for s in self.spans.values()]

    def read_document(self, document_id: str, offset: int = 0, limit: int = 6):
        if document_id not in {d.id for d in self.package.documents}:
            raise DomainError("unknown_document", "Document is not in the current package", 404)
        if offset < 0 or not 1 <= limit <= 8:
            raise DomainError("invalid_page", "Invalid document page", 422)
        blocks = [s for s in self.spans.values() if s.document_id == document_id]
        page = self.bounded(blocks[offset : offset + limit])
        self.seen.update(s.id for s in page)
        return {
            "blocks": [{"span_id": s.id, "file": s.file, "text": s.text} for s in page],
            "next_offset": offset + len(page) if offset + len(page) < len(blocks) else None,
            "total_blocks": len(blocks),
            "limited_by_token_budget": len(page) < len(blocks[offset : offset + limit]),
        }

    def read_evidence(self, span_id: str):
        if span_id not in self.spans:
            raise DomainError("unknown_evidence", "Evidence is not in the current package", 404)
        self.seen.add(span_id)
        return self.spans[span_id].model_dump()

    def search(self, query: str, limit: int = 6):
        if not query.strip() or len(query) > 2000 or not 1 <= limit <= 10:
            raise DomainError("invalid_search", "Invalid search query or limit", 422)
        query_tokens = set(tokens(query))
        scored = []
        for span in self.spans.values():
            counts = Counter(tokens(span.text))
            score = sum(min(counts.get(t, 0), 3) for t in query_tokens)
            if score:
                scored.append((score, span))
        scored.sort(key=lambda item: (-item[0], item[1].file, item[1].start))
        bounded_ids = {s.id for s in self.bounded([s for _, s in scored[:limit]])}
        selected = [(score, s) for score, s in scored[:limit] if s.id in bounded_ids]
        self.seen.update(s.id for _, s in selected)
        return {
            "matches": [
                {"span_id": s.id, "file": s.file, "text": s.text, "score": score}
                for score, s in selected
            ],
            "exhaustive": False,
            "note": "Empty search results do not prove absence of information.",
        }

    def amendments(self):
        selected = [
            s
            for s in self.spans.values()
            if re.search(
                r"изменени[яй].{0,30}извещени|следующ.{0,20}редакци|изложить", s.text, re.I | re.S
            )
        ]
        page = self.bounded(selected[:8])
        self.seen.update(s.id for s in page)
        return {
            "candidates": [{"span_id": s.id, "file": s.file, "text": s.text} for s in page],
            "truncated": len(selected) > len(page),
            "note": "These are candidate amendment clauses, not an automatic priority decision.",
        }

    def call(self, name: str, arguments: dict):
        if name == "list_documents":
            return {"documents": self.index()}
        if name == "read_document":
            return self.read_document(**arguments)
        if name == "read_evidence":
            return self.read_evidence(**arguments)
        if name == "search_documents":
            return self.search(**arguments)
        if name == "find_amendments":
            return self.amendments()
        if name == "calculate":
            return {
                "result": calculate(**arguments),
                "operation": arguments["operation"],
                "operands": arguments["operands"],
            }
        raise DomainError("unknown_tool", "Tool is not allowed", 422)


def schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def tool_schemas(candidate_schema: dict):
    return [
        schema("list_documents", "List documents in this procurement package only.", {}, []),
        schema(
            "read_document",
            "Read original blocks; follow next_offset to read remaining blocks.",
            {
                "document_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            ["document_id"],
        ),
        schema(
            "read_evidence",
            "Read a complete original evidence block by its ID.",
            {"span_id": {"type": "string"}},
            ["span_id"],
        ),
        schema(
            "search_documents",
            "Lexical search; empty results cannot establish absence.",
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            ["query"],
        ),
        schema(
            "find_amendments",
            "Locate candidate clauses that replace earlier provisions. Read their scope.",
            {},
            [],
        ),
        schema(
            "calculate",
            "Bounded decimal arithmetic. Evidence for all operands is still required.",
            {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide", "percentage"],
                },
                "operands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 8,
                },
            },
            ["operation", "operands"],
        ),
        {
            "type": "function",
            "function": {
                "name": "submit_answers",
                "description": "Submit proposed answers for mandatory server validation. Submission is not an approval.",
                "parameters": candidate_schema,
            },
        },
    ]
