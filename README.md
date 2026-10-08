# 블로그 글 리뷰어

새 블로그 글 초안을 넣으면, 내 기존 블로그 글을 RAG로 참고해서 세 명의 페르소나가 각자 관점으로 리뷰하고, 그 결과를 종합해 점수와 수정안을 내놓는 도구입니다.

- **초보 독자**: 이해 안 되는 용어, 건너뛴 설명, 따라 하다 막힐 지점
- **시니어 개발자**: 기술적 정확성, 빠진 예외 상황, 더 나은 구현 방식
- **SEO 전문가**: 제목, 소제목 구조, 키워드, 도입부의 검색 노출

평균 점수가 기준(기본 7점)에 못 미치면 수정안을 만들어 다시 리뷰하고, 이 과정을 최대 2회 반복합니다.

## 흐름

![리뷰 워크플로우](docs/graph.png)

| 노드 | 하는 일 |
|---|---|
| `retrieve` | 초안과 관련된 기존 글을 PGVector에서 찾습니다. |
| `review_beginner`, `review_senior`, `review_seo` | 세 페르소나가 기존 글을 근거로 동시에 리뷰합니다. 각자 점수(1~10), 좋은 점, 고칠 점을 냅니다. |
| `synthesize` | 평균 점수를 계산하고, 세 리뷰를 우선순위별 수정 사항으로 정리합니다. |
| `revise` | 평균이 기준 미만이면 수정안을 쓰고 리뷰 단계로 돌아갑니다. |

## 기술 스택

| 역할 | 사용한 것 |
|---|---|
| 워크플로우 | LangGraph, PostgresSaver 체크포인터 |
| 문서 분할·검색 | LangChain |
| 벡터 저장소 | PostgreSQL + pgvector (`langchain-postgres`의 PGVector) |
| LLM | Claude (`claude-opus-5-5`) |
| 임베딩 | `BAAI/bge-m3` (로컬 실행, 1024차원) |
| 화면 | Streamlit |

## 파일 구조

```
blog-reviewer/
├─ config.py          # .env 로딩, DB URL, LLM·임베딩·벡터 저장소 생성, 기준 점수 등 설정
├─ check_db.py        # DB 연결 확인
├─ ingest.py          # 블로그 글 수집 → 분할 → 임베딩 → PGVector 적재
├─ search_test.py     # 검색 테스트
├─ retriever.py       # 초안과 관련된 기존 글 검색 (글 단위로 묶기)
├─ reviewer.py        # Review 스키마, 페르소나 한 명의 리뷰
├─ editor.py          # 리뷰 종합, 수정안 생성
├─ graph.py           # LangGraph 워크플로우
├─ app.py             # Streamlit 화면
├─ prompts/
│  ├─ common.md       # 모든 리뷰어 공통: 리뷰 방식, 점수 기준
│  ├─ beginner.md     # 초보 독자
│  ├─ senior.md       # 시니어 개발자
│  ├─ seo.md          # SEO 전문가
│  ├─ synthesize.md   # 종합(편집장)
│  └─ revise.md       # 수정안 작성
├─ samples/           # 테스트용 초안과 그 수정안
└─ docs/graph.png     # 그래프 구조 이미지
```

파일은 만든 순서대로 읽으면 됩니다: `config` → `ingest` → `retriever` → `reviewer` → `editor` → `graph` → `app`.

## 준비

### 1. PostgreSQL + pgvector

pgvector가 설치된 PostgreSQL이 필요합니다. 이 프로젝트는 `pgvector/pgvector:pg16` 이미지를 씁니다.
DB에 스키마와 확장을 한 번 만들어 둡니다.

```sql
CREATE SCHEMA IF NOT EXISTS blog_reviewer;
CREATE EXTENSION IF NOT EXISTS vector;
```

모든 테이블은 `blog_reviewer` 스키마 안에 만들어집니다. 코드에는 스키마 이름을 적지 않고, 연결 문자열의 `search_path`로 지정합니다.

### 2. 패키지 설치

Python 3.12 기준입니다.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 환경 변수

`.env.example`을 `.env`로 복사하고 값을 채웁니다.

| 키 | 설명 |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://` 형식. 끝에 `?options=-csearch_path%3Dblog_reviewer,public`을 붙입니다. |
| `ANTHROPIC_API_KEY` | Claude API 키 |

### 4. 블로그 주소

`config.py`의 `BLOG_URL`을 자기 블로그 주소로 바꿉니다. 수집기는 티스토리 기준입니다(아래 "다른 블로그에 쓰려면" 참고).

## 실행

### 1. DB 연결 확인

```bash
python check_db.py
```

스키마, `vector` 확장, 테이블 생성 권한을 확인하고 `OK`를 출력합니다.

### 2. 블로그 글 적재

