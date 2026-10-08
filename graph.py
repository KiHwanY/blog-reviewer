"""블로그 글 리뷰 워크플로우 (LangGraph).

    retrieve → 세 페르소나 리뷰(병렬) → synthesize → 평균 7점 미만이면 revise → 다시 리뷰
                                                  └ 7점 이상, 2회 수정, 점수 정체 중 하나면 종료

    python graph.py                # samples/draft.md로 실행
    python graph.py 내초안.md
    python graph.py --image        # 그래프 구조를 docs/graph.png로 저장
"""

import operator
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Iterator, TypedDict

from langchain_core.documents import Document
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from psycopg import Connection
from psycopg.rows import dict_row

import config
import editor
import reviewer
import usage
from retriever import retrieve

GRAPH_IMAGE = Path("docs/graph.png")

# 체크포인트에서 되살릴 때 허용할 우리 프로젝트의 Pydantic 모델
CHECKPOINT_SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=[("reviewer", "Review"), ("editor", "Synthesis")]
)


class ReviewState(TypedDict, total=False):
    draft: str  # 현재 초안. revise를 거치면 수정안으로 바뀐다
    references: list[Document]  # 검색된 기존 글 발췌
    # 세 리뷰 노드가 동시에 쓰므로 dict를 합치는 리듀서를 둔다
    reviews: Annotated[dict[str, reviewer.Review], operator.or_]
    average_score: float
    synthesis: editor.Synthesis
    revision_count: int
    pass_score: float  # 이 점수 이상이면 수정 없이 끝낸다
    # 라운드별 기록: 리뷰한 초안, 세 리뷰, 평균 점수, 종합 결과
    history: Annotated[list[dict], operator.add]
    usage: Annotated[list[dict], operator.add]  # LLM 호출별 토큰 수와 예상 비용


# ---------- 노드 ----------

def retrieve_node(state: ReviewState) -> dict:
    return {"references": retrieve(state["draft"]), "revision_count": 0}


def make_review_node(persona: str):
    """페르소나 하나를 담당하는 리뷰 노드를 만든다."""

    def review_node(state: ReviewState) -> dict:
        with usage.track(f"{reviewer.PERSONAS[persona]} 리뷰") as used:
            result = reviewer.review(persona, state["draft"], state["references"])
        return {"reviews": {persona: result}, "usage": [used]}

    return review_node


def synthesize_node(state: ReviewState) -> dict:
    reviews = state["reviews"]
    average = editor.average_score(reviews)
    with usage.track("종합") as used:
        synthesis = editor.synthesize(state["draft"], reviews)
    round_record = {
        "round": state["revision_count"],
        "draft": state["draft"],
        "reviews": dict(reviews),
        "average_score": average,
        "synthesis": synthesis,
    }
    return {
        "average_score": average,
        "synthesis": synthesis,
        "history": [round_record],
        "usage": [used],
    }


def revise_node(state: ReviewState) -> dict:
    original_draft = state["history"][0]["draft"]
    with usage.track("수정안 작성") as used:
        revised = editor.revise(
            state["draft"],
            state["synthesis"],
            state["references"],
            max_chars=config.revision_char_limit(original_draft),
        )
    return {"draft": revised, "revision_count": state["revision_count"] + 1, "usage": [used]}


STOP_MESSAGES = {
    "passed": "평균 점수가 기준을 넘었습니다.",
    "no_improvement": "수정해도 평균 점수가 오르지 않아 멈췄습니다.",
    "max_revisions": "최대 수정 횟수에 도달했습니다.",
}


def stop_reason(state: ReviewState) -> str | None:
    """리뷰를 끝낼 이유를 돌려준다. 계속 수정해야 하면 None."""
    history = state["history"]
    if state["average_score"] >= state.get("pass_score", config.PASS_SCORE):
        return "passed"
    # 직전 라운드보다 점수가 오르지 않았다면 더 고쳐도 비용만 든다
    if len(history) >= 2 and history[-1]["average_score"] <= history[-2]["average_score"]:
        return "no_improvement"
    if state["revision_count"] >= config.MAX_REVISIONS:
        return "max_revisions"
    return None


def should_revise(state: ReviewState) -> str:
    return "done" if stop_reason(state) else "revise"


# ---------- 그래프 ----------

