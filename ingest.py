"""블로그 글 수집 → 분할 → 임베딩 → PGVector 적재.

    python ingest.py            # data/posts.json이 있으면 재사용, 없으면 수집
    python ingest.py --refresh  # 블로그에서 다시 수집

적재는 매번 컬렉션을 비우고 전체를 다시 넣는다(멱등).
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

POSTS_FILE = Path("data/posts.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (blog-reviewer; personal ingest)"}
REQUEST_DELAY = 1.0  # 글 요청 사이 간격(초)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH_SIZE = 64


# ---------- 1. 수집 ----------

def fetch_post_urls() -> list[str]:
    """sitemap.xml에서 글 URL만 골라낸다. (카테고리·홈 등은 제외)"""
    response = requests.get(f"{config.BLOG_URL}/sitemap.xml", headers=HEADERS, timeout=20)
    response.raise_for_status()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text for loc in ET.fromstring(response.content).findall("s:url/s:loc", ns)]
    post_pattern = re.compile(re.escape(config.BLOG_URL) + r"/(\d+|entry/.+)$")
    return [url for url in urls if post_pattern.match(url)]


def html_to_text(body) -> str:
    """본문 HTML을 텍스트로 바꾼다. 소제목과 코드 블록은 마크다운 표기로 남긴다."""
    for tag in body.select("script, style, figcaption, .og-desc, .og-host"):
        tag.decompose()
    for level in (2, 3, 4):
        for heading in body.find_all(f"h{level}"):
            heading.string = f"\n{'#' * level} {heading.get_text(' ', strip=True)}\n"
    for pre in body.find_all("pre"):
        language = pre.get("data-ke-language") or ""
        pre.string = f"\n```{language}\n{pre.get_text().strip()}\n```\n"

    # 줄바꿈은 블록 태그에서만 넣는다. (굵은 글씨 같은 인라인 태그에서 문장이 끊기지 않게)
    for br in body.find_all("br"):
        br.replace_with("\n")
    for item in body.find_all("li"):
        item.insert(0, "- ")
    for cell in body.find_all(["td", "th"]):
        cell.append(" | ")
    for block in body.find_all(["p", "li", "tr", "blockquote", "div", "figure", "hr"]):
        if not block.find_parent(["td", "th"]):  # 표의 한 행은 한 줄로 유지
            block.append("\n")

    text = body.get_text()
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_post(url: str) -> dict | None:
    """글 한 편의 제목, 작성일, 카테고리, 본문을 가져온다. 본문이 없으면 None."""
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    body = soup.select_one(".contents_style")
    if body is None:  # 보호 글 등 본문이 없는 페이지
        return None

    def meta(prop: str) -> str:
        tag = soup.find("meta", property=prop)
        return tag["content"].strip() if tag else ""

    category = soup.select_one(".category")
    return {
        "url": url,
        "title": meta("og:title"),
        "published_at": meta("article:published_time"),
        "category": category.get_text(strip=True) if category else "",
        "content": html_to_text(body),
    }


def collect() -> list[dict]:
    """블로그 전체 글을 수집해 data/posts.json에 저장한다."""
    urls = fetch_post_urls()
    print(f"sitemap에서 글 {len(urls)}개 발견")

    posts, skipped = [], []
    for i, url in enumerate(urls, 1):
        post = fetch_post(url)
        if post and post["content"]:
            posts.append(post)
        else:
            skipped.append(url)
        if i % 25 == 0 or i == len(urls):
            print(f"  수집 {i}/{len(urls)}")
        time.sleep(REQUEST_DELAY)

    POSTS_FILE.parent.mkdir(exist_ok=True)
    POSTS_FILE.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {POSTS_FILE} ({len(posts)}개, 건너뜀 {len(skipped)}개)")
    for url in skipped:
        print(f"  건너뜀: {url}")
    return posts


# ---------- 2. 분할 ----------

def split(posts: list[dict]) -> list[Document]:
    """글을 청크로 나눈다. 각 청크 앞에 제목을 붙여 어느 글의 일부인지 알 수 있게 한다."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " ", ""],
    )
    documents = []
    for post in posts:
        metadata = {key: post[key] for key in ("title", "url", "published_at", "category")}
        for i, chunk in enumerate(splitter.split_text(post["content"])):
            documents.append(
                Document(
                    page_content=f"[{post['title']}]\n{chunk}",
                    metadata={**metadata, "chunk": i},
                )
            )
    return documents


# ---------- 3. 임베딩 + 적재 ----------

def load(documents: list[Document]) -> None:
    """컬렉션을 비우고 전체 청크를 임베딩해 적재한다."""
    store = config.get_vector_store()
    store.delete_collection()
    store.create_collection()

    started = time.time()
    for start in range(0, len(documents), BATCH_SIZE):
        store.add_documents(documents[start : start + BATCH_SIZE])
        done = min(start + BATCH_SIZE, len(documents))
        print(f"  적재 {done}/{len(documents)} ({time.time() - started:.0f}초)")


def main() -> None:
    refresh = "--refresh" in sys.argv
    if POSTS_FILE.exists() and not refresh:
        posts = json.loads(POSTS_FILE.read_text(encoding="utf-8"))
        print(f"{POSTS_FILE} 재사용 ({len(posts)}개)")
    else:
        posts = collect()

    documents = split(posts)
    print(f"분할: 글 {len(posts)}개 → 청크 {len(documents)}개")

    load(documents)
    print("완료")


if __name__ == "__main__":
    main()
