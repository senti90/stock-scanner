import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from supabase import create_client
from datetime import datetime, timedelta

st.set_page_config(page_title="단타 스캐너", layout="wide")

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("⚡ 장마감 스캐너")

selected_date = st.date_input("분석 날짜", datetime.today() - timedelta(days=1))


# 관심종목 불러오기
def load_watchlist():
    data = supabase.table("watchlist").select("*").execute()
    return pd.DataFrame(data.data)


# 관심종목 저장
def save_watchlist(row):
    item = {
        "code": str(row["종목코드"]),
        "name": str(row["종목명"]),
        "market": "KRX",
        "candle": str(row["캔들"]),
        "score": int(row["점수"]),
        "reason": str(row["이유"]),
    }
    supabase.table("watchlist").insert(item).execute()


# 핵심: 초고속 분석
def fast_scan(date):
    date_str = date.strftime("%Y-%m-%d")

    # 전체 시장 한 번에 가져오기
    df = fdr.DataReader("KRX", date_str)

    if df is None or df.empty:
        return pd.DataFrame()

    # 거래대금 계산
    df["거래대금"] = df["Close"] * df["Volume"]

    # 1차 필터 (속도 핵심)
    df = df[
        (df["Volume"] >= 500000) &
        (df["거래대금"] >= 10000000000) &
        (df["Close"] >= 1000)
    ]

    results = []

    for _, row in df.iterrows():
        try:
            open_price = row["Open"]
            high_price = row["High"]
            low_price = row["Low"]
            close_price = row["Close"]

            if open_price == 0 or high_price == 0:
                continue

            change_rate = ((close_price - open_price) / open_price) * 100
            close_near_high = ((high_price - close_price) / high_price) * 100

            # 캔들
            candle = "양봉" if close_price > open_price else "음봉"

            score = 0

            if change_rate >= 7:
                score += 20
            if change_rate >= 15:
                score += 20

            if row["거래대금"] >= 30000000000:
                score += 20

            if close_near_high <= 5:
                score += 20

            if candle == "양봉":
                score += 10
            else:
                score -= 10

            if score >= 30:
                results.append({
                    "관심": False,
                    "종목코드": row["Code"],
                    "종목명": row["Name"],
                    "차트": f"https://finance.naver.com/item/main.naver?code={row['Code']}",
                    "캔들": candle,
                    "등락률": round(change_rate, 2),
                    "거래대금(억)": round(row["거래대금"] / 100000000, 1),
                    "점수": score,
                    "이유": "단타 조건 충족"
                })

        except:
            continue

    return pd.DataFrame(results)


tab1, tab2 = st.tabs(["📊 분석", "⭐ 관심종목"])

with tab1:
    if st.button("⚡ 빠르게 분석"):
        with st.spinner("분석 중... (5초 내 완료)"):
            result = fast_scan(selected_date)

        if result.empty:
            st.warning("종목 없음")
        else:
            result = result.sort_values(by="점수", ascending=False)

            edited = st.data_editor(
                result,
                column_config={
                    "관심": st.column_config.CheckboxColumn("관심"),
                    "차트": st.column_config.LinkColumn("차트", display_text="보기"),
                },
                hide_index=True
            )

            selected = edited[edited["관심"] == True]

            if st.button("선택 저장"):
                for _, row in selected.iterrows():
                    save_watchlist(row)
                st.success("저장 완료")

with tab2:
    st.subheader("저장된 관심종목")

    watch = load_watchlist()

    if watch.empty:
        st.info("없음")
    else:
        watch["차트"] = watch["code"].apply(
            lambda x: f"https://finance.naver.com/item/main.naver?code={x}"
        )

        st.dataframe(
            watch[["name", "score", "reason", "차트"]],
            column_config={"차트": st.column_config.LinkColumn("차트", display_text="보기")}
        )
