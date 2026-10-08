# pgvector + LangChain으로 RAG 벡터 검색 구현하기 (bge-m3 한국어 임베딩)

### Intro

안녕하세요. 환이s입니다 👋

이 글은 Docker로 pgvector를 띄우고 LangChain PGVector와 bge-m3로 한국어 블로그 글을 의미 검색하는 RAG 검색 단계 구현기입니다.

이전 글 [[Vibe Coding] 지역 블로그 AI 에이전트 구축기 (feat. Claude + pgvector)](https://drg2524.tistory.com/259)의 후속 글입니다. 그 글에서는 pgvector로 기존 글과의 유사도를 비교해 중복 글을 막았습니다. 이번에는 LangChain을 붙여 제 블로그 글 자체를 의미로 검색해 보겠습니다.

> RAG(Retrieval-Augmented Generation) = 질문과 관련된 문서를 먼저 찾고(검색), 그 문서를 LLM에 함께 넘겨 답을 만들게 하는(생성) 방식입니다.

RAG는 검색과 생성 두 단계로 나뉘는데, 이 글은 그중 **검색 단계까지만** 다룹니다. 요즘 RAG 이야기가 많아서 저도 직접 해봤는데, 생각보다 쉽게 검색 단계까지 만들 수 있었습니다. 생성 단계는 다음 글에서 LangGraph를 붙이면서 이어가겠습니다.

이번 글에서 다루는 내용은 다음과 같습니다.

- Docker로 pgvector(pg16) 실행하기 (비밀번호·볼륨·포트 설정, 정상 실행 확인 포함)
- bge-m3 한국어 임베딩과 LangChain PGVector로 블로그 글 저장하기 (`ingest.py`)
- `similarity_search_with_score`로 의미 기반 검색을 하고 점수 읽는 법 (`search.py`)
- 운영 시 알아둘 점 (collection_name, 고정 id, 재적재, HNSW 인덱스)
  - HNSW 인덱스 = 근사 최근접 검색용 인덱스입니다. 전체를 다 비교하지 않기 때문에 빠릅니다.

준비물은 다음과 같습니다.

- Docker
- Python [확인 필요: 사용한 Python 버전]
- 메모리 [확인 필요: 테스트한 PC의 메모리 용량 / bge-m3 로딩 시 필요했던 메모리]
- 디스크 여유 공간 : 첫 실행 때 bge-m3 모델을 약 2GB 이상 내려받습니다.
- GPU는 없어도 됩니다. 저는 CPU만으로 진행했습니다.

### 1. Docker로 pgvector(pg16) 실행하기

먼저 **벡터 DB**가 필요합니다. 벡터 DB는 숫자 배열(벡터)을 저장해 두고, 주어진 벡터와 가까운 것을 찾아 주는 DB를 말합니다. pgvector는 PostgreSQL에 벡터 타입과 거리 연산자를 추가해 주는 확장입니다. 그래서 평소 쓰던 Postgres를 그대로 벡터 DB로 쓸 수 있습니다.

컨테이너는 pgvector 프로젝트가 배포하는 이미지(`pgvector/pgvector:pg16`)로 띄웁니다. 이 이미지에는 pgvector가 미리 설치되어 있습니다. Docker 공식(Official) 이미지인 `postgres`와는 다른 이미지입니다.

비밀번호는 코드나 명령에 직접 적지 않고 환경 변수로 넘기겠습니다. 뒤에서 실행할 파이썬 스크립트도 이 환경 변수를 읽으므로, **같은 터미널**에서 이어서 진행해 주세요.

```bash
export PGVECTOR_PASSWORD='<비밀번호>'

docker run -d \
  --name pgvector-db \
  -e POSTGRES_PASSWORD="$PGVECTOR_PASSWORD" \
  -p 127.0.0.1:5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  pgvector/pgvector:pg16
```

- `-e POSTGRES_PASSWORD` : 이 옵션이 빠지면 초기화 단계에서 오류가 나고 컨테이너가 바로 종료됩니다.
- `-p 127.0.0.1:5432:5432` : 내 PC(localhost)에서만 접속할 수 있도록 포트를 엽니다. `-p 5432:5432`로 쓰면 모든 네트워크 인터페이스에 DB가 노출됩니다. 로컬 실습 용도라면 `127.0.0.1`을 붙이는 것을 권장합니다.
- `-v pgdata:/var/lib/postgresql/data` : 볼륨이 없으면 컨테이너를 다시 만들 때 저장해 둔 임베딩이 모두 사라집니다.
- 계정과 DB를 따로 지정하지 않았기 때문에 기본값인 `postgres` 계정과 `postgres` DB가 만들어집니다.

볼륨 설정과 외부 접속 구성은 이전 글 [[ Docker ] PostgreSQL Docker 볼륨 설정 및 외부 접속 구성하기](https://drg2524.tistory.com/228)에서 더 자세히 정리해 두었습니다. 다른 PC에서 접속해야 한다면 그 글을 참고해 주세요.

#### 1-1. pgvector 컨테이너 정상 실행 확인 (docker ps, docker logs)

컨테이너가 제대로 떴는지 확인합니다.

```bash
docker ps
```

목록에 `pgvector-db`가 있고 STATUS 열이 `Up ...`으로 표시되면 실행 중인 상태입니다. 목록에 없다면 컨테이너가 시작 직후 종료된 것이니 로그를 확인해 주세요.

```bash
docker logs pgvector-db
```

로그 마지막 부분에 `database system is ready to accept connections`가 보이면 접속할 준비가 된 것입니다.

#### 1-2. 5432 포트 충돌 시 대처법

이전 글(228)에서 만든 `postgres-db` 컨테이너가 이미 5432 포트를 쓰고 있다면 `docker run`이 포트 충돌로 실패합니다. 이때는 둘 중 하나를 선택하면 됩니다.

- 기존 컨테이너 중지 : `docker stop postgres-db` 후 다시 실행합니다.
- 다른 포트 사용 : `-p 127.0.0.1:5433:5432`로 바꿔 실행합니다. 이 경우 뒤의 파이썬 코드에 있는 접속 URL 포트도 `5433`으로 바꿔 주세요.

실패한 컨테이너가 남아 있으면 이름이 겹쳐 다시 실행되지 않습니다. 재실행 전에 `docker rm pgvector-db`로 먼저 지워 주세요.

#### 1-3. CREATE EXTENSION vector는 따로 실행해야 하나요?

이미지에 pgvector가 설치되어 있어도, DB에서 확장을 활성화하는 단계는 따로 필요합니다. LangChain PGVector는 기본 설정에서 `CREATE EXTENSION IF NOT EXISTS vector`를 자동으로 실행합니다. 이 글처럼 기본 `postgres` 계정으로 접속하면 이 자동 생성이 그대로 동작합니다. `postgres` 계정은 **슈퍼유저**, 즉 모든 권한을 가진 DB 관리자 계정이기 때문입니다.

권한이 제한된 계정으로 접속할 때는 pgvector 버전을 확인해야 합니다. 확장이 trusted로 표시되어 있으면 DB에 CREATE 권한이 있는 일반 계정도 실행할 수 있고, 그렇지 않으면 슈퍼유저 권한이 필요합니다. 아래 명령으로 버전과 trusted 여부를 확인할 수 있습니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "SELECT name, version, superuser, trusted FROM pg_available_extension_versions WHERE name = 'vector';"
```

[확인 필요: 사용한 이미지의 pgvector 버전과 위 쿼리의 superuser/trusted 결과]

일반 계정으로 확장을 만들 수 없는 경우에는, 슈퍼유저로 아래 명령을 먼저 실행해 둡니다. 그다음 PGVector에 `create_extension=False`를 넘기면 됩니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. bge-m3 임베딩과 LangChain PGVector로 문서 저장

이 단계에서 쓰는 용어를 먼저 정리하겠습니다.

- **임베딩** = 글을 의미를 담은 숫자 배열(벡터)로 바꾸는 것입니다. 의미가 비슷한 글일수록 벡터끼리 가까워집니다. 그래서 키워드가 정확히 일치하지 않아도 찾을 수 있는 **의미 검색**이 가능해집니다.
- **bge-m3** = BAAI가 무료로 공개한 다국어 임베딩 모델입니다. 한국어를 지원해서 **한국어 임베딩** 용도로 쓸 수 있고, 1024차원 벡터를 만듭니다.
- **청크** = 긴 글을 임베딩하기 좋은 길이로 자른 조각입니다.
- **LangChain** = LLM 애플리케이션을 만들 때 쓰는 파이썬 프레임워크입니다. 임베딩 모델, 벡터 저장소, 텍스트 분할기 등을 같은 방식으로 다룰 수 있게 해 줍니다.

#### 2-1. 패키지 설치 (langchain_community 대신 langchain_postgres 기준)

```bash
pip install -U langchain-postgres "psycopg[binary]" langchain-huggingface sentence-transformers langchain-text-splitters
```

제가 설치한 버전은 다음과 같습니다.

[확인 필요: `pip show langchain-postgres langchain-huggingface sentence-transformers langchain-text-splitters` 로 확인한 실제 버전]

> 참고로 `langchain_community.vectorstores`의 PGVector는 deprecated 상태입니다. deprecated는 더 이상 사용을 권장하지 않아 이후 버전에서 제거될 수 있다는 뜻입니다. 이 글은 별도 패키지인 `langchain_postgres`를 기준으로 작성했습니다. 아래 코드의 `connection=` 인자도 `langchain_postgres` 기준입니다.

#### 2-2. ingest.py로 블로그 글을 pgvector에 저장하기

이 스크립트는 `posts/` 폴더에 있는 `.md` 파일을 읽어서 청크로 나누고, 임베딩해서 pgvector에 저장합니다. 그래서 실행하는 위치에 **`posts/` 폴더와 `.md` 파일이 있어야 합니다.**

블로그 글이 따로 없다면 아래처럼 예시 파일 3개를 만들어 따라 하셔도 됩니다.

```bash
mkdir -p posts

cat > posts/jpa-n-plus-1.md << 'EOF'
# JPA N+1 문제 정리
연관 관계가 있는 엔티티를 조회할 때, 목록 조회 쿼리 1번 뒤에 연관 엔티티 조회 쿼리가 N번 추가로 나가는 문제입니다.
fetch join이나 EntityGraph로 한 번에 가져오면 해결할 수 있습니다.
EOF

cat > posts/docker-postgres-volume.md << 'EOF'
# Docker PostgreSQL 볼륨 설정
Docker 볼륨을 연결하면 컨테이너를 삭제하고 다시 만들어도 DB 데이터가 유지됩니다.
-v 옵션으로 볼륨을 /var/lib/postgresql/data 경로에 연결합니다.
EOF

cat > posts/spring-board.md << 'EOF'
# Spring 게시판 목록/글쓰기 구현
Controller에서 목록 데이터를 Map에 담아 뷰로 넘기고, 글쓰기는 세션의 사용자 id를 작성자로 저장합니다.
mapper 파일에 select문과 insert문을 작성합니다.
EOF
```

아래 코드를 `ingest.py`로 저장하고, `posts/` 폴더가 있는 위치에서 실행합니다.

```bash
python ingest.py
```

**처음 실행할 때는 bge-m3 모델(약 2GB 이상)을 내려받느라 한동안 아무 출력 없이 멈춘 것처럼 보일 수 있습니다.** 다운로드는 첫 실행 때 한 번만 하고, 이후에는 캐시된 모델을 씁니다.

```python
# ingest.py
import os
from pathlib import Path
from urllib.parse import quote_plus

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

COLLECTION = "blog_posts"

# 1) bge-m3 임베딩 모델 로딩 (GPU 없이 CPU로 실행, 첫 실행 시 모델 다운로드)
emb = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    model_kwargs={"device": "cpu"},
    encode_kwargs={
        "normalize_embeddings": True,  # 벡터 길이를 1로 맞춤
        "batch_size": 32,  # 한 번에 임베딩할 청크 수 [확인 필요: 실제 사용한 배치 크기]
    },
)

# 2) 접속 URL 형식: postgresql+psycopg://<사용자>:<비밀번호>@<호스트>:<포트>/<DB>
#    비밀번호는 환경 변수에서 읽습니다. (특수문자가 있어도 되도록 quote_plus 처리)
password = quote_plus(os.environ["PGVECTOR_PASSWORD"])
url = f"postgresql+psycopg://postgres:{password}@localhost:5432/postgres"  # 포트를 바꿨다면 5433 등으로 수정

# 3) 블로그 글 로딩
# [확인 필요: 실제로 글을 어떤 형식/경로에서 불러왔는지 (예: 마크다운 파일 폴더, 크롤링 결과 등)]
posts_dir = Path("posts")
raw_docs = [
    Document(
        page_content=p.read_text(encoding="utf-8"),
        metadata={"title": p.stem, "source": str(p)},
    )
    for p in sorted(posts_dir.glob("*.md"))
]

# 4) 청크 분할 (800자 단위)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,  # [확인 필요: 실제 사용한 overlap 값]
)

