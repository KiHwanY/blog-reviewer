"""블로그 글 리뷰어 화면 (Streamlit).

    streamlit run app.py
"""

import streamlit as st

import config
import graph
import usage
from reviewer import PERSONAS

PRIORITY_COLORS = {"높음": "red", "중간": "orange", "낮음": "gray"}

st.set_page_config(page_title="블로그 글 리뷰어", page_icon=":material/rate_review:", layout="wide")


# ---------- 실행 ----------

def run_review(draft: str, pass_score: float) -> None:
    """그래프를 실행하면서 진행 상황을 보여주고, 결과를 세션에 저장한다."""
    thread = graph.thread_config()
    with st.status("리뷰를 진행하고 있습니다", expanded=True) as status:
        with graph.open_graph() as workflow:
            inputs = {"draft": draft, "pass_score": pass_score}
            for update in workflow.stream(inputs, thread, stream_mode="updates"):
                for node, output in update.items():
                    st.write(graph.describe_update(node, output))
            st.session_state.result = workflow.get_state(thread).values
        status.update(label="리뷰가 끝났습니다", state="complete", expanded=False)

    # 주소에 thread_id를 남겨 두면 새로고침해도 체크포인트에서 결과를 다시 불러온다
    st.query_params["thread"] = thread["configurable"]["thread_id"]


def load_saved_result(thread_id: str) -> None:
    """체크포인트에 저장된 리뷰 결과를 불러온다."""
    with graph.open_graph() as workflow:
        values = workflow.get_state(graph.thread_config(thread_id)).values
    if values.get("history"):
        st.session_state.result = values


# ---------- 결과 표시 ----------

def show_summary(result: dict) -> None:
    history = result["history"]
    first, last = history[0], history[-1]
    pass_score = result.get("pass_score", config.PASS_SCORE)
    used = result.get("usage", [])  # 사용량 기록을 넣기 전에 저장된 결과에는 없다

    with st.container(horizontal=True):
        st.metric("원본 평균", f"{first['average_score']}점", border=True)
        st.metric(
            "최종 평균",
            f"{last['average_score']}점",
            delta=round(last["average_score"] - first["average_score"], 1) or None,
            border=True,
        )
        st.metric("수정 횟수", f"{result['revision_count']}회", border=True)
        st.metric("기준 점수", f"{pass_score:g}점", border=True)
        if used:
            st.metric("예상 비용", f"${usage.total(used)['cost']:.2f}", border=True)

    reason = graph.stop_reason(result)
    if reason == "passed":
        st.success(graph.STOP_MESSAGES[reason], icon=":material/check_circle:")
    else:
        st.warning(
            f"{graph.STOP_MESSAGES[reason]} 평균 {last['average_score']}점으로 기준에 못 미쳤으니 "
            "아래 남은 수정 사항을 확인해 주세요.",
            icon=":material/warning:",
        )

    if used:
        with st.expander("LLM 사용량", icon=":material/payments:"):
            st.dataframe(
                used + [usage.total(used)],
                column_config={
                    "step": "단계",
                    "input_tokens": st.column_config.NumberColumn("입력 토큰", format="localized"),
                    "output_tokens": st.column_config.NumberColumn("출력 토큰", format="localized"),
                    "cost": st.column_config.NumberColumn("예상 비용", format="$%.3f"),
                },
                hide_index=True,
                alt="LLM 호출별 토큰 사용량과 예상 비용",
            )
            st.caption("토큰 수에 공개 단가를 곱한 값입니다. 실제 청구액은 Anthropic 콘솔에서 확인하세요.")


def show_reviews(record: dict) -> None:
    """세 페르소나의 리뷰를 나란히 보여준다."""
    for column, (persona, name) in zip(st.columns(len(PERSONAS), border=True), PERSONAS.items()):
        review = record["reviews"][persona]
        with column:
            st.metric(name, f"{review.score}점")
            st.markdown("**좋은 점**")
            st.markdown("\n".join(f"- {item}" for item in review.strengths))
            st.markdown("**고칠 점**")
            st.markdown("\n".join(f"- {item}" for item in review.improvements))


def show_synthesis(record: dict) -> None:
    synthesis = record["synthesis"]
    st.info(synthesis.summary, icon=":material/summarize:")
    for fix in synthesis.fixes:
        with st.container(border=True):
            with st.container(horizontal=True):
                st.badge(fix.priority, color=PRIORITY_COLORS[fix.priority])
                st.caption(" · ".join(fix.raised_by))
            st.markdown(f"**{fix.issue}**")
            st.markdown(f":material/arrow_forward: {fix.suggestion}")


def show_draft(record: dict) -> None:
    rendered, source = st.tabs(["미리보기", "마크다운"])
    with rendered:
        st.markdown(record["draft"])
    with source:
        st.code(record["draft"], language="markdown", wrap_lines=True)
    st.download_button(
        "마크다운 내려받기",
        record["draft"],
        file_name=f"draft_round{record['round']}.md",
        mime="text/markdown",
        icon=":material/download:",
    )


def show_result(result: dict) -> None:
    history = result["history"]
    show_summary(result)

    round_number = st.segmented_control(
        "라운드",
        range(len(history)),
        default=len(history) - 1,
        required=True,
        format_func=lambda n: f"{graph.round_label(n)} · {history[n]['average_score']}점",
        help="원본과 각 수정안이 받은 리뷰를 골라 볼 수 있습니다.",
    )
    record = history[round_number]
    is_original = record["round"] == 0

    st.subheader("페르소나별 리뷰")
    show_reviews(record)

    st.subheader("종합 결과")
    show_synthesis(record)

    st.subheader("리뷰한 원본" if is_original else f"{record['round']}차 수정안")
    if not is_original:
        st.caption("`[확인 필요: …]` 표시는 글쓴이가 직접 채워야 하는 자리입니다.")
    show_draft(record)


# ---------- 화면 ----------

st.title("블로그 글 리뷰어")
st.caption(
    "새 글 초안을 넣으면 기존 블로그 글을 근거로 초보 독자, 시니어 개발자, SEO 전문가가 리뷰하고, "
    "종합 결과와 수정안을 만들어 줍니다."
)

with st.sidebar:
    pass_score = st.slider(
        "기준 점수",
        min_value=1.0,
        max_value=10.0,
        value=config.PASS_SCORE,
        step=0.5,
        help="평균 점수가 이 값보다 낮으면 수정안을 만들어 다시 리뷰합니다.",
    )
    st.caption(f"수정은 최대 {config.MAX_REVISIONS}회까지 반복합니다.")
    st.caption(f"모델: {config.LLM_MODEL} · 임베딩: {config.EMBEDDING_MODEL}")

with st.form("draft_form"):
    draft = st.text_area(
        "초안",
        height=300,
        placeholder="# 제목\n\n마크다운으로 쓴 초안을 붙여 넣으세요.",
    )
    submitted = st.form_submit_button("리뷰 시작", type="primary", icon=":material/play_arrow:")
    st.caption("리뷰 한 번에 1~2분, 수정이 2회 반복되면 8분쯤 걸립니다.")

if submitted:
    if draft.strip():
        run_review(draft, pass_score)
    else:
        st.warning("초안을 입력해 주세요.")
elif "result" not in st.session_state and "thread" in st.query_params:
    load_saved_result(st.query_params["thread"])

if "result" in st.session_state:
    show_result(st.session_state.result)
