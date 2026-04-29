import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timedelta
import urllib.parse

st.set_page_config(page_title="단타 스캐너", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔥 단타 + 뉴스 + 섹터 스캐너")

selected_date = st.date_input("분석 날짜", datetime.today() - timedelta(days=1))


# =========================
# 섹터 추정 (간단 버전)
# =========================
def get_sector(name):
    if any(x in name for x in ["바이오", "제약", "헬스"]):
        return "바이오"
    if any(x in name for x in ["반도체", "전자", "칩"]):
        return "반도체"
    if any(x in name for x in ["철강", "포스코"]):
        return "철강"
    if any(x in name for x in ["자동차", "모터"]):
        return "자동차"
    if any(x in name for x in ["화학", "케미칼"]):
        return "화학"
    return "기타"


# =========================
# 뉴스 링크 생성
# =========================
def get_news_link(name):
    query = urllib.parse.quote(f"{name} 주가 상승")
    return f"https://search.naver.com/search.naver?where=news&query={query}"


# =========================
# 관심종목 저장
# =========================
def save_watchlist(row):
    item = {
        "code": str(row["종목코드"]),
        "name": str(row["종목명"]),
        "market": "KRX",
        "candle": str(row["캔들"]),
        "score": int(row["점수"]),
        "reason": str(row["이유"]),
        "sector": str(row["섹터"]),
    }
    supabase.table("watchlist").insert(item).execute()


def load_watchlist():
    data = supabase.table("watchlist").select("*").execute()
    return pd.DataFrame(data.data)


# =========================
# ETF 제거
# =========================
def is_excluded(name):
    keywords = ["ETF", "ETN", "KODEX", "TIGER", "KBSTAR", "ARIRANG",
                "레버리지", "인버스", "스팩", "리츠", "우"]

    return any(k in name.upper() for k in keywords)


# =========================
# 거래량 상위
# =========================
def get_top_volume():
    url = "https://finance.naver.com/sise/sise_quant.naver"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(res.text, "html.parser")

    stocks = []

    for row in soup.select("table.type_2 tr"):
        cols = row.find_all("td")

        if len(cols) > 1:
            try:
                name = cols[1].text.strip()
                code = cols[1].find("a")["href"].split("=")[-1]

                if not is_excluded(name):
                    stocks.append((code, name))
            except:
                continue

    return stocks[:200]


# =========================
# 분석
# =========================
def fast_scan(date):
    start = (date - timedelta(days=40)).strftime("%Y-%m-%d")
    end = date.strftime("%Y-%m-%d")

    stocks = get_top_volume()
    results = []

    for code, name in stocks:
        try:
            df = fdr.DataReader(code, start, end)

            if df is None or len(df) < 25:
                continue

            d = df.iloc[-1]

            open_p = d["Open"]
            high_p = d["High"]
            close_p = d["Close"]
            vol = d["Volume"]

            if open_p == 0 or high_p == 0:
                continue

            value = close_p * vol
            change = ((close_p - open_p) / open_p) * 100
            near_high = ((high_p - close_p) / high_p) * 100

            ma5 = df["Close"].rolling(5).mean().iloc[-1]
            ma20 = df["Close"].rolling(20).mean().iloc[-1]

            sector = get_sector(name)

            if value < 20000000000:
                continue
            if change < 5:
                continue
            if close_p <= open_p:
                continue
            if near_high > 5:
                continue

            score = round(change + (value / 10000000000), 1)

            results.append({
                "관심": False,
                "종목코드": code,
                "종목명": name,
                "섹터": sector,
                "차트": f"https://finance.naver.com/item/main.naver?code={code}",
                "뉴스": get_news_link(name),
                "등락률": round(change, 2),
                "거래대금(억)": round(value / 100000000, 1),
                "점수": score,
                "캔들": "양봉",
                "이유": "수급 + 기술적 조건"
            })

        except:
            continue

    df = pd.DataFrame(results)

    if not df.empty:
        df = df.sort_values(by="점수", ascending=False)

    return df


# =========================
# UI
# =========================
tab1, tab2 = st.tabs(["📊 분석", "⭐ 관심종목"])

with tab1:
    if "result" not in st.session_state:
        st.session_state.result = pd.DataFrame()

    if st.button("⚡ 분석 시작"):
        st.session_state.result = fast_scan(selected_date)

    result = st.session_state.result

    if result.empty:
        st.warning("분석 결과 없음")
    else:
        edited = st.data_editor(
            result.head(15),
            key="editor",
            column_config={
                "관심": st.column_config.CheckboxColumn("관심"),
                "차트": st.column_config.LinkColumn("차트"),
                "뉴스": st.column_config.LinkColumn("뉴스"),
            },
            use_container_width=True,
            hide_index=True
        )

        selected = edited[edited["관심"] == True]

        if st.button("저장"):
            for _, row in selected.iterrows():
                save_watchlist(row)
            st.success("저장 완료")

with tab2:
    watch = load_watchlist()

    if watch.empty:
        st.info("없음")
    else:
        watch["차트"] = watch["code"].apply(
            lambda x: f"https://finance.naver.com/item/main.naver?code={x}"
        )

        st.dataframe(
            watch[["name", "sector", "score", "reason", "차트"]],
            column_config={"차트": st.column_config.LinkColumn("차트")},
            use_container_width=True
        )