docs, ids = [], []
for raw in raw_docs:
    for i, chunk in enumerate(splitter.split_documents([raw])):
        docs.append(chunk)
        # 컬렉션명을 접두어로 붙인 고정 id (이유는 4-2 참고)
        ids.append(f"{COLLECTION}:{raw.metadata['source']}#{i}")

# 5) 벡터 저장소 생성 및 저장
store = PGVector(
    embeddings=emb,
    collection_name=COLLECTION,
    connection=url,
    embedding_length=1024,  # bge-m3 차원 수 (HNSW 인덱스를 걸려면 필요)
    use_jsonb=True,
)
store.add_documents(docs, ids=ids)

print(f"글 {len(raw_docs)}개 → 청크 {len(docs)}개 저장 완료")
```

- `normalize_embeddings=True` : 벡터의 길이를 1로 맞춰 줍니다. 길이가 같아지기 때문에 벡터의 방향만으로 비교하게 됩니다.
- `RecursiveCharacterTextSplitter`는 기본적으로 글자 수로 길이를 잽니다. 그래서 `chunk_size=800`은 청크 하나가 800자 안쪽이라는 뜻입니다.
- id에 `blog_posts:` 같은 컬렉션명을 붙인 이유는, id가 컬렉션별이 아니라 테이블 전체에서 겹치면 안 되는 값일 수 있기 때문입니다. 자세한 내용은 4-2에서 다룹니다.

**저장이 잘 됐는지 확인하기**

스크립트가 끝나면 마지막 줄에 저장한 청크 수가 출력됩니다. DB에도 같은 수가 들어갔는지 확인합니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "SELECT c.name, count(*) FROM langchain_pg_embedding e JOIN langchain_pg_collection c ON e.collection_id = c.uuid GROUP BY c.name;"
```

