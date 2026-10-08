"""검색 테스트: 질문을 넣었을 때 관련 글이 잘 나오는지 눈으로 확인한다.

    python search_test.py                 # 준비된 질문들로 테스트
    python search_test.py "내 질문"        # 직접 질문
"""

import sys
import time

import config

QUESTIONS = [
    "JPA에서 N+1 문제는 어떻게 해결해?",
    "스프링 시큐리티로 로그인 구현하는 방법",
    "쿠버네티스 클러스터 백업은 어떻게 하지?",
    "SOLID 원칙이 뭐야?",
    "바이브 코딩으로 프로젝트 만든 경험",
    "무례한 사람을 대하는 방법",
    "How do I ship logs to Loki?",  # 영어 질문 → 한국어 글
    "김치찌개 맛있게 끓이는 법",  # 블로그에 없는 주제
]

TOP_K = 4


def search(question: str) -> None:
    store = config.get_vector_store()
    started = time.time()
    results = store.similarity_search_with_score(question, k=TOP_K)
    elapsed = time.time() - started

    print(f"\nQ. {question}  ({elapsed:.2f}초)")
    for doc, distance in results:
        meta = doc.metadata
        print(f"  {distance:.3f} | {meta['category']} | {meta['title']} (#{meta['chunk']})")


def main() -> None:
    questions = sys.argv[1:] or QUESTIONS
    print("코사인 거리: 낮을수록 가깝다")
    for question in questions:
        search(question)


if __name__ == "__main__":
    main()
