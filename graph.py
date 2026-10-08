"""블로그 글 리뷰 워크플로우 (LangGraph).

    retrieve → 세 페르소나 리뷰(병렬) → synthesize → 평균 7점 미만이면 revise → 다시 리뷰
                                                  └ 7점 이상이거나 2회 수정했으면 종료

    python graph.py                # samples/draft.md로 실행, docs/graph.png 저장
    python graph.py 내초안.md
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
    history: Annotated[list[dict], operator.add]  # 라운드별 초안과 점수 기록


# ---------- 노드 ----------

def retrieve_node(state: ReviewState) -> dict:
    return {"references": retrieve(state["draft"]), "revision_count": 0}


def make_review_node(persona: str):
    """페르소나 하나를 담당하는 리뷰 노드를 만든다."""

    def review_node(state: ReviewState) -> dict:
        result = reviewer.review(persona, state["draft"], state["references"])
        return {"reviews": {persona: result}}

    return review_node


def synthesize_node(state: ReviewState) -> dict:
    reviews = state["reviews"]
    average = editor.average_score(reviews)
    round_record = {
        "round": state["revision_count"],
        "draft": state["draft"],
        "scores": {persona: review.score for persona, review in reviews.items()},
        "average_score": average,
    }
    return {
        "average_score": average,
        "synthesis": editor.synthesize(state["draft"], reviews),
        "history": [round_record],
    }


def revise_node(state: ReviewState) -> dict:
    revised = editor.revise(state["draft"], state["synthesis"], state["references"])
    return {"draft": revised, "revision_count": state["revision_count"] + 1}


def should_revise(state: ReviewState) -> str:
    """평균 점수가 기준 미만이고 수정 횟수가 남아 있으면 수정한다."""
    if state["average_score"] >= config.PASS_SCORE:
        return "done"
    if state["revision_count"] >= config.MAX_REVISIONS:
        return "done"
    return "revise"


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


def new_thread_config() -> dict:
    """리뷰 한 건마다 새 thread_id를 쓴다. 이 id로 나중에 결과를 다시 불러올 수 있다."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def save_graph_image(path: Path = GRAPH_IMAGE) -> None:
    """그래프 구조를 PNG로 저장한다. 렌더링은 mermaid.ink 서버가 해 주므로 인터넷이 필요하다."""
    path.parent.mkdir(exist_ok=True)
    png = build_graph().get_graph().draw_mermaid_png(max_retries=5, retry_delay=2.0)
    path.write_bytes(png)


# ---------- 실행 ----------

def main() -> None:
    draft_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/draft.md")
    draft = draft_path.read_text(encoding="utf-8")

    save_graph_image()
    print(f"그래프 이미지 저장: {GRAPH_IMAGE}")

    thread = new_thread_config()
    print(f"초안: {draft_path} / thread_id: {thread['configurable']['thread_id']}")

    with open_graph() as graph:
        for update in graph.stream({"draft": draft}, thread, stream_mode="updates"):
            for node, output in update.items():
                if node == "retrieve":
                    titles = dict.fromkeys(d.metadata["title"] for d in output["references"])
                    print(f"[retrieve] 기존 글 {len(titles)}편")
                elif node.startswith("review_"):
                    persona, review = next(iter(output["reviews"].items()))
                    print(f"[{node}] {reviewer.PERSONAS[persona]} {review.score}점")
                elif node == "synthesize":
                    fixes = output["synthesis"].fixes
                    print(f"[synthesize] 평균 {output['average_score']}점, 수정 사항 {len(fixes)}개")
                elif node == "revise":
                    print(f"[revise] {output['revision_count']}차 수정안 ({len(output['draft'])}자)")

        final = graph.get_state(thread).values

    print("\n===== 결과 =====")
    for record in final["history"]:
        label = "원본" if record["round"] == 0 else f"{record['round']}차 수정"
        print(f"{label}: 평균 {record['average_score']}점 {record['scores']}")
    print(f"\n[총평] {final['synthesis'].summary}")
    print("\n[남은 수정 사항]")
    print(editor.format_fixes(final["synthesis"].fixes))

    if final["revision_count"]:
        output_path = draft_path.with_name(f"{draft_path.stem}.revised.md")
        output_path.write_text(final["draft"], encoding="utf-8")
        print(f"\n최종 수정안 저장: {output_path}")


if __name__ == "__main__":
    main()