`blog_posts` 행의 count가 스크립트가 출력한 청크 수와 같으면 정상입니다. 위 예시 파일 3개로 따라 하셨다면 세 글 모두 800자보다 짧아 청크가 하나씩 나오므로 `3`이 나와야 합니다.

#### 2-3. CPU로 bge-m3 임베딩 3,000개 저장한 소요 시간

- **청크 크기를 800자로 정한 이유** : [확인 필요: 800자를 고른 이유]
- **저장한 양** : 3,000개 [확인 필요: 3,000개가 블로그 글 수인지, 분할 후 청크 수인지]
- **소요 시간** : [확인 필요: 3,000개를 저장하는 데 실제로 걸린 시간(분), 모델 다운로드 시간 제외 여부]
- **실행 환경** : GPU 없이 CPU만 사용했습니다. [확인 필요: CPU 모델 / 코어 수], 배치 크기 [확인 필요]

GPU가 없다 보니 시간이 꽤 걸렸습니다. 따라 하실 때 위 수치와 비슷한 속도라면 정상적으로 진행되고 있다고 보시면 됩니다.

### 3. similarity_search로 의미 기반 검색하기

검색은 저장과 분리해서 별도 스크립트인 `search.py`로 만듭니다. `ingest.py`를 다시 실행하면 임베딩을 처음부터 다시 하기 때문입니다. `search.py`에서는 `emb`와 `store`만 같은 설정으로 다시 만들고, `add_documents`는 호출하지 않습니다.

