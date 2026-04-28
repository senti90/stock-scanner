import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timedelta

st.set_page_config(page_title="단타 스캐너", layout="wide")

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔥 장마감 스캐너")
st.write("다음날 단타 가능성 있는 종목 자동 필터링 되어 보여집니다.")
st.write("분석할 날짜를 선택하세요.")

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


# 네이버 거래량 상위 가져오기
def get_top_volume():
    url = "https://finance.naver.com/sise/sise_quant.naver"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")

    stocks = []

    for row in soup.select("table.type_2 tr"):
        cols = row.find_all("td")

        if len(cols) > 1:
            try:
                name = cols[1].text.strip()
                link = cols[1].find("a")["href"]
                code = link.split("=")[-1]
                stocks.append((code, name))
            except:
                continue

    return stocks[:200]


# 핵심 분석
def fast_scan(date):
    date_str = date.strftime("%Y-%m-%d")
    stocks = get_top_volume()

    results = []

    for code, name in stocks:
        try:
            df = fdr.DataReader(code, date_str, date_str)

            if df.empty:
                continue

            d = df.iloc[-1]

            open_price = d["Open"]
            high_price = d["High"]
            close_price = d["Close"]
            volume = d["Volume"]

            if open_price == 0 or high_price == 0:
                continue

            trading_value = close_price * volume

            change_rate = ((close_price - open_price) / open_price) * 100
            close_near_high = ((high_price - close_price) / high_price) * 100
            upper_tail = ((high_price - close_price) / close_price) * 100

            # 🔥 핵심 필터
            if change_rate < 8:
                continue

            if close_price <= open_price:
                continue

            if close_near_high > 3:
                continue

            if trading_value < 20000000000:
                continue

            if upper_tail > 5:
                continue

            # 점수
            score = round(change_rate + (trading_value / 10000000000), 1)

            results.append({
                "관심": False,
                "종목코드": code,
                "종목명": name,
                "차트": f"https://finance.naver.com/item/main.naver?code={code}",
                "등락률(%)": round(change_rate, 2),
                "거래대금(억)": round(trading_value / 100000000, 1),
                "점수": score,
                "이유": "단타 핵심 조건 통과"
            })

        except:
            continue

    df_result = pd.DataFrame(results)

    if not df_result.empty:
        df_result = df_result.sort_values(by="점수", ascending=False)

    return df_result


# UI
tab1, tab2 = st.tabs(["📊 분석", "⭐ 관심종목"])

with tab1:
    if st.button("⚡ 분석 시작"):
        with st.spinner("초고속 분석 중..."):
            result = fast_scan(selected_date)

        if result.empty:
            st.warning("조건 만족 종목 없음")
        else:
            result = result.head(10)

            edited = st.data_editor(
                result,
                column_config={
                    "관심": st.column_config.CheckboxColumn("관심"),
                    "차트": st.column_config.LinkColumn("차트", display_text="차트보기"),
                },
                hide_index=True
            )

            selected = edited[edited["관심"] == True]

            if st.button("관심종목 저장"):
                for _, row in selected.iterrows():
                    save_watchlist(row)
                st.success("저장 완료")

with tab2:
    watch = load_watchlist()

    if watch.empty:
        st.info("관심종목 없음")
    else:
        watch["차트"] = watch["code"].apply(
            lambda x: f"https://finance.naver.com/item/main.naver?code={x}"
        )

        st.dataframe(
            watch[["name", "score", "reason", "차트"]],
            column_config={
                "차트": st.column_config.LinkColumn("차트", display_text="보기")
            }
        )
