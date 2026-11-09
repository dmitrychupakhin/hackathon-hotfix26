from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.provider_settings import MODEL_EXAMPLES, normalize_base_url


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid4())


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerStatus(StrEnum):
    ANSWER = "ответ"
    CONFLICT = "расхождение"
    ABSENT = "нет в документах"
    UNKNOWN = "не знаю"


class Document(DTO):
    id: str = Field(default_factory=uid)
    name: str
    text: str
    sha256: str
    encoding: str = "utf-8"
    warning: str | None = None
    original_name: str | None = None
    source_file_id: str | None = None
    source_version: str | None = None
    source_updated_at: str | None = None
    original_sha256: str | None = None
    media_type: str = "text/plain"
    extractor: str = "text"
    artifact_key: str | None = None
    partial: bool = False
    locations: list[dict] = Field(default_factory=list)


class Package(DTO):
    id: str = Field(default_factory=uid)
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    documents: list[Document] = Field(default_factory=list)
    created_at: str = Field(default_factory=now)
    revision: str = ""


class Question(DTO):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    package_id: str
    text: str = Field(min_length=1, max_length=12000)


class Span(DTO):
    id: str
    document_id: str
    file: str
    source_hash: str
    anchor_method: Literal["harness_evidence", "exact_text_match"] = "harness_evidence"
    source_file_id: str | None = None
    source_version: str | None = None
    original_sha256: str | None = None
    start: int
    end: int
    text: str
    locations: list[dict] = Field(default_factory=list)


class EvidenceRef(DTO):
    span_id: str
    quote: str | None = Field(default=None, max_length=12000)


class Calculation(DTO):
    operation: Literal["add", "subtract", "multiply", "divide", "percentage"]
    operands: list[str] = Field(min_length=2, max_length=8)
    result: str


class Candidate(DTO):
    id: str
    status: AnswerStatus
    answer: str = Field(default="", max_length=12000)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    calculation: Calculation | None = None
    clarification_question: str | None = Field(default=None, min_length=1, max_length=1000)


class CandidateBatch(DTO):
    answers: list[Candidate] = Field(max_length=200)


class Check(DTO):
    code: str
    message: str
    passed: bool
    method: Literal["code", "llm"] = "code"


class HarnessStep(DTO):
    schema_version: Literal[1] = 1
    step_id: str
    kind: str
    status: Literal["started", "completed", "failed", "cancelled", "interrupted"]
    title: str
    message: str
    package_id: str | None
    question_ids: list[str]
    details: dict
    elapsed_seconds: float | None


class Answer(DTO):
    id: str
    status: AnswerStatus | None
    answer: str = ""
    quote: str = ""
    file: str = ""
    evidence: list[Span] = Field(default_factory=list)
    calculation: Calculation | None = None
    checks: list[Check] = Field(default_factory=list)
    origin: Literal["model", "fallback", "raw"] = "model"
    reason: str | None = None
    clarification_question: str | None = Field(
        default=None,
        description="Question to ask the user when status is 'не знаю' because the referent is ambiguous. This is not a factual answer.",
    )


class RunOptions(DTO):
    question_grouping: Literal["per_package"] = "per_package"
    max_output_tokens: int | None = Field(default=None, ge=256, le=32000)
    max_calls: int = Field(default=48, ge=1, le=200)
    max_repairs: int = Field(default=1, ge=0, le=3)
    max_rounds_per_package: int = Field(default=8, ge=1, le=20)
    semantic_review: bool = True
    context: Literal["auto", "full", "retrieval"] = "auto"
    timeout_seconds: float = Field(default=600, ge=1, le=3600)


class ProfilePromptInput(DTO):
    system_prompt: str | None = Field(
        default=None,
        min_length=1,
        max_length=32000,
        description="System prompt from the backend user profile, supported in plain/harness modes. Null or omitted uses that mode's built-in prompt. Server limits and harness checks are controlled separately.",
    )

    @field_validator("system_prompt")
    @classmethod
    def valid_system_prompt(cls, value):
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("System prompt must contain text and no NUL characters")
        return value


class GenerationSettings(ProfilePromptInput):
    additional_instructions: str = Field(
        default="",
        max_length=8000,
        description="Profile instructions appended to built-in plain/harness rules, as in Django chat. Forbidden in baseline/raw.",
    )
    mode: Literal["plain", "harness", "raw", "baseline"] = "harness"
    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
        examples=MODEL_EXAMPLES,
        description="Optional model ID. Omitted/null uses APIMIRA_MODEL from .env; default openai/gpt-6-luna. Explicit IDs are sent to the configured provider.",
    )
    base_url: str | None = Field(
        default=None,
        max_length=2000,
        examples=["https://apimira.com/v1"],
        description="Optional provider API base URL, including /v1. Omitted/null uses APIMIRA_BASE_URL from .env; default https://apimira.com/v1. Overrides must be enabled via AI_ALLOWED_BASE_URLS; API keys are never accepted in this field.",
    )
    options: RunOptions = Field(default_factory=RunOptions)

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value):
        return normalize_base_url(value) if value is not None else None

    @model_validator(mode="after")
    def validate_system_prompt_mode(self):
        if self.additional_instructions and self.mode in {"baseline", "raw"}:
            raise ValueError("baseline/raw cannot use profile instructions")
        if self.mode in {"raw", "baseline"} and self.system_prompt is not None:
            raise ValueError(
                "system_prompt is supported in plain/harness modes; raw/baseline have no system message"
            )
        return self


class RunCreate(GenerationSettings):
    questions: list[Question] = Field(min_length=1, max_length=200)
    session_id: str | None = None

    @model_validator(mode="after")
    def unique_questions(self):
        if self.additional_instructions and self.mode in {"baseline", "raw"}:
            raise ValueError("baseline/raw cannot use profile instructions")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Question IDs must be unique")
        return self


class PackageCreate(DTO):
    code: str = Field(min_length=1, max_length=80, pattern=r"^[\w.-]+$")
    name: str = Field(min_length=1, max_length=200)


class TextDocument(DTO):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=5_000_000)

    @field_validator("name")
    @classmethod
    def filename_only(cls, value):
        if "/" in value or "\\" in value or value in {".", ".."} or "\x00" in value:
            raise ValueError("Provide a plain filename, not a filesystem path")
        if not value.lower().endswith((".txt", ".md")):
            raise ValueError("MVP supports TXT and Markdown documents")
        return value


class PackageInput(PackageCreate):
    documents: list[TextDocument] = Field(min_length=1, max_length=64)


class DatasetQuestion(DTO):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    package: str
    question: str = Field(min_length=1, max_length=12000)


class DatasetCreate(DTO):
    name: str = Field(min_length=1, max_length=200)
    packages: list[PackageInput] = Field(min_length=1, max_length=50)
    questions: list[DatasetQuestion] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def check_references(self):
        codes = [p.code for p in self.packages]
        if len(set(codes)) != len(codes):
            raise ValueError("Package codes must be unique")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Question IDs must be unique")
        if any(q.package not in codes for q in self.questions):
            raise ValueError("Question references an unknown package")
        return self


class SessionCreate(DTO):
    package_id: str
    title: str = Field(default="Диалог по закупке", max_length=200)


class ChatMessage(GenerationSettings):
    mode: Literal["plain", "harness"] = "harness"
    text: str = Field(min_length=1, max_length=12000)
    question_id: str | None = Field(default=None, pattern=r"^[\w.-]+$", max_length=100)


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