가장 간단한 검색은 아래 한 줄입니다.

```python
store.similarity_search("JPA N+1 문제", k=4)
```

`k`는 돌려받을 결과 개수입니다. 이렇게 하면 관련 글 4개가 `Document` 리스트로 돌아옵니다. 다만 `similarity_search`는 **점수를 돌려주지 않습니다.** 점수까지 보려면 `similarity_search_with_score`를 씁니다.

아래 코드를 `search.py`로 저장하고 `python search.py`로 실행합니다. `PGVECTOR_PASSWORD` 환경 변수가 설정된 터미널에서 실행해야 합니다.

```python
# search.py
import os
from urllib.parse import quote_plus

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

COLLECTION = "blog_posts"

# ingest.py와 같은 모델·설정이어야 같은 공간의 벡터로 비교됩니다.
emb = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

password = quote_plus(os.environ["PGVECTOR_PASSWORD"])
url = f"postgresql+psycopg://postgres:{password}@localhost:5432/postgres"

store = PGVector(
    embeddings=emb,
    collection_name=COLLECTION,
    connection=url,
    embedding_length=1024,
    use_jsonb=True,
)

results = store.similarity_search_with_score("JPA N+1 문제", k=4)
for doc, distance in results:
    print(f"거리 {distance:.4f} (유사도 {1 - distance:.4f})  {doc.metadata['title']}")
```

