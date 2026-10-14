"""블로그 글 리뷰어 (Streamlit).

    streamlit run app.py

로그인하지 않았으면 로그인 페이지만, 로그인하면 리뷰 페이지를 보여준다.
"""

import streamlit as st

import auth

st.set_page_config(page_title="블로그 글 리뷰어", page_icon=":material/rate_review:", layout="wide")

login_page = st.Page("app_pages/login.py", title="로그인", icon=":material/login:")
review_page = st.Page("app_pages/review.py", title="리뷰", icon=":material/rate_review:")

if auth.is_logged_in():
    page = st.navigation([review_page], position="hidden")
    with st.sidebar:
        if st.button("로그아웃", icon=":material/logout:"):
            auth.log_out()
            st.rerun()
else:
    page = st.navigation([login_page], position="hidden")

page.run()
