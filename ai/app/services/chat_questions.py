"""Validate model-selected answer units without guessing question boundaries.

Code only checks lossless coverage and limits, then assigns trusted IDs.
Punctuation, CSV fields and line layout are opaque to this validator.
"""

from pydantic import Field

from app.domain import DTO, DomainError, Question


class ChatPlan(DTO):
    parts: list[str] = Field(min_length=1, max_length=50)


def questions_from_plan(message_id: str, package_id: str, text: str, plan: ChatPlan):
    cursor = 0
    for part in plan.parts:
        if not part.strip():
            raise DomainError("invalid_chat_plan", "Empty answer unit", 422)
        position = text.find(part, cursor)
        if position < 0 or text[cursor:position].strip():
            raise DomainError(
                "invalid_chat_plan", "Answer units must copy the complete message in order", 422
            )
        cursor = position + len(part)
    if text[cursor:].strip():
        raise DomainError("invalid_chat_plan", "Answer units omitted part of the message", 422)
    return [
        Question(
            id=message_id if len(plan.parts) == 1 else f"{message_id}.q{index:02d}",
            package_id=package_id,
            text=text if len(plan.parts) == 1 else part,
        )
        for index, part in enumerate(plan.parts, 1)
    ]
