# pgvector 써본 후기

요즘 RAG가 유행이라 나도 한번 해봤다. 내 블로그 글을 벡터 DB에 넣고 검색하는 걸 만들었는데 생각보다 쉬웠다.

## 설치

Docker로 pgvector 이미지를 띄우면 끝이다.

```bash
docker run -d -p 5432:5432 pgvector/pgvector:pg16
```

그다음 LangChain의 PGVector를 쓰면 테이블도 알아서 만들어준다.

## 임베딩

임베딩은 bge-m3를 썼다. 무료고 한국어도 잘 된다. 청크는 800자로 잘랐다.

```python
store = PGVector(embeddings=emb, connection=url, collection_name="blog_posts")
store.add_documents(docs)
```

3000개 넣는데 좀 오래 걸렸는데 GPU가 없어서 그런 것 같다.

## 검색

```python
store.similarity_search("JPA N+1 문제", k=4)
```

이렇게 하면 관련 글이 나온다. 코사인 유사도라 점수가 높을수록 비슷한 글이다. 영어로 물어봐도 한글 글이 나와서 신기했다.

## 마무리

pgvector는 그냥 Postgres라서 따로 벡터 DB를 안 배워도 돼서 좋다. 다음엔 LangGraph를 붙여볼 예정이다.
