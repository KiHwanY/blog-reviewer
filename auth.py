""".env에 둔 계정 하나로 앱을 잠근다.

내 PC에서 혼자 쓰는 도구를 위한 간단한 잠금이다. 사용자 구분이 없고,
로그인 상태는 브라우저 세션에만 남아서 새로고침하면 다시 로그인해야 한다.

로그인 화면이 바로 뜨도록, 이 파일은 LLM·임베딩 라이브러리를 불러오는
config.py를 import하지 않고 .env만 직접 읽는다.
"""

import hmac
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def check_credentials(username: str, password: str) -> bool:
    """아이디와 비밀번호가 .env의 APP_USERNAME, APP_PASSWORD와 같은지 확인한다."""
    expected_username = os.environ.get("APP_USERNAME")
    expected_password = os.environ.get("APP_PASSWORD")
    if not expected_username or not expected_password:
        raise RuntimeError(".env에 APP_USERNAME과 APP_PASSWORD를 설정해 주세요.")
    # 비교 시간으로 값을 추측하지 못하게 compare_digest를 쓴다
    username_ok = hmac.compare_digest(username.encode(), expected_username.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return username_ok and password_ok


def is_logged_in() -> bool:
    return st.session_state.get("logged_in", False)


def log_in() -> None:
    st.session_state.logged_in = True
    st.session_state.just_logged_in = True  # 리뷰 페이지에서 환영 모션을 한 번만 보여준다


def log_out() -> None:
    st.session_state.clear()
