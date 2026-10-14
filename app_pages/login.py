"""로그인 페이지: 앱을 열면 가장 먼저 보이는 대표 화면.

따뜻한 미색 바탕에 짙은 초록을 포인트 색으로 쓰는 "편집실" 콘셉트다.
모션은 CSS 애니메이션으로 넣는다.
- 배경: 은은한 초록·베이지 빛이 천천히 흐른다
- 소개 문구와 카드: 아래에서 떠오르며 차례로 나타난다
- 로고: 살짝 위아래로 떠 있다
- 입력칸: 포커스하면 테두리가 빛난다
- 버튼: 올리면 떠오르고, 빛이 한 번 지나간다
- 로그인 실패: 카드가 좌우로 흔들리고 오류 문구가 나타난다
- 아래 화살표: 통통 튀며 서비스 소개로 내려가라고 알려 준다
움직임 줄이기를 켠 사용자에게는 애니메이션을 끈다.
"""

import base64
import importlib
import threading
import time

import streamlit as st

import auth

GREEN = "#1E4D3A"
WARM_UP_DELAY = 1.5  # 초. 리뷰 페이지 모듈을 미리 불러오기 전에 기다리는 시간
MUTED = "#6B6F6A"


def icon_uri(paths: str, color: str = GREEN) -> str:
    """선 아이콘을 CSS 배경으로 쓸 data URI로 만든다. (st.html은 <svg> 태그를 걸러낸다)"""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{paths}</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


ICONS = {
    "BOOK": icon_uri(
        '<path d="M12 7v13"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 '
        '4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>'
    ),
    "DATABASE": icon_uri(
        '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/>'
        '<path d="M3 12a9 3 0 0 0 18 0"/>',
        MUTED,
    ),
    "SHIELD": icon_uri(
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 '
        '1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
        '<path d="m9 12 2 2 4-4"/>',
        MUTED,
    ),
    "ARROW": icon_uri('<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>', "#1F2421"),
}

