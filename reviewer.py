"""페르소나 리뷰: 한 명의 페르소나가 초안을 리뷰해 구조화된 결과를 돌려준다.

    python reviewer.py                    # samples/draft.md를 세 페르소나로 리뷰
    python reviewer.py 내초안.md senior    # 파일과 페르소나 지정
"""

import sys
from pathlib import Path

from langchain_core.documents import Document
from pydantic import BaseModel, Field

import config
from retriever import format_references, retrieve

PROMPT_DIR = Path(__file__).parent / "prompts"

PERSONAS = {
    "beginner": "초보 독자",
    "senior": "시니어 개발자",
    "seo": "SEO 전문가",
}


class Review(BaseModel):
    """페르소나 한 명의 리뷰 결과."""

    score: int = Field(ge=1, le=10, description="이 관점에서 본 초안의 완성도 (1~10)")
    strengths: list[str] = Field(description="좋은 점")
    improvements: list[str] = Field(description="고칠 점. 중요한 것부터")


def load_system_prompt(persona: str) -> str:
    """공통 리뷰 방식 + 페르소나별 관점을 합쳐 시스템 프롬프트를 만든다."""
    common = (PROMPT_DIR / "common.md").read_text(encoding="utf-8")
    role = (PROMPT_DIR / f"{persona}.md").read_text(encoding="utf-8")
    return f"{role}\n\n{common}"


def review(persona: str, draft: str, references: list[Document]) -> Review:
    """페르소나 한 명이 기존 글 발췌를 근거로 초안을 리뷰한다."""
    llm = config.get_llm().with_structured_output(Review, method="json_schema")
    user_message = (
        f"# 기존 글 발췌\n\n{format_references(references)}\n\n"
        f"# 초안\n\n<초안>\n{draft}\n</초안>\n\n"
        "위 초안을 당신의 관점에서 리뷰해 주세요."
    )
    return llm.invoke([("system", load_system_prompt(persona)), ("user", user_message)])


def print_review(persona: str, result: Review) -> None:
    print(f"\n===== {PERSONAS[persona]} : {result.score}점 =====")
    print("[좋은 점]")
    for item in result.strengths:
        print(f"  - {item}")
    print("[고칠 점]")
    for item in result.improvements:
        print(f"  - {item}")


def main() -> None:
    draft_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/draft.md")
    personas = sys.argv[2:] or list(PERSONAS)
    draft = draft_path.read_text(encoding="utf-8")

    references = retrieve(draft)
    print(f"초안: {draft_path} ({len(draft)}자)")
    print("근거로 쓸 기존 글:")
    for title in dict.fromkeys(doc.metadata["title"] for doc in references):
        print(f"  - {title}")

    for persona in personas:
        print_review(persona, review(persona, draft, references))


if __name__ == "__main__":
    main()
