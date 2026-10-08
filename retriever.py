"""초안과 관련된 기존 글 검색.

청크를 넉넉히 뽑은 뒤 글 단위로 묶어, 서로 다른 글 몇 편을 근거로 돌려준다.
(청크 상위 N개만 쓰면 한 글이 결과를 독차지하는 경우가 많다.)
"""

from langchain_core.documents import Document

import config

QUERY_CHARS = 1500  # 초안 앞부분(제목 + 도입부)만 검색 질의로 쓴다
FETCH_K = 20  # 먼저 뽑는 청크 수
MAX_DISTANCE = 0.5  # 코사인 거리가 이보다 멀면 무관한 글로 본다
MAX_POSTS = 4  # 근거로 쓸 글 수
CHUNKS_PER_POST = 2  # 글 하나당 발췌 수


def retrieve(draft: str) -> list[Document]:
    """초안과 관련된 기존 글 발췌를 가까운 글 순서로 돌려준다. 관련 글이 없으면 빈 목록."""
    store = config.get_vector_store()
    results = store.similarity_search_with_score(draft[:QUERY_CHARS], k=FETCH_K)

    chunks_by_post: dict[str, list[Document]] = {}  # 결과가 가까운 순이라 dict 순서도 가까운 글 순
    for doc, distance in results:
        if distance > MAX_DISTANCE:
            continue
        doc.metadata["distance"] = round(distance, 3)
        chunks = chunks_by_post.setdefault(doc.metadata["url"], [])
        if len(chunks) < CHUNKS_PER_POST:
            chunks.append(doc)

    posts = list(chunks_by_post.values())[:MAX_POSTS]
    return [chunk for chunks in posts for chunk in chunks]


def format_references(references: list[Document]) -> str:
    """검색된 발췌를 프롬프트에 넣을 텍스트로 만든다."""
    if not references:
        return "(관련된 기존 글을 찾지 못했습니다.)"

    blocks = []
    for doc in references:
        meta = doc.metadata
        blocks.append(
            f"<기존글 제목=\"{meta['title']}\" 카테고리=\"{meta['category']}\" "
            f"작성일=\"{meta['published_at'][:10]}\" url=\"{meta['url']}\">\n"
            f"{doc.page_content}\n"
            f"</기존글>"
        )
    return "\n\n".join(blocks)