LOGIN_CSS = """
<style>
/* 명조체(Noto Serif KR)는 테마 설정(.streamlit/config.toml)이 불러온다.
   여기서 @import로 또 불러오면 글꼴을 내려받는 동안 화면 전체가 3초쯤 늦게 그려진다. */

/* 바탕: 미색 위로 초록·베이지 빛이 천천히 흐른다 */
.stApp {
  background-color: #EFEDE8;
  background-image:
    radial-gradient(circle at 15% 10%, rgba(30, 77, 58, 0.07), transparent 40%),
    radial-gradient(circle at 85% 90%, rgba(196, 170, 120, 0.12), transparent 45%);
  background-size: 160% 160%;
  animation: bg-drift 18s ease-in-out infinite alternate;
  color: #1F2421;
}
[data-testid="stHeader"] { background: transparent; }
/* 로그아웃하고 돌아왔을 때 빈 사이드바가 남지 않게 한다 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }

/* 가운데 큰 판: 미색 종이 느낌 */
.stMainBlockContainer {
  max-width: 840px;
  margin: 24px auto;
  padding: 1.75rem 2rem 2.5rem;
  background: #FBFAF6;
  border: 1px solid #E3E0D8;
  border-radius: 18px;
}

/* 상단 바 */
.brand-bar { display: flex; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; color: #1F2421; }
.brand-logo {
  width: 30px; height: 30px; border-radius: 50%;
  display: grid; place-items: center;
  background: __GREEN__; color: #FBFAF6;
  font-family: 'Noto Serif KR', 'Nanum Myeongjo', Batang, serif; font-weight: 700; font-size: 16px;
  animation: float 3.2s ease-in-out infinite;
}
.brand-link { color: #4A4F4A; font-size: 0.9rem; text-decoration: none; }
.brand-link:hover { color: __GREEN__; }

/* 소개 문구 */
.hero { text-align: center; margin: 2.5rem 0 1.5rem; }
.hero > * { animation: rise-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both; }
.eyebrow {
  display: inline-flex; align-items: center; gap: 8px;
  color: __GREEN__; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.14em;
}
.eyebrow::before {
  content: ""; width: 16px; height: 16px;
  background: url("__BOOK__") center / contain no-repeat;
}
.hero h1 {
  font-family: 'Noto Serif KR', 'Nanum Myeongjo', Batang, serif; font-weight: 500;
  font-size: 2.6rem; line-height: 1.25; color: #1F2421;
  margin: 1rem 0 0.9rem; padding: 0; animation-delay: 0.08s;
}
.hero p { color: __MUTED__; font-size: 0.98rem; line-height: 1.7; margin: 0; animation-delay: 0.16s; }

/* 카드: 아래에서 떠오르며 나타난다 */
[class*="st-key-login_card"] {
  padding: 1.75rem 1.5rem 1.25rem;
  border-radius: 14px;
  background: #FFFFFF;
  border: 1px solid #E3E0D8;
  box-shadow: 0 18px 40px rgba(31, 36, 33, 0.08);
  animation: card-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) 0.1s both;
}
[class*="st-key-login_card"] label p { color: #1F2421; font-weight: 700; font-size: 0.9rem; }

/* 입력칸: 흰 바탕, 포커스하면 초록으로 빛난다 */
[class*="st-key-login_card"] [data-testid="stTextInputRootElement"] {
  background: #FFFFFF; border: 1px solid #DAD7CF; border-radius: 8px; min-height: 44px;
  transition: box-shadow 0.25s ease, border-color 0.25s ease, transform 0.25s ease;
}
[class*="st-key-login_card"] [data-testid="stTextInputField"] { color: #1F2421; }
/* Streamlit 기본 포커스 스타일이 우선 적용되므로 !important로 덮는다 */
[class*="st-key-login_card"] [data-testid="stTextInputRootElement"]:focus-within {
  border-color: __GREEN__ !important;
  box-shadow: 0 0 0 4px rgba(30, 77, 58, 0.14) !important;
  transform: translateY(-1px);
}

/* 버튼: 짙은 초록. 올리면 떠오르고 빛이 지나간다 */
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button {
  position: relative; overflow: hidden;
  min-height: 46px; border-radius: 8px;
  background: __GREEN__; border-color: __GREEN__; color: #FFFFFF; font-weight: 700;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button:hover {
  background: #173D2E; border-color: #173D2E; color: #FFFFFF;
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(30, 77, 58, 0.3);
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button::after {
  content: ""; position: absolute; top: 0; left: -120%;
  width: 60%; height: 100%;
  background: linear-gradient(120deg, transparent, rgba(255, 255, 255, 0.35), transparent);
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button:hover::after {
  animation: shine 0.8s ease;
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button:active {
  transform: translateY(0) scale(0.98);
}

/* 로그인 실패: 카드가 흔들리고 오류 문구가 나타난다 */
[class*="st-key-login_card_shake"] {
  animation: card-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both, shake 0.45s ease 0.05s;
}
[class*="st-key-login_error"] { animation: rise-in 0.35s ease both; }

/* 하단: 구분선, 특징 두 개, 아래 화살표 */
.page-foot {
  margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid #E3E0D8;
  text-align: center; animation: rise-in 0.7s ease 0.4s both;
}
.badges { display: flex; justify-content: center; gap: 22px; color: __MUTED__; font-size: 0.85rem; }
.badge { display: inline-flex; align-items: center; gap: 7px; }
.badge::before { content: ""; width: 16px; height: 16px; background: center / contain no-repeat; }
.badge.db::before { background-image: url("__DATABASE__"); }
.badge.shield::before { background-image: url("__SHIELD__"); }
.scroll-down {
  display: inline-grid; place-items: center; margin-top: 0.9rem;
  width: 34px; height: 34px; border-radius: 50%;
  background: #FFFFFF url("__ARROW__") center / 16px no-repeat;
  border: 1px solid #E3E0D8;
  animation: bounce 2s ease-in-out infinite;
}

/* 서비스 소개 */
.service { margin-top: 3.5rem; scroll-margin-top: 2rem; }
.service h2 {
  font-family: 'Noto Serif KR', 'Nanum Myeongjo', Batang, serif; font-weight: 500; text-align: center;
  font-size: 1.7rem; color: #1F2421; margin-bottom: 1.5rem;
}
.features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }
.feature {
  background: #FFFFFF; border: 1px solid #E3E0D8; border-radius: 12px; padding: 1.1rem 1.2rem;
}
.feature b { display: block; color: __GREEN__; margin-bottom: 0.4rem; }
.feature span { color: __MUTED__; font-size: 0.9rem; line-height: 1.6; }

@keyframes bg-drift { from { background-position: 0% 0%; } to { background-position: 100% 100%; } }
@keyframes card-in {
  from { opacity: 0; transform: translateY(28px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}
@keyframes rise-in {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: none; }
}
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }
@keyframes shine { to { left: 140%; } }
@keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(5px); } }
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-10px); }
  40% { transform: translateX(9px); }
  60% { transform: translateX(-6px); }
  80% { transform: translateX(4px); }
}

@media (max-width: 640px) {
  .stMainBlockContainer { margin: 0; border-radius: 0; padding: 1.25rem 1rem 2rem; }
  .hero h1 { font-size: 2rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""

HEADER_HTML = """
<div class="brand-bar">
  <div class="brand"><span class="brand-logo">H</span>Hwan_velop</div>
  <a class="brand-link" href="#service">서비스 소개</a>