실제 출력은 다음과 같습니다.

```
[확인 필요: "JPA N+1 문제" 질의의 실제 출력 (상위 4개 글 제목과 점수)]
```

#### 3-1. 점수 읽는 법: 유사도가 아니라 거리입니다

**코사인 유사도**는 두 벡터의 방향이 얼마나 비슷한지를 나타내는 값으로, 1에 가까울수록 비슷합니다. 그런데 `similarity_search_with_score`가 돌려주는 값은 코사인 유사도가 아닙니다. pgvector의 `<=>` 연산자로 계산한 **코사인 거리**입니다.

- **거리는 낮을수록 가깝습니다(비슷합니다).**
- **유사도 = 1 - 거리**

`<=>` 연산자와 유사도 임계값 기준은 [[Vibe Coding] 지역 블로그 AI 에이전트 구축기 (feat. Claude + pgvector)](https://drg2524.tistory.com/259)의 '4-4. PostgreSQL + pgvector로 의미 기반 중복 방지'에서 다뤘습니다. 그 글의 "유사도 0.8688, 임계값 0.85"는 1 - 거리로 환산한 **유사도** 기준입니다. 이 글의 출력처럼 거리로 바꾸면 임계값 0.85는 거리 0.15, 0.8688은 거리 약 0.1312에 해당합니다. 두 글의 숫자를 비교하실 때는 어느 쪽이 거리이고 어느 쪽이 유사도인지 먼저 확인해 주세요.

다만 이 환산은 단위를 바꾼 것일 뿐, 기준값을 그대로 가져다 쓸 수 있다는 뜻은 아닙니다. 임베딩 모델이 다르면 점수 분포 자체가 달라집니다. 모델이 다르므로 bge-m3에서는 임계값을 다시 잡아야 합니다. [확인 필요: 259번 글에서 사용한 로컬 한국어 임베딩 모델명. bge-m3와 같은 모델이라면 이 문단 수정 필요]

#### 3-2. bge-m3 한국어 임베딩 확인 (영어 질의로 한글 글 검색)

검색하면서 가장 신기했던 점은, 영어로 물어봐도 한글로 쓴 글이 검색된다는 것이었습니다. bge-m3가 한국어에서도 잘 동작한다고 판단한 근거는 다음 결과입니다.

```
[확인 필요: 실제로 던진 영어 질의와 그 결과로 나온 한글 글 제목·점수]
```

### 4. 운영 시 알아둘 점

#### 4-1. collection_name은 테이블 이름이 아닙니다

PGVector는 처음 실행할 때 `langchain_pg_collection`과 `langchain_pg_embedding` 두 테이블을 알아서 만들어 줍니다. `collection_name="blog_posts"`를 넘겨도 `blog_posts`라는 테이블이 생기지는 않습니다. `langchain_pg_collection`에 `blog_posts`라는 이름의 행이 하나 생기고, 실제 임베딩은 모두 `langchain_pg_embedding`에 저장됩니다. 각 임베딩이 어느 컬렉션에 속하는지는 `collection_id`로 구분합니다. 즉, 컬렉션은 한 쌍의 테이블 안에서 데이터를 나누는 논리적인 구분값입니다.

이전 글 [[Vibe Coding] 지역 블로그 AI 에이전트 구축기 (feat. Claude + pgvector)](https://drg2524.tistory.com/259)에서 직접 만든 `blog_posts` 테이블과는 이름만 같고 전혀 다른 것입니다. 헷갈리지 않으셨으면 합니다.

#### 4-2. 고정 id에 컬렉션명을 접두어로 붙이는 이유

컬렉션이 논리적인 구분일 뿐이라면, `langchain_pg_embedding`의 `id`는 컬렉션별 키가 아니라 테이블 전체의 기본키일 수 있습니다. 그렇다면 다른 컬렉션에 같은 id(예: `posts/a.md#0`)를 넣을 때 기존 컬렉션의 행이 덮어쓰기됩니다. 그래서 `ingest.py`에서는 `blog_posts:posts/a.md#0`처럼 컬렉션명을 접두어로 붙였습니다.

사용 중인 버전에서 어떻게 되어 있는지는 아래 명령으로 직접 확인할 수 있습니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "\d langchain_pg_embedding"
```

출력의 Indexes 항목에서 기본키(`PRIMARY KEY`)가 `id` 하나로만 잡혀 있다면, id는 테이블 전체에서 겹치면 안 되는 값입니다. 기본키에 `collection_id`가 함께 묶여 있지 않다는 뜻입니다.

[확인 필요: 사용한 langchain-postgres 버전과 위 명령으로 확인한 기본키 구성]

#### 4-3. add_documents를 다시 실행하면 중복 저장되나요?

`ids`를 넘기지 않으면 실행할 때마다 새 id가 발급되어 같은 문서가 계속 쌓입니다. `ingest.py`처럼 고정 id를 넘기면, 같은 id는 새로 추가되지 않고 덮어쓰기(upsert)됩니다. 그래서 몇 번을 다시 실행해도 결과가 같습니다.

단, 글이 짧아져 청크 수가 줄면 이전의 뒷번호 청크가 그대로 남습니다. 지울 id를 일일이 찾기보다는, 다시 저장하기 전에 해당 글(source)의 기존 청크를 메타데이터 기준으로 한꺼번에 지우는 편이 확실합니다. `ingest.py`의 `store = PGVector(...)` 아래 부분을 다음처럼 바꾸면 됩니다.

```python
from sqlalchemy import create_engine, text

engine = create_engine(url)

def delete_chunks(source: str) -> None:
    """해당 source(파일 경로)로 저장된 기존 청크를 모두 지웁니다."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM langchain_pg_embedding
                WHERE collection_id = (
                    SELECT uuid FROM langchain_pg_collection WHERE name = :collection
                )
                AND cmetadata->>'source' = :source
            """),
            {"collection": COLLECTION, "source": source},
        )

