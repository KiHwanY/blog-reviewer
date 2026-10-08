"""DB 연결 확인 스크립트.

blog_reviewer 스키마만 들여다본다. public 스키마는 다른 프로젝트의 데이터라 건드리지 않는다.
연결 문자열(비밀번호 포함)은 출력하지 않는다.
"""

import os

import psycopg
from dotenv import load_dotenv

SCHEMA = "blog_reviewer"


def psycopg_url() -> str:
    """.env의 DATABASE_URL을 psycopg가 이해하는 형태로 돌려준다.

    SQLAlchemy용 접두사(postgresql+psycopg://)가 붙어 있으면 떼어낸다.
    """
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    with psycopg.connect(psycopg_url()) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
        db, user, schema = conn.execute(
            "SELECT current_database(), current_user, current_schema()"
        ).fetchone()
        search_path = conn.execute("SHOW search_path").fetchone()[0]
        vector = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        can_create = conn.execute(
            "SELECT has_schema_privilege(current_user, %s, 'CREATE')", (SCHEMA,)
        ).fetchone()[0]
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1",
            (SCHEMA,),
        ).fetchall()

    print(f"PostgreSQL     : {version}")
    print(f"DB / 유저      : {db} / {user}")
    print(f"현재 스키마    : {schema}")
    print(f"search_path    : {search_path}")
    print(f"vector 확장    : {vector[0] if vector else '없음'}")
    print(f"{SCHEMA} CREATE 권한: {can_create}")
    print(f"{SCHEMA} 테이블: {[t[0] for t in tables] or '없음'}")

    assert schema == SCHEMA, f"기본 스키마가 {SCHEMA}가 아니다: {schema}"
    assert vector, "vector 확장이 설치되어 있지 않다"
    assert can_create, f"{SCHEMA} 스키마에 테이블을 만들 권한이 없다"
    print("OK")


if __name__ == "__main__":
    main()
