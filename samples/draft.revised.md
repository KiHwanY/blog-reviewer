# pgvector LangChain 벡터 검색 구현 (bge-m3 한국어 임베딩)

### Intro

안녕하세요. 환이s입니다 👋

Docker로 pgvector를 띄우고, bge-m3 한국어 임베딩과 LangChain PGVector로 블로그 글을 유사도 검색하는 과정을 코드와 함께 정리합니다. RAG에서 검색 단계에 해당하는 부분입니다. LangChain은 LLM과 벡터 DB 연동을 묶어 주는 파이썬 프레임워크입니다.

준비물: Docker, Python [확인 필요: 버전]

1. Docker로 pgvector(PostgreSQL 16) 띄우기
2. bge-m3 임베딩과 청크 분할
3. LangChain PGVector로 유사도 검색하기

### 1. Docker로 pgvector(PostgreSQL 16) 띄우기

pgvector는 PostgreSQL에 벡터 타입과 거리 연산을 추가하는 확장입니다.

```bash
docker run -d --name pgvector -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=<비밀번호> -e POSTGRES_DB=blog \
  -v pgdata:/var/lib/postgresql/data pgvector/pgvector:pg16
docker ps --filter name=pgvector   # STATUS가 Up이면 정상
```

로컬에서만 쓸 거라면 `127.0.0.1`을 붙여 외부 접속을 막는 것을 권장합니다. 여기서 정한 `<비밀번호>`는 2장 접속 문자열의 비밀번호와 같아야 합니다. 볼륨과 외부 접속 설정은 [[ Docker ] PostgreSQL Docker 볼륨 설정 및 외부 접속 구성하기](https://drg2524.tistory.com/228), 이 구성을 실제 에이전트에 적용한 사례는 [[Vibe Coding] 지역 블로그 AI 에이전트 구축기 (feat. Claude + pgvector)](https://drg2524.tistory.com/259)를 참고해 주세요.

### 2. bge-m3 임베딩과 청크 분할

임베딩은 텍스트를 의미 벡터로 바꾸는 작업입니다. 긴 글을 통째로 임베딩하면 검색이 부정확해지기 때문에 800자 청크로 잘라서 넣었습니다. 800자를 고른 이유는 [확인 필요: 800자를 고른 이유]입니다.

```bash
pip install langchain-postgres "psycopg[binary]" langchain-huggingface langchain-text-splitters sentence-transformers
# [확인 필요: 사용한 패키지 버전, 해당 버전에서 sentence-transformers가 필요한지]
```

아래 코드를 `index.py`로 저장해 `python index.py`로 실행합니다.

```python
import os
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

url = os.environ["PG_URL"]  # 예: postgresql+psycopg://admin:<비밀번호>@localhost:5432/blog
emb = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")  # 첫 실행 시 약 2GB 모델을 내려받아 시간이 걸립니다
store = PGVector(embeddings=emb, connection=url,
                 collection_name="blog_posts", embedding_length=1024)

posts = load_posts()  # [확인 필요: 글 불러오는 코드] title·url·content dict 목록
sp = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)  # [확인 필요: 실제 사용한 overlap 값]

for p in posts:
    # 재적재 전에 이 URL의 기존 청크를 지운다
    old = store.similarity_search("", k=1000, filter={"url": p["url"]})  # [확인 필요: 실제 사용한 삭제 방식]
    if old:
        store.delete(ids=[d.id for d in old])
    meta = {"title": p["title"], "url": p["url"]}
    docs = sp.create_documents([p["content"]], [meta])
    store.add_documents(docs, ids=[f"{p['url']}#{i}" for i in range(len(docs))])
```

접속 문자열은 `드라이버://계정:비번@호스트:포트/DB` 형식이고, 드라이버로는 psycopg(PostgreSQL용 파이썬 드라이버)를 씁니다. 비밀번호에 `@`나 `#`이 들어 있으면 URL 인코딩을 해야 합니다.¹

ids를 'URL#청크 번호'로만 지정하면 같은 청크는 덮어써집니다. 하지만 글이 짧아져 청크 수가 줄면 기존 `#5`, `#6` 같은 청크가 남아 검색에 계속 걸리기 때문에 먼저 지우고 다시 넣습니다. 삭제된 글은 따로 지워 줘야 합니다. 매번 전체를 다시 임베딩하면 비용이 크므로, 본문 해시를 메타데이터에 저장해 두고 바뀐 글만 처리하는 방법도 쓸 수 있습니다.

overlap은 문장이 청크 경계에서 잘려 의미가 끊기지 않도록 100자로 주었습니다.

`CREATE EXTENSION vector`는 PGVector가 기본으로 실행해 줍니다. 계정에 권한이 없다면 아래 명령을 직접 실행합니다.

```bash
docker exec -it pgvector psql -U admin -d blog -c "CREATE EXTENSION vector;"
```

#### PGVector가 만드는 테이블 (langchain_pg_collection, langchain_pg_embedding)

`blog_posts`라는 테이블은 생기지 않습니다. 대신 공용 테이블인 `langchain_pg_collection`(컬렉션)과 `langchain_pg_embedding`(벡터·본문·메타데이터)이 생기고, `blog_posts`는 컬렉션 이름으로만 쓰입니다.

벡터 인덱스는 자동으로 만들어지지 않아서 검색할 때 모든 행과 거리를 계산하는 전체 스캔으로 동작합니다. 데이터가 늘면 근사 검색용 벡터 인덱스인 HNSW를 만들면 됩니다. 이때 `embedding_length=1024`로 차원을 지정해 두어야 합니다. 차원이 없는 `vector` 컬럼에는 인덱스를 만들 수 없습니다. 인덱스는 거리 함수에 맞춰 `vector_cosine_ops`로 만듭니다.

```sql
CREATE INDEX ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops);
```

[확인 필요: 넣은 개수와 단위(글/청크)]를 넣는 데 [확인 필요: 소요 시간]이 걸렸습니다. GPU 없이 [확인 필요: CPU 사양], 배치 크기 [확인 필요] 환경에서 실행했습니다.

### 3. LangChain PGVector로 유사도 검색하기

별도 파일에서 실행한다면 `emb`와 `store`를 다시 만들어야 합니다. 결과는 청크 단위로 나오기 때문에 같은 글이 상위를 여러 번 차지할 수 있습니다. 그래서 k를 넉넉히 잡은 뒤 url 기준으로 중복을 제거합니다.

```python
import os
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings

emb = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
store = PGVector(embeddings=emb, connection=os.environ["PG_URL"],
                 collection_name="blog_posts", embedding_length=1024)

seen = set()
for doc, score in store.similarity_search_with_score("JPA N+1 문제", k=20):
    if doc.metadata["url"] in seen:
        continue
    seen.add(doc.metadata["url"])
    print(round(score, 4), doc.metadata["title"])
    if len(seen) == 4:
        break
```

```text
[확인 필요: 실제 출력, 값이 아래 설명과 맞는지]
```

#### similarity_search_with_score 점수 해석 (코사인 거리 vs 유사도)

기본 설정에서 이 점수는 코사인 거리(pgvector `<=>`)라서 낮을수록 비슷한 글입니다. 코사인 유사도는 1 - 거리로 계산하고, 높을수록 비슷합니다. [구축기 글](https://drg2524.tistory.com/259)도 계산 방식은 같습니다. 다만 그 글의 임계값 0.85는 다른 로컬 한국어 모델로 글 전체를 비교해서 나온 값입니다. 모델과 비교 단위가 다르면 유사도 분포도 달라지므로 이 수치를 그대로 가져다 쓰면 안 됩니다. 임계값은 bge-m3와 청크 단위 기준으로 다시 측정해야 합니다.

#### 한국어·영어 질의 결과 비교

| 질의 | 상위 결과 |
|---|---|
| JPA N+1 문제 | [확인 필요] |
| [확인 필요: 영어 질의] | [확인 필요] |

bge-m3는 다국어(크로스링구얼) 검색을 지원하기 때문에, 영어로 물어봐도 한글 글이 나왔습니다.

### 마무리

pgvector는 결국 PostgreSQL이라 벡터 DB를 따로 배우지 않아도 된다는 점이 좋았습니다. 다음에는 LangGraph(LLM 작업을 단계별 그래프로 엮는 프레임워크)를 붙여 보겠습니다.

---

¹ 이 글은 `langchain_postgres` 기준입니다. 구버전 `langchain_community`는 `connection` 대신 `connection_string` 인자를 씁니다.