# 글 단위로 "기존 청크 삭제 → 새 청크 저장"
for raw in raw_docs:
    source = raw.metadata["source"]
    chunks = splitter.split_documents([raw])
    delete_chunks(source)
    store.add_documents(
        chunks,
        ids=[f"{COLLECTION}:{source}#{i}" for i in range(len(chunks))],
    )
```

`use_jsonb=True`로 저장했기 때문에 메타데이터는 `cmetadata` JSONB 컬럼에 들어 있습니다. 그래서 `cmetadata->>'source'`로 조회할 수 있습니다. 청크 id를 꼭 지정해서 지우고 싶다면 `store.delete(ids=[...])`도 쓸 수 있습니다.

다만 upsert든 삭제 후 저장이든, 이 방식은 실행할 때마다 **모든 글을 다시 임베딩**합니다. CPU 환경에서는 이 비용이 꽤 큽니다. 글 내용의 해시(예: `hashlib.sha256`)를 메타데이터에 함께 저장해 두고, 다음 실행 때 해시가 같은 글은 건너뛰면 바뀐 글만 다시 임베딩할 수 있습니다. 이 부분은 후속 글에서 따로 정리해 보겠습니다.

#### 4-4. 기본 상태에는 벡터 인덱스(HNSW)가 없습니다

인덱스가 없으면 검색할 때마다 **순차 스캔**이 일어납니다. 순차 스캔은 테이블의 모든 행을 처음부터 끝까지 하나씩 비교하는 방식입니다. **HNSW**는 근사 최근접 검색용 인덱스로, 전체를 다 비교하지 않기 때문에 빠릅니다. 대신 결과가 근사값이라 정확히 가장 가까운 것을 놓칠 수도 있습니다.

bge-m3의 1024차원은 pgvector HNSW 인덱스의 한도(2000차원) 안에 있으므로 HNSW 인덱스를 걸 수 있습니다. 다만 인덱스를 걸려면 컬럼에 차원이 고정되어 있어야 합니다. 그래서 `ingest.py`처럼 테이블을 처음 만들 때 `embedding_length=1024`를 넘겨 두어야 합니다.

인덱스는 컨테이너 안의 psql로 생성합니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "CREATE INDEX ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops);"
```

