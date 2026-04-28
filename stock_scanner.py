import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from supabase import create_client
from datetime import datetime, timedelta

st.set_page_config(page_title="장마감 단타 스캐너", layout="wide")

# Supabase 연결
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📈 장마감 스캐너")
st.write("장마감 후 데이터를 기준으로 내일 단타 관심종목을 빠르게 분류합니다.")

selected_date = st.date_input("분석 날짜 선택", datetime.today() - timedelta(days=1))


@st.cache_data
def get_stock_list():
    kospi = fdr.StockListing("KOSPI")
    kosdaq = fdr.StockListing("KOSDAQ")
    stocks = pd.concat([kospi, kosdaq], ignore_index=True)
    return stocks[["Code", "Name", "Market"]]


@st.cache_data
def load_stock_data(code, start_date, end_date):
    return fdr.DataReader(code, start_date, end_date)


def load_watchlist():
    try:
        data = supabase.table("watchlist").select("*").order("created_at", desc=True).execute()
        return pd.DataFrame(data.data)
    except Exception as e:
        st.error("관심종목 불러오기 실패")
        st.write(e)
        return pd.DataFrame()


def save_watchlist(row):
    try:
        item = {
            "code": str(row["종목코드"]),
            "name": str(row["종목명"]),
            "market": str(row["시장"]),
            "candle": str(row["캔들"]),
            "score": int(row["점수"]),
            "reason": str(row["분류이유"]),
        }
        supabase.table("watchlist").insert(item).execute()
        return True
    except Exception as e:
        st.error("저장 실패")
        st.write(e)
        return False


def delete_watchlist(item_id):
    try:
        supabase.table("watchlist").delete().eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error("삭제 실패")
        st.write(e)
        return False


