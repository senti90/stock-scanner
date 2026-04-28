import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timedelta

st.set_page_config(page_title="단타 스캐너", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔥 장마감 스캐너")
st.write("ETF/ETN/리츠/스팩/우선주를 제외하고, 단타 후보만 필터링합니다.")

selected_date = st.date_input("분석 날짜를 선택하세요", datetime.today() - timedelta(days=1))


def load_watchlist():
    data = supabase.table("watchlist").select("*").execute()
    return pd.DataFrame(data.data)


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


def is_excluded_stock(name):
    exclude_keywords = [
        "ETF", "ETN", "KODEX", "TIGER", "ACE", "SOL", "HANARO",
        "KBSTAR", "KOSEF", "ARIRANG", "TIMEFOLIO", "RISE",
        "레버리지", "인버스", "선물", "TR", "합성",
        "스팩", "SPAC", "리츠", "REIT", "우선주"
    ]

    if any(keyword in name.upper() for keyword in exclude_keywords):
        return True

    # 우선주 제거: 삼성전자우, 현대차2우B 같은 형태
    if name.endswith("우") or "우B" in name or "우C" in name:
        return True

    return False


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
                link = cols[1].find("a")["href"]
                code = link.split("=")[-1]

                if not name or not code:
                    continue

                if is_excluded_stock(name):
                    continue

                stocks.append((code, name))

            except:
                continue

    return stocks[:200]


def fast_scan(date):
    start_date = (date - timedelta(days=40)).strftime("%Y-%m-%d")
    end_date = (date + timedelta(days=1)).strftime("%Y-%m-%d")

    stocks = get_top_volume()
    results = []

    for code, name in stocks:
        try:
            if is_excluded_stock(name):
                continue

            df = fdr.DataReader(code, start_date, end_date)

            if df is None or df.empty or len(df) < 25:
                continue

            df = df[df.index <= pd.to_datetime(date)]

            if len(df) < 25:
                continue

            d = df.iloc[-1]

            open_price = d["Open"]
            high_price = d["High"]
            close_price = d["Close"]
            volume = d["Volume"]

            if open_price == 0 or high_price == 0 or close_price == 0:
                continue

            trading_value = close_price * volume

            change_rate = ((close_price - open_price) / open_price) * 100
            close_near_high = ((high_price - close_price) / high_price) * 100
            upper_tail = ((high_price - close_price) / close_price) * 100

            ma5 = df["Close"].rolling(5).mean().iloc[-1]
            ma20 = df["Close"].rolling(20).mean().iloc[-1]
            high20 = df["High"].rolling(20).max().iloc[-2]
            avg_volume20 = df["Volume"].rolling(20).mean().iloc[-2]
            volume_power = volume / avg_volume20 if avg_volume20 > 0 else 0

            candle = "양봉" if close_price > open_price else "음봉"

            # 1차 강제 필터
            if trading_value < 20000000000:
                continue

            if close_price < 1000:
                continue

            if change_rate < 5:
                continue

            if candle != "양봉":
                continue

            if close_near_high > 5:
                continue

            if upper_tail > 8:
                continue

            score = 0
            reasons = []

            if trading_value >= 20000000000:
                score += 15
                reasons.append("거래대금 200억 이상")

            if trading_value >= 50000000000:
                score += 20
                reasons.append("거래대금 500억 이상")

            if volume_power >= 2:
                score += 15
                reasons.append("20일 평균 거래량 2배 이상")

            if volume_power >= 3:
                score += 20
                reasons.append("20일 평균 거래량 3배 이상")

            if change_rate >= 8:
                score += 20
                reasons.append("8% 이상 상승")

            if change_rate >= 15:
                score += 20
                reasons.append("15% 이상 급등")

            if close_near_high <= 3:
                score += 20
                reasons.append("고가 3% 이내 마감")

            if upper_tail <= 3:
                score += 10
                reasons.append("윗꼬리 짧음")

            if close_price > ma5:
                score += 10
                reasons.append("5일선 위 마감")

            if close_price > ma20:
                score += 10
                reasons.append("20일선 위 마감")

            if close_price >= high20:
                score += 25
                reasons.append("20일 신고가 돌파")

            if ma5 > ma20:
                score += 10
                reasons.append("5일선이 20일선 위")

            if change_rate >= 25 and close_near_high > 3:
                score -= 15
                reasons.append("과열 주의")

            if score >= 60:
                results.append({
                    "관심": False,
                    "종목코드": code,
                    "종목명": name,
                    "차트": f"https://finance.naver.com/item/main.naver?code={code}",
                    "캔들": candle,
                    "등락률(%)": round(change_rate, 2),
                    "거래대금(억)": round(trading_value / 100000000, 1),
                    "거래량폭증배수": round(volume_power, 2),
                    "5일선": round(ma5, 0),
                    "20일선": round(ma20, 0),
                    "20일신고가돌파": "Y" if close_price >= high20 else "N",
                    "고가대비종가거리(%)": round(close_near_high, 2),
                    "점수": int(score),
                    "이유": ", ".join(reasons)
                })

        except:
            continue

    result = pd.DataFrame(results)

    if not result.empty:
        result = result.sort_values(by="점수", ascending=False)

    return result


tab1, tab2 = st.tabs(["📊 분석", "⭐ 관심종목"])

with tab1:
    if "scan_result" not in st.session_state:
        st.session_state.scan_result = pd.DataFrame()

    if st.button("⚡ 기술분석 시작"):
        with st.spinner("기술적 조건 분석 중..."):
            st.session_state.scan_result = fast_scan(selected_date)

    result = st.session_state.scan_result

    if result.empty:
        st.warning("아직 분석 결과가 없습니다. 기술분석 시작 버튼을 눌러주세요.")
    else:
        result = result.head(15)

        edited = st.data_editor(
            result,
            key="stock_editor",
            column_config={
                "관심": st.column_config.CheckboxColumn("관심"),
                "차트": st.column_config.LinkColumn("차트", display_text="차트보기"),
            },
            hide_index=True,
            use_container_width=True
        )

        selected = edited[edited["관심"] == True]

        if st.button("관심종목 저장"):
            if selected.empty:
                st.warning("체크한 종목이 없습니다.")
            else:
                saved_count = 0
                for _, row in selected.iterrows():
                    save_watchlist(row)
                    saved_count += 1

                st.success(f"{saved_count}개 관심종목 저장 완료")

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
            },
            use_container_width=True
        )