`vector_cosine_ops`는 이 인덱스를 코사인 거리(`<=>`) 기준으로 만들라는 지정입니다. PGVector의 기본 거리 방식이 코사인이므로 그에 맞춘 것입니다.

**필터와 함께 쓸 때 주의할 점**

이 인덱스는 특정 컬렉션이 아니라 `langchain_pg_embedding` 테이블 전체, 즉 **모든 컬렉션에 걸리는 인덱스**입니다. LangChain은 검색할 때 `collection_id`로 필터링합니다. 그런데 HNSW는 먼저 인덱스에서 후보를 뽑고 나서 필터를 적용합니다. 후보 수는 기본 `hnsw.ef_search`=40개입니다. 그래서 다른 컬렉션의 데이터가 많으면 필터를 통과하는 결과가 k개보다 적게 나오거나, recall(찾아야 할 결과를 실제로 찾은 비율)이 떨어질 수 있습니다.

pgvector 0.8 이상에서는 iterative scan을 켜서 결과가 부족할 때 인덱스를 더 탐색하게 할 수 있습니다. `ef_search`를 올려 후보 수를 늘리는 방법도 있습니다.

```sql
SET hnsw.iterative_scan = relaxed_order;  -- pgvector 0.8 이상
SET hnsw.ef_search = 100;
```

`SET`은 해당 세션에만 적용됩니다. LangChain 연결에 이 설정을 적용하는 방법은 파라미터 튜닝과 함께 후속 글에서 다루겠습니다. 이 글처럼 컬렉션이 `blog_posts` 하나뿐이라면 필터로 걸러지는 행이 없으므로 이 문제는 드러나지 않습니다.

**인덱스를 실제로 타는지 확인하기**

`EXPLAIN ANALYZE`로 실행 계획을 보면 됩니다. 아래는 저장된 임베딩 하나를 기준으로 가까운 4개를 찾는 쿼리입니다.

```bash
docker exec -it pgvector-db psql -U postgres -c "EXPLAIN ANALYZE SELECT id FROM langchain_pg_embedding ORDER BY embedding <=> (SELECT embedding FROM langchain_pg_embedding LIMIT 1) LIMIT 4;"
```

계획에 `Index Scan using ..._embedding_idx`처럼 HNSW 인덱스 이름이 보이면 인덱스를 탄 것입니다. `Seq Scan on langchain_pg_embedding`이 보이면 순차 스캔입니다. 행 수가 적으면 PostgreSQL이 순차 스캔이 더 싸다고 판단해 인덱스를 쓰지 않을 수도 있습니다.

참고로 3,000건 규모라면 순차 스캔으로도 충분할 수 있습니다. 인덱스는 데이터가 늘어 검색이 느려졌을 때 걸어도 늦지 않습니다. 인덱스 파라미터 튜닝과 인덱스 적용 전후 비교는 범위가 커서 후속 글에서 따로 다루겠습니다.

### 마무리

이번 글에서는 Docker로 pgvector를 띄우고, bge-m3 한국어 임베딩과 LangChain PGVector로 제 블로그 글을 저장한 뒤 의미 검색하는 데까지 정리했습니다.

즉, 여기서 확인할 수 있는 핵심은

- pgvector는 결국 Postgres라서, 벡터 DB를 따로 배우지 않고도 익숙한 환경에서 의미 검색을 붙일 수 있다는 점
- `similarity_search_with_score`의 점수는 코사인 **거리**이므로 낮을수록 비슷하고, 유사도는 1 - 거리로 계산한다는 점. 임베딩 모델이 바뀌면 임계값도 다시 잡아야 한다는 점
- 운영 단계에서는 collection_name의 의미, 컬렉션명을 붙인 고정 id, 재적재 시 기존 청크 정리, HNSW 인덱스와 필터의 관계를 함께 챙겨야 한다는 점

입니다.

RAG를 검색과 생성으로 나눈다면, 이 글은 검색 단계까지입니다. 다음 글에서는 여기에 LangGraph를 붙여, 검색한 글을 바탕으로 답을 만드는 생성 단계까지 이어가 보겠습니다.

[확인 필요: 다음 글 발행 후 제목과 링크 추가]