def analyze_market(selected_date):
    stocks = get_stock_list()
    results = []

    start_date = (selected_date - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = (selected_date + timedelta(days=1)).strftime("%Y-%m-%d")

    progress = st.progress(0)
    status = st.empty()

    total = len(stocks)

    for i, row in stocks.iterrows():
        code = row["Code"]
        name = row["Name"]
        market = row["Market"]

        try:
            if "스팩" in name or "SPAC" in name or name.endswith("우"):
                continue

            df = load_stock_data(code, start_date, end_date)
            if df is None or df.empty:
                continue

            df = df[df.index <= pd.to_datetime(selected_date)]
            if len(df) < 2:
                continue

            today = df.iloc[-1]
            yesterday = df.iloc[-2]

            open_price = today["Open"]
            high_price = today["High"]
            low_price = today["Low"]
            close_price = today["Close"]
            volume = today["Volume"]
            prev_close = yesterday["Close"]

            if open_price == 0 or high_price == 0 or low_price == 0 or close_price == 0 or prev_close == 0:
                continue

            trading_value = close_price * volume

            if volume < 500000:
                continue
            if trading_value < 10000000000:
                continue
            if close_price < 1000:
                continue

            change_rate = ((close_price - prev_close) / prev_close) * 100
            candle_rate = ((close_price - open_price) / open_price) * 100
            upper_tail_rate = ((high_price - close_price) / close_price) * 100
            close_near_high = ((high_price - close_price) / high_price) * 100
            lower_tail_rate = ((min(open_price, close_price) - low_price) / low_price) * 100

            if close_price > open_price:
                candle_type = "양봉"
            elif close_price < open_price:
                candle_type = "음봉"
            else:
                candle_type = "보합"

            score = 0
            reasons = []

            if change_rate >= 7:
                score += 20
                reasons.append("7% 이상 상승")
            if change_rate >= 15:
                score += 20
                reasons.append("15% 이상 급등")
            if change_rate >= 25:
                score += 20
                reasons.append("상한가 근접")

            if trading_value >= 10000000000:
                score += 10
                reasons.append("거래대금 100억 이상")
            if trading_value >= 30000000000:
                score += 15
                reasons.append("거래대금 300억 이상")
            if trading_value >= 50000000000:
                score += 20
                reasons.append("거래대금 500억 이상")

            if volume >= 3000000:
                score += 10
                reasons.append("거래량 300만주 이상")
            if volume >= 10000000:
                score += 15
                reasons.append("거래량 1,000만주 이상")

            if close_near_high <= 3:
                score += 20
                reasons.append("종가가 고가 3% 이내")
            elif close_near_high <= 7:
                score += 10
                reasons.append("종가가 고가 7% 이내")

            if candle_type == "양봉":
                score += 10
                reasons.append("양봉 마감")
                if candle_rate >= 5:
                    score += 10
                    reasons.append("강한 양봉")
            elif candle_type == "음봉":
                score -= 20
                reasons.append("음봉 마감")

            if upper_tail_rate >= 8:
                score -= 15
                reasons.append("윗꼬리 과다")
            if lower_tail_rate >= 5 and candle_type == "양봉":
                score += 10
                reasons.append("아래꼬리 지지")

            if change_rate >= 28 and close_near_high > 5:
                score -= 20
                reasons.append("상한가 실패/과열 주의")

            if score >= 30:
                results.append({
                    "관심등록": False,
                    "종목코드": code,
                    "종목명": name,
                    "시장": market,
                    "차트보기": f"https://finance.naver.com/item/main.naver?code={code}",
                    "캔들": candle_type,
                    "등락률(%)": round(change_rate, 2),
                    "캔들등락률(%)": round(candle_rate, 2),
                    "거래량": int(volume),
                    "거래대금(억)": round(trading_value / 100000000, 1),
                    "고가대비종가거리(%)": round(close_near_high, 2),
                    "윗꼬리(%)": round(upper_tail_rate, 2),
                    "아래꼬리(%)": round(lower_tail_rate, 2),
                    "점수": score,
                    "분류이유": ", ".join(reasons),
                })

        except Exception:
            continue

        if i % 50 == 0:
            progress.progress(min(i / total, 1.0))
            status.write(f"전체 {total}개 중 분석 중... {i}/{total}")

    progress.progress(1.0)
    status.write("분석 완료")

    return pd.DataFrame(results)


tab1, tab2 = st.tabs(["📊 오늘 분석", "⭐ 저장한 관심종목"])

with tab1:
    if st.button("분석 시작"):
        with st.spinner("단타 후보 분석 중입니다."):
            result_df = analyze_market(selected_date)

        if result_df.empty:
            st.warning("조건에 맞는 종목이 없습니다.")
        else:
            result_df = result_df.sort_values(by="점수", ascending=False)

            st.subheader("🔥 내일 단타 관심종목 TOP 20")

            edited_df = st.data_editor(
                result_df.head(50),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "관심등록": st.column_config.CheckboxColumn("관심등록"),
                    "차트보기": st.column_config.LinkColumn("차트보기", display_text="네이버 차트"),
                },
                disabled=[
                    "종목코드", "종목명", "시장", "차트보기", "캔들", "등락률(%)",
                    "캔들등락률(%)", "거래량", "거래대금(억)", "고가대비종가거리(%)",
                    "윗꼬리(%)", "아래꼬리(%)", "점수", "분류이유"
                ],
            )

            selected_rows = edited_df[edited_df["관심등록"] == True]

            if st.button("선택한 종목 관심종목에 저장"):
                if selected_rows.empty:
                    st.warning("체크한 종목이 없습니다.")
                else:
                    saved = 0
                    for _, row in selected_rows.iterrows():
                        if save_watchlist(row):
                            saved += 1
                    st.success(f"{saved}개 종목 저장 완료")

            st.subheader("🟢 양봉 마감 종목")
            st.dataframe(result_df[result_df["캔들"] == "양봉"], use_container_width=True)

            st.subheader("🔴 음봉 마감 종목")
            st.dataframe(result_df[result_df["캔들"] == "음봉"], use_container_width=True)

with tab2:
    st.subheader("⭐ 저장한 관심종목")

    watch_df = load_watchlist()

    if watch_df.empty:
        st.info("아직 저장한 관심종목이 없습니다.")
    else:
        watch_df["차트보기"] = watch_df["code"].apply(
            lambda x: f"https://finance.naver.com/item/main.naver?code={x}"
        )

        st.dataframe(
            watch_df[["created_at", "code", "name", "market", "candle", "score", "reason", "차트보기"]],
            use_container_width=True,
            column_config={
                "차트보기": st.column_config.LinkColumn("차트보기", display_text="네이버 차트")
            },
        )

        delete_id = st.number_input("삭제할 관심종목 ID 입력", min_value=1, step=1)

        if st.button("해당 ID 삭제"):
            if delete_watchlist(delete_id):
                st.success("삭제 완료. 새로고침하면 반영됩니다.")