def build_graph(checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(ReviewState)
    review_nodes = [f"review_{persona}" for persona in reviewer.PERSONAS]

    builder.add_node("retrieve", retrieve_node)
    for persona, node_name in zip(reviewer.PERSONAS, review_nodes):
        builder.add_node(node_name, make_review_node(persona))
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("revise", revise_node)

    builder.add_edge(START, "retrieve")
    for node_name in review_nodes:
        builder.add_edge("retrieve", node_name)  # 세 리뷰로 갈라져 병렬 실행
        builder.add_edge("revise", node_name)  # 수정 후에는 리뷰부터 다시
    builder.add_edge(review_nodes, "synthesize")  # 세 리뷰가 모두 끝나면 종합
    builder.add_conditional_edges(
        "synthesize", should_revise, {"revise": "revise", "done": END}
    )
    return builder.compile(checkpointer=checkpointer)


@contextmanager
def open_graph() -> Iterator[CompiledStateGraph]:
    """PostgresSaver 체크포인터가 붙은 그래프를 연다.

    체크포인트 테이블은 search_path 첫 번째인 blog_reviewer 스키마에 생긴다.
    """
    # from_conn_string()과 같은 연결 옵션을 쓰되, 직렬화 설정을 넘기려고 직접 연결한다
    with Connection.connect(
        config.psycopg_url(), autocommit=True, prepare_threshold=0, row_factory=dict_row
    ) as conn:
        checkpointer = PostgresSaver(conn, serde=CHECKPOINT_SERDE)
        checkpointer.setup()
        yield build_graph(checkpointer)


def thread_config(thread_id: str | None = None) -> dict:
    """리뷰 한 건마다 새 thread_id를 쓴다. 이 id로 나중에 결과를 다시 불러올 수 있다."""
    return {"configurable": {"thread_id": thread_id or str(uuid.uuid4())}}


def round_label(round_number: int) -> str:
    return "원본" if round_number == 0 else f"{round_number}차 수정"


def describe_update(node: str, output: dict) -> str:
    """노드 하나가 끝났을 때 보여줄 진행 메시지."""
    if node == "retrieve":
        titles = dict.fromkeys(doc.metadata["title"] for doc in output["references"])
        return f"기존 글 {len(titles)}편을 근거로 찾았습니다"
    if node.startswith("review_"):
        persona, review = next(iter(output["reviews"].items()))
        message = f"{reviewer.PERSONAS[persona]} 리뷰 완료: {review.score}점"
    elif node == "synthesize":
        fixes = output["synthesis"].fixes
        message = f"종합 완료: 평균 {output['average_score']}점, 수정 사항 {len(fixes)}개"
    else:  # revise
        message = f"{output['revision_count']}차 수정안 작성 완료 ({len(output['draft']):,}자)"
    return f"{message} · {usage.describe(output['usage'][0])}"


def save_graph_image(path: Path = GRAPH_IMAGE) -> None:
    """그래프 구조를 PNG로 저장한다. 렌더링은 mermaid.ink 서버가 해 주므로 인터넷이 필요하다."""
    path.parent.mkdir(exist_ok=True)
    png = build_graph().get_graph().draw_mermaid_png(max_retries=5, retry_delay=2.0)
    path.write_bytes(png)


# ---------- 실행 ----------

def main() -> None:
    if "--image" in sys.argv:
        save_graph_image()
        print(f"그래프 이미지 저장: {GRAPH_IMAGE}")
        return

    draft_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/draft.md")
    draft = draft_path.read_text(encoding="utf-8")

    thread = thread_config()
    print(f"초안: {draft_path} / thread_id: {thread['configurable']['thread_id']}")

    with open_graph() as graph:
        for update in graph.stream({"draft": draft}, thread, stream_mode="updates"):
            for node, output in update.items():
                print(f"[{node}] {describe_update(node, output)}")
        final = graph.get_state(thread).values

    print("\n===== 결과 =====")
    for record in final["history"]:
        scores = {persona: review.score for persona, review in record["reviews"].items()}
        print(f"{round_label(record['round'])}: 평균 {record['average_score']}점 {scores}")
    print(f"종료: {STOP_MESSAGES[stop_reason(final)]}")
    print(f"사용량: {usage.describe(usage.total(final['usage']))}")
    print(f"\n[총평] {final['synthesis'].summary}")
    print("\n[남은 수정 사항]")
    print(editor.format_fixes(final["synthesis"].fixes))

    if final["revision_count"]:
        output_path = draft_path.with_name(f"{draft_path.stem}.revised.md")
        output_path.write_text(final["draft"], encoding="utf-8")
        print(f"\n최종 수정안 저장: {output_path}")


if __name__ == "__main__":
    main()
