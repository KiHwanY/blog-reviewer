"""로그인 페이지: 앱을 열면 가장 먼저 보이는 대표 화면.

모션은 CSS 애니메이션으로 넣는다.
- 배경: 은은한 그라데이션이 천천히 흐른다
- 카드: 아래에서 떠오르며 나타나고, 안의 요소가 차례로 따라 나온다
- 로고: 살짝 위아래로 떠 있다
- 입력칸: 포커스하면 테두리가 빛난다
- 버튼: 올리면 떠오르고, 빛이 한 번 지나간다
- 로그인 실패: 카드가 좌우로 흔들리고 오류 문구가 나타난다
움직임 줄이기를 켠 사용자에게는 애니메이션을 끈다.
"""

import base64

import streamlit as st

import auth

# 펜 아이콘. st.html은 <svg> 태그를 걸러내므로 CSS 배경 이미지로 넣는다
PEN_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" '
    'fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>'
)
PEN_ICON_URI = "data:image/svg+xml;base64," + base64.b64encode(PEN_ICON.encode()).decode()

LOGIN_CSS = """
<style>
/* 배경: 두 개의 빛 덩어리가 천천히 움직인다 */
.stApp {
  background:
    radial-gradient(circle at 20% 20%, rgba(255, 75, 75, 0.18), transparent 45%),
    radial-gradient(circle at 80% 80%, rgba(99, 102, 241, 0.18), transparent 45%);
  background-size: 160% 160%;
  animation: bg-drift 16s ease-in-out infinite alternate;
}
[data-testid="stHeader"] { background: transparent; }
/* 로그아웃하고 돌아왔을 때 빈 사이드바가 남지 않게 한다 */
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }

/* 카드: 아래에서 떠오르며 나타난다 */
[class*="st-key-login_card"] {
  margin-top: 12vh;
  padding: 2.25rem 2rem 1.75rem;
  border-radius: 20px;
  background: color-mix(in srgb, var(--st-background-color, #ffffff) 82%, transparent);
  backdrop-filter: blur(12px);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.14);
  animation: card-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}

/* 카드 안의 요소가 차례로 따라 나온다 */
[class*="st-key-login_card"] > div > [data-testid="stElementContainer"],
[class*="st-key-login_card"] > div > [data-testid="stForm"],
[class*="st-key-login_card"] > [data-testid="stElementContainer"],
[class*="st-key-login_card"] > [data-testid="stForm"] {
  animation: rise-in 0.6s cubic-bezier(0.22, 1, 0.36, 1) both;
}
[class*="st-key-login_card"] > :nth-child(1) { animation-delay: 0.15s; }
[class*="st-key-login_card"] > :nth-child(2) { animation-delay: 0.25s; }
[class*="st-key-login_card"] > :nth-child(3) { animation-delay: 0.35s; }
[class*="st-key-login_card"] > :nth-child(4) { animation-delay: 0.45s; }

/* 로고: 살짝 떠 있다 */
.login-logo {
  width: 64px; height: 64px; margin: 0 auto 0.75rem;
  display: grid; place-items: center;
  border-radius: 18px;
  background: url("__PEN_ICON__") center / 30px no-repeat, linear-gradient(135deg, #ff4b4b, #6366f1);
  box-shadow: 0 10px 24px rgba(255, 75, 75, 0.35);
  animation: float 3.2s ease-in-out infinite;
}
.login-title { text-align: center; font-size: 1.6rem; font-weight: 700; margin: 0; }
.login-subtitle { text-align: center; opacity: 0.7; margin: 0.35rem 0 0.5rem; font-size: 0.95rem; }

/* 입력칸: 포커스하면 빛난다 */
[class*="st-key-login_card"] [data-baseweb="input"] {
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}
[class*="st-key-login_card"] [data-baseweb="input"]:focus-within {
  box-shadow: 0 0 0 4px rgba(255, 75, 75, 0.18);
  transform: translateY(-1px);
}

/* 버튼: 올리면 떠오르고 빛이 지나간다 */
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button {
  position: relative; overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 22px rgba(255, 75, 75, 0.35);
}
[class*="st-key-login_card"] [data-testid="stFormSubmitButton"] button::after {
  content: ""; position: absolute; top: 0; left: -120%;
  width: 60%; height: 100%;
  background: linear-gradient(120deg, transparent, rgba(255, 255, 255, 0.45), transparent);
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

@keyframes bg-drift { from { background-position: 0% 0%; } to { background-position: 100% 100%; } }
@keyframes card-in {
  from { opacity: 0; transform: translateY(28px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}
@keyframes rise-in {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: none; }
}
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
@keyframes shine { to { left: 140%; } }
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-10px); }
  40% { transform: translateX(9px); }
  60% { transform: translateX(-6px); }
  80% { transform: translateX(4px); }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
"""

LOGO_HTML = """
<div class="login-logo" aria-hidden="true"></div>
<p class="login-title">블로그 글 리뷰어</p>
<p class="login-subtitle">내 블로그를 아는 세 명의 리뷰어가 초안을 읽어 드립니다</p>
"""

st.html(LOGIN_CSS.replace("__PEN_ICON__", PEN_ICON_URI))

if "failed_attempts" not in st.session_state:
    st.session_state.failed_attempts = 0
failed = st.session_state.failed_attempts

# 실패할 때마다 카드의 key를 바꿔, 흔들림 애니메이션이 매번 다시 재생되게 한다
card_key = f"login_card_shake_{failed}" if failed else "login_card"

with st.container(horizontal=True, horizontal_alignment="center"):
    with st.container(key=card_key, width=420):
        st.html(LOGO_HTML)

        with st.form("login_form", border=False):
            username = st.text_input("아이디", placeholder="아이디", autocomplete="username")
            password = st.text_input(
                "비밀번호", type="password", placeholder="비밀번호", autocomplete="current-password"
            )
            submitted = st.form_submit_button(
                "로그인", type="primary", icon=":material/login:", width="stretch"
            )

        if failed:
            with st.container(key=f"login_error_{failed}"):
                st.error("아이디 또는 비밀번호가 맞지 않습니다.", icon=":material/error:")

if submitted:
    if auth.check_credentials(username, password):
        auth.log_in()
        st.session_state.failed_attempts = 0
    else:
        st.session_state.failed_attempts += 1
    st.rerun()
