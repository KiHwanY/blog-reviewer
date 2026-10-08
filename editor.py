"""리뷰 종합과 수정안 생성.

- synthesize(): 세 리뷰를 우선순위별 수정 사항으로 정리한다.
- revise(): 수정 사항을 반영해 초안을 고쳐 쓴다.
"""

from pathlib import Path
from typing import Literal

from langchain_core.documents import Document
from pydantic import BaseModel, Field

import config
from retriever import format_references
from reviewer import PERSONAS, Review

PROMPT_DIR = Path(__file__).parent / "prompts"
REVISE_MAX_TOKENS = 64000  # 글 전체를 다시 쓰므로 넉넉히 준다


class Fix(BaseModel):
    """수정 사항 하나."""

    priority: Literal["높음", "중간", "낮음"]
    issue: str = Field(description="무엇이 문제인지")
    suggestion: str = Field(description="어떻게 고치면 되는지")
    raised_by: list[str] = Field(description="이 문제를 지적한 리뷰어 이름")


class Synthesis(BaseModel):
    """세 리뷰를 종합한 결과."""

    summary: str = Field(description="초안의 현재 상태와 가장 중요한 한 가지")
    fixes: list[Fix] = Field(description="수정 사항. 우선순위가 높은 것부터")


def average_score(reviews: dict[str, Review]) -> float:
    """평균 점수는 LLM에 맡기지 않고 직접 계산한다."""
    return round(sum(review.score for review in reviews.values()) / len(reviews), 1)


def format_reviews(reviews: dict[str, Review]) -> str:
    blocks = []
    for persona, review in reviews.items():
        strengths = "\n".join(f"- {item}" for item in review.strengths)
        improvements = "\n".join(f"- {item}" for item in review.improvements)
        blocks.append(
            f"<리뷰 리뷰어=\"{PERSONAS[persona]}\" 점수=\"{review.score}\">\n"
            f"좋은 점:\n{strengths}\n고칠 점:\n{improvements}\n</리뷰>"
        )
    return "\n\n".join(blocks)


def format_fixes(fixes: list[Fix]) -> str:
    return "\n".join(
        f"{i}. [{fix.priority}] {fix.issue}\n   → {fix.suggestion}"
        for i, fix in enumerate(fixes, 1)
    )


def synthesize(draft: str, reviews: dict[str, Review]) -> Synthesis:
    """세 리뷰를 우선순위별 수정 사항으로 정리한다."""
    llm = config.get_llm().with_structured_output(Synthesis, method="json_schema")
    system = (PROMPT_DIR / "synthesize.md").read_text(encoding="utf-8")
    user_message = (
        f"# 초안\n\n<초안>\n{draft}\n</초안>\n\n"
        f"# 리뷰\n\n{format_reviews(reviews)}\n\n"
        "세 리뷰를 종합해 수정 사항을 정리해 주세요."
    )
    return llm.invoke([("system", system), ("user", user_message)])


def revise(draft: str, synthesis: Synthesis, references: list[Document]) -> str:
    """수정 사항을 반영해 고쳐 쓴 글(마크다운)을 돌려준다."""
    system = (PROMPT_DIR / "revise.md").read_text(encoding="utf-8")
    user_message = (
        f"# 기존 글 발췌\n\n{format_references(references)}\n\n"
        f"# 초안\n\n<초안>\n{draft}\n</초안>\n\n"
        f"# 수정 사항\n\n{format_fixes(synthesis.fixes)}\n\n"
        "수정 사항을 반영해 초안을 고쳐 써 주세요."
    )
    response = config.get_llm(max_tokens=REVISE_MAX_TOKENS).invoke(
        [("system", system), ("user", user_message)]
    )
    if response.response_metadata.get("stop_reason") == "max_tokens":
        raise RuntimeError("수정안이 max_tokens에 걸려 중간에 잘렸습니다.")
    return response.text.strip()