임베딩 모델(약 2GB)을 처음 받을 때만 오프라인 설정을 끄고 실행합니다.

```powershell
$env:HF_HUB_OFFLINE = "0"
python ingest.py
```

그다음부터는 그냥 실행하면 됩니다.

```bash
python ingest.py            # data/posts.json이 있으면 재사용
python ingest.py --refresh  # 블로그에서 다시 수집
```

- 수집 원본은 `data/posts.json`에 저장됩니다.
- 적재는 매번 컬렉션을 비우고 전체를 다시 넣습니다. 이어서 하기는 되지 않습니다.
- GPU가 없으면 오래 걸립니다. 글 258편(청크 3,037개)에 CPU로 약 50분 걸렸습니다.

### 3. 검색 테스트

```bash
python search_test.py
python search_test.py "JPA N+1 문제"
```

출력되는 숫자는 코사인 거리라서 낮을수록 가깝습니다.

### 4. 리뷰 실행

화면으로 실행합니다.

```bash
streamlit run app.py
```

터미널에서 실행할 수도 있습니다.

```bash
python reviewer.py                    # 세 페르소나 리뷰만 (종합·수정 없음)
python reviewer.py 내초안.md senior    # 파일과 페르소나 지정
python graph.py 내초안.md              # 전체 워크플로우. 수정안은 내초안.revised.md로 저장
python graph.py --image               # docs/graph.png 다시 만들기 (인터넷 필요)
```

리뷰 한 번에 1~2분, 수정이 2회 반복되면 7~8분 걸립니다.

## 화면 사용법

1. 초안을 마크다운으로 붙여 넣고 **리뷰 시작**을 누릅니다.
2. 진행 상황이 노드 단위로 표시됩니다.
3. 끝나면 원본 평균과 최종 평균, 수정 횟수가 나옵니다.
4. **라운드**에서 원본, 1차 수정, 2차 수정을 골라 그때의 리뷰, 종합 결과, 글을 봅니다.
5. 수정안은 미리보기로 확인하고 마크다운으로 내려받습니다.

리뷰가 끝나면 주소에 `?thread=<id>`가 붙습니다. 이 주소로 다시 들어오면 체크포인트에 저장된 결과를 그대로 불러옵니다.

수정안의 `[확인 필요: …]` 표시는 측정값이나 실행 환경처럼 글쓴이만 아는 내용을 채울 자리입니다. LLM이 지어내지 않도록 비워 둔 것입니다.

## 설정 바꾸기

`config.py`에서 바꿉니다.

| 설정 | 기본값 | 설명 |
|---|---|---|
| `LLM_MODEL` | `claude-opus-5-5` | `claude-sonnet-5-5`로 바꾸면 비용이 절반입니다. |
| `PASS_SCORE` | `7.0` | 평균이 이 값 미만이면 수정합니다. 화면 사이드바에서도 바꿀 수 있습니다. |
| `MAX_REVISIONS` | `2` | 수정 → 재리뷰 반복 횟수 상한 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 바꾸면 `EMBEDDING_DIM`도 맞추고 다시 적재해야 합니다. |

검색 범위는 `retriever.py`(거리 기준 `MAX_DISTANCE`, 근거로 쓸 글 수 `MAX_POSTS`), 청크 크기는 `ingest.py`(`CHUNK_SIZE`)에 있습니다.

리뷰어의 관점이나 점수 기준을 바꾸려면 `prompts/`의 마크다운 파일을 고칩니다. 코드를 건드릴 필요가 없습니다.

## 다른 블로그에 쓰려면

`ingest.py`의 수집 부분만 바꾸면 됩니다.

- `fetch_post_urls()`: `sitemap.xml`에서 글 URL을 고릅니다.
- `fetch_post()`: 제목(`og:title`), 작성일(`article:published_time`), 카테고리(`.category`), 본문(`.contents_style`)을 읽습니다. 카테고리와 본문의 선택자는 티스토리 스킨에 따라 다를 수 있습니다.

`collect()`가 `title`, `url`, `published_at`, `category`, `content`를 가진 글 목록을 돌려주기만 하면 나머지는 그대로 동작합니다.

## 알아둘 점

- **수정안은 길어집니다.** 리뷰어가 요구하는 설명을 받아 적다 보니 짧은 초안일수록 크게 불어납니다(샘플은 663자 → 12,000자 이상). 그대로 발행할 글이 아니라 고칠 방향을 보여주는 뼈대로 쓰는 것이 맞습니다.
- **점수는 실행마다 조금씩 다릅니다.** 같은 초안도 1점 안팎으로 흔들립니다.
- **비공개·보호 글은 수집되지 않습니다.**
- **`.env`와 `data/`는 커밋하지 않습니다.** `.gitignore`에 들어 있습니다.