</div>
<div class="hero">
  <div class="eyebrow">PRIVATE EDITORIAL WORKSPACE</div>
  <h1>신뢰할 수 있는<br>글의 편집실</h1>
  <p>승인된 에디터만 지식 베이스를 활용해 검토와 수정을<br>이어갈 수 있습니다.</p>
</div>
"""

FOOTER_HTML = """
<div class="page-foot">
  <div class="badges">
    <span class="badge db">Private retrieval index</span>
    <span class="badge shield">Access controlled</span>
  </div>
  <a class="scroll-down" href="#service" aria-label="서비스 소개로 이동"></a>
</div>
<section class="service" id="service">
  <h2>서비스 소개</h2>
  <div class="features">
    <div class="feature"><b>내 블로그를 아는 리뷰</b>
      <span>기존 글 258편을 근거로 삼아, 이어지는 글을 링크하고 말투 차이를 짚어 줍니다.</span></div>
    <div class="feature"><b>세 가지 관점</b>
      <span>초보 독자, 시니어 개발자, SEO 전문가가 각자 다른 곳을 봅니다.</span></div>
    <div class="feature"><b>수정안까지</b>
      <span>우선순위별 수정 사항을 정리하고, 기준 점수에 못 미치면 수정안을 써서 다시 리뷰합니다.</span></div>
  </div>
</section>
"""


@st.cache_resource(show_spinner=False)
def warm_up_review_page() -> None:
    """로그인 화면을 띄운 뒤, 리뷰 페이지가 쓰는 무거운 라이브러리를 미리 불러 둔다.

    서버 프로세스당 한 번만 실행된다. 사용자가 아이디를 입력하는 동안 뒤에서 불러 두면
    로그인 직후 리뷰 페이지가 바로 열린다.
    """
    # 바로 시작하면 무거운 import가 CPU를 잡아 첫 화면 전송이 몇 초 늦어진다.
    # 화면이 다 그려질 시간을 준 뒤에 시작한다.
    def load_later() -> None:
        time.sleep(WARM_UP_DELAY)
        importlib.import_module("graph")

    threading.Thread(target=load_later, daemon=True).start()


def page_css() -> str:
    css = LOGIN_CSS.replace("__GREEN__", GREEN).replace("__MUTED__", MUTED)
    for name, uri in ICONS.items():
        css = css.replace(f"__{name}__", uri)
    return css


st.html(page_css())
st.html(HEADER_HTML)

if "failed_attempts" not in st.session_state:
    st.session_state.failed_attempts = 0
failed = st.session_state.failed_attempts

# 실패할 때마다 카드의 key를 바꿔, 흔들림 애니메이션이 매번 다시 재생되게 한다
card_key = f"login_card_shake_{failed}" if failed else "login_card"

with st.container(horizontal=True, horizontal_alignment="center"):
    with st.container(key=card_key, width=420):
        with st.form("login_form", border=False):
            username = st.text_input("ID", placeholder="아이디 입력", autocomplete="username")
            password = st.text_input(
                "비밀번호", type="password", placeholder="비밀번호 입력", autocomplete="current-password"
            )
            submitted = st.form_submit_button("편집실 들어가기", type="primary", width="stretch")

        if failed:
            with st.container(key=f"login_error_{failed}"):
                st.error("아이디 또는 비밀번호가 맞지 않습니다.", icon=":material/error:")

st.html(FOOTER_HTML)

if submitted:
    if auth.check_credentials(username, password):
        auth.log_in()
        st.session_state.failed_attempts = 0
    else:
        st.session_state.failed_attempts += 1
    st.rerun()

warm_up_review_page()
