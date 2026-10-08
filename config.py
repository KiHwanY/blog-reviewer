"""공통 설정: .env 로딩, DB URL, LLM·임베딩·벡터 저장소 생성.

비밀값(API 키, DB 비밀번호)은 .env에서만 읽는다. 여기에는 비밀이 아닌 설정만 둔다.
"""

import os
from functools import lru_cache

# 임베딩 모델은 로컬 캐시만 쓴다. 이 값이 없으면 로딩할 때마다 Hugging Face에
# 버전을 확인하러 가고, 연결이 불안정하면 시작이 몇 분씩 늦어진다.
# huggingface 관련 import보다 먼저 설정해야 적용된다.
# 모델을 처음 내려받을 때만 HF_HUB_OFFLINE=0으로 실행한다.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

load_dotenv()

BLOG_URL = "https://drg2524.tistory.com"

SCHEMA = "blog_reviewer"
COLLECTION = "blog_posts"

LLM_MODEL = "claude-opus-5-5"
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

PASS_SCORE = 7.0  # 평균 점수가 이 값 미만이면 수정안을 만든다
MAX_REVISIONS = 2  # 수정 → 재리뷰 반복 횟수 상한


def sqlalchemy_url() -> str:
    """PGVector(SQLAlchemy)용 연결 문자열. .env의 값을 그대로 쓴다."""
    return os.environ["DATABASE_URL"]


def psycopg_url() -> str:
    """psycopg를 직접 쓰는 곳(PostgresSaver 등)용 연결 문자열.

    SQLAlchemy용 접두사(postgresql+psycopg://)를 떼어낸다.
    """
    return sqlalchemy_url().replace("postgresql+psycopg://", "postgresql://", 1)


def get_llm(max_tokens: int = 16000) -> ChatAnthropic:
    """리뷰와 수정안 생성에 쓰는 LLM. ANTHROPIC_API_KEY는 환경변수에서 자동으로 읽힌다.

    max_tokens에는 모델의 생각(thinking) 분량도 포함된다. 긴 글을 통째로 받을 때는
    넉넉히 주고, 그런 긴 응답은 타임아웃을 피하려고 스트리밍으로 받는다.
    """
    return ChatAnthropic(model=LLM_MODEL, max_tokens=max_tokens, streaming=max_tokens > 16000)


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """bge-m3 임베딩. 모델 로딩이 무거워서 프로세스당 한 번만 만든다."""
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )


def get_vector_store() -> PGVector:
    """blog_posts 컬렉션. 테이블은 search_path 첫 번째인 blog_reviewer 스키마에 생긴다."""
    return PGVector(
        embeddings=get_embeddings(),
        connection=sqlalchemy_url(),
        collection_name=COLLECTION,
        embedding_length=EMBEDDING_DIM,
        create_extension=False,  # vector 확장은 이미 설치되어 있다
    )
