import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta

st.set_page_config(page_title="장마감 스캐너", layout="wide")

st.title("📈 장마감 단타 스캐너")
st.write("장마감 후 데이터를 기준으로 내일 단타 관심종목을 빠르게 분류합니다.")

selected_date = st.date_input("분석 날짜 선택", datetime.today() - timedelta(days=1))
date_str = selected_date.strftime("%Y-%m-%d")


@st.cache_data
def get_stock_list():
    kospi = fdr.StockListing("KOSPI")
    kosdaq = fdr.StockListing("KOSDAQ")
    stocks = pd.concat([kospi, kosdaq], ignore_index=True)
    return stocks[["Code", "Name", "Market"]]


@st.cache_data
def load_stock_data(code, start_date, end_date):
    return fdr.DataReader(code, start_date, end_date)


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
            # 스팩 / 우선주 / ETF성 종목 일부 제거
            if "스팩" in name or "SPAC" in name or "우" == name[-1:]:
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

            # ✅ 단타용 1차 필터: 여기서 대부분 제거
            if volume < 500000:
                continue

            if trading_value < 10000000000:  # 거래대금 100억 미만 제거
                continue

            if close_price < 1000:  # 동전주 제거
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

            # 상승률 점수
            if change_rate >= 7:
                score += 20
                reasons.append("7% 이상 상승")

            if change_rate >= 15:
                score += 20
                reasons.append("15% 이상 급등")

            if change_rate >= 25:
                score += 20
                reasons.append("상한가 근접")

            # 거래대금 점수
            if trading_value >= 10000000000:
                score += 10
                reasons.append("거래대금 100억 이상")

            if trading_value >= 30000000000:
                score += 15
                reasons.append("거래대금 300억 이상")

            if trading_value >= 50000000000:
                score += 20
                reasons.append("거래대금 500억 이상")

            # 거래량 점수
            if volume >= 3000000:
                score += 10
                reasons.append("거래량 300만주 이상")

            if volume >= 10000000:
                score += 15
                reasons.append("거래량 1,000만주 이상")

            # 종가 위치
            if close_near_high <= 3:
                score += 20
                reasons.append("종가가 고가 3% 이내")

            elif close_near_high <= 7:
                score += 10
                reasons.append("종가가 고가 7% 이내")

            # 캔들
            if candle_type == "양봉":
                score += 10
                reasons.append("양봉 마감")

                if candle_rate >= 5:
                    score += 10
                    reasons.append("강한 양봉")

            elif candle_type == "음봉":
                score -= 20
                reasons.append("음봉 마감")

            else:
                reasons.append("보합 마감")

            # 꼬리 판단
            if upper_tail_rate >= 8:
                score -= 15
                reasons.append("윗꼬리 과다")

            if lower_tail_rate >= 5 and candle_type == "양봉":
                score += 10
                reasons.append("아래꼬리 지지")

            # 과열 감점
            if change_rate >= 28 and close_near_high > 5:
                score -= 20
                reasons.append("상한가 실패/과열 주의")

            # 최종 저장
            if score >= 30:
                results.append({
                    "종목코드": code,
                    "종목명": name,
                    "시장": market,
                    "캔들": candle_type,
                    "등락률(%)": round(change_rate, 2),
                    "캔들등락률(%)": round(candle_rate, 2),
                    "거래량": int(volume),
                    "거래대금(억)": round(trading_value / 100000000, 1),
                    "고가대비종가거리(%)": round(close_near_high, 2),
                    "윗꼬리(%)": round(upper_tail_rate, 2),
                    "아래꼬리(%)": round(lower_tail_rate, 2),
                    "점수": score,
                    "분류이유": ", ".join(reasons)
                })

        except Exception:
            continue

        if i % 50 == 0:
            progress.progress(min(i / total, 1.0))
            status.write(f"전체 {total}개 중 분석 중... {i}/{total}")

    progress.progress(1.0)
    status.write("분석 완료")

    return pd.DataFrame(results)


if st.button("분석 시작"):
    with st.spinner("단타 후보 분석 중입니다."):
        result_df = analyze_market(selected_date)

    if result_df.empty:
        st.warning("조건에 맞는 종목이 없습니다.")
    else:
        result_df = result_df.sort_values(by="점수", ascending=False)

        st.subheader("🔥 내일 단타 관심종목 TOP 20")
        st.dataframe(result_df.head(20), use_container_width=True)

        st.subheader("🟢 양봉 마감 종목")
        st.dataframe(result_df[result_df["캔들"] == "양봉"], use_container_width=True)

        st.subheader("🔴 음봉 마감 종목")
        st.dataframe(result_df[result_df["캔들"] == "음봉"], use_container_width=True)

        st.subheader("🚀 +10% 이상 급등주")
        st.dataframe(result_df[result_df["등락률(%)"] >= 10], use_container_width=True)

        st.subheader("💰 거래대금 500억 이상")
        st.dataframe(result_df[result_df["거래대금(억)"] >= 500], use_container_width=True)

        csv = result_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="CSV 다운로드",
            data=csv,
            file_name=f"stock_scanner_{date_str}.csv",
            mime="text/csv"
        )