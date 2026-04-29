import streamlit as st
import pandas as pd
import FinanceDataReader as fdr
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET

st.set_page_config(page_title="단타 스캐너", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔥 단타 + 뉴스재료 분석 스캐너")
st.write("수급, 캔들, 기술적 조건, 최근 1개월 뉴스재료를 함께 분석합니다.")

selected_date = st.date_input("분석 날짜", datetime.today() - timedelta(days=1))


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
        "sector": str(row["섹터"]),
        "news_material": str(row["뉴스재료"]),
        "news_titles": str(row["뉴스제목"]),
    }
    supabase.table("watchlist").insert(item).execute()


def get_news_link(name):
    query = urllib.parse.quote(f"{name} 주가 상승 재료")
    return f"https://search.naver.com/search.naver?where=news&query={query}"


def fetch_news_titles(name):
    query = urllib.parse.quote(f"{name} 주가 OR 상승 OR 급등 OR 수주 OR 계약 OR 실적")
    url = f"https://news.google.com/rss/search?q={query}+when:30d&hl=ko&gl=KR&ceid=KR:ko"

    titles = []

    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        root = ET.fromstring(res.content)

        for item in root.findall(".//item")[:10]:
            title = item.find("title")
            if title is not None and title.text:
                clean_title = title.text.split(" - ")[0].strip()
                titles.append(clean_title)

    except:
        pass

    return titles


def infer_news_material(titles):
    if not titles:
        return "뉴스 부족"

    text = " ".join(titles)

    theme_keywords = {
        "2차전지/배터리": ["2차전지", "배터리", "리튬", "양극재", "음극재", "전고체", "ESS"],
        "반도체": ["반도체", "HBM", "D램", "낸드", "파운드리", "AI칩", "웨이퍼"],
        "AI/로봇": ["AI", "인공지능", "로봇", "챗봇", "자동화", "엔비디아"],
        "방산": ["방산", "무기", "수출", "K2", "K9", "드론", "국방"],
        "원전/전력": ["원전", "전력", "변압기", "전선", "송전", "전력망", "SMR"],
        "바이오/제약": ["임상", "FDA", "신약", "바이오", "제약", "치료제", "허가"],
        "수주/공급계약": ["수주", "공급계약", "계약", "납품", "MOU", "협약"],
        "실적개선": ["실적", "영업이익", "매출", "흑자", "어닝", "호실적"],
        "정책/정부지원": ["정부", "정책", "지원", "규제완화", "국책", "예산"],
        "경영권/지분": ["지분", "인수", "합병", "M&A", "최대주주", "경영권"],
        "중국/미중갈등": ["중국", "미중", "관세", "수출통제", "희토류"],
        "화장품/소비재": ["화장품", "K뷰티", "소비", "면세", "중국 소비"],
    }

    matched = []

    for theme, keywords in theme_keywords.items():
        count = sum(text.count(k) for k in keywords)
        if count > 0:
            matched.append((theme, count))

    if not matched:
        return "재료 불명확"

    matched = sorted(matched, key=lambda x: x[1], reverse=True)
    return ", ".join([x[0] for x in matched[:3]])

def infer_theme_sector(titles):
    if not titles:
        return "테마없음"

    text = " ".join(titles)

    theme_map = {
        "2차전지": ["2차전지", "배터리", "리튬", "양극재", "음극재", "전고체", "ESS"],
        "반도체/AI": ["반도체", "HBM", "D램", "AI", "엔비디아", "데이터센터"],
        "방산": ["방산", "무기", "수출", "드론", "국방"],
        "원전/전력": ["원전", "전력", "변압기", "전선", "송전"],
        "바이오": ["임상", "FDA", "신약", "치료제"],
        "자동차": ["자동차", "전기차", "자율주행"],
        "철강/소재": ["철강", "금속", "니켈", "구리"],
        "정책": ["정부", "정책", "지원", "규제완화"],
        "M&A/지분": ["인수", "합병", "지분", "경영권"],
        "중국/수출": ["중국", "수출", "관세"],
    }

    scores = []

    for theme, keywords in theme_map.items():
        count = sum(text.count(k) for k in keywords)
        if count > 0:
            scores.append((theme, count))

    if not scores:
        return "기타테마"

    scores = sorted(scores, key=lambda x: x[1], reverse=True)

    return scores[0][0]
    
def get_sector(name):
    if any(x in name for x in ["바이오", "제약", "셀", "헬스", "메디"]):
        return "바이오/제약"
    if any(x in name for x in ["반도체", "전자", "테크", "칩", "하이닉스"]):
        return "반도체/전자"
    if any(x in name for x in ["포스코", "철강", "스틸", "금속"]):
        return "철강/금속"
    if any(x in name for x in ["화학", "케미", "소재", "석유"]):
        return "화학/소재"
    if any(x in name for x in ["자동차", "모터", "차", "타이어"]):
        return "자동차/부품"
    if any(x in name for x in ["전력", "에너지", "전기", "배터리", "2차전지"]):
        return "에너지/2차전지"
    if any(x in name for x in ["AI", "소프트", "정보", "데이터", "시스템"]):
        return "AI/소프트웨어"
    return "기타"


def is_excluded(name):
    upper_name = name.upper()

    exclude_keywords = [
        "ETF", "ETN", "KODEX", "TIGER", "KBSTAR", "ACE", "SOL",
        "HANARO", "KOSEF", "ARIRANG", "TIMEFOLIO",
        "레버리지", "인버스", "선물", "스팩", "SPAC", "리츠", "REIT"
    ]

    if any(k in upper_name for k in exclude_keywords):
        return True

    if name.endswith("우") or "우B" in name or "우C" in name:
        return True

    return False


def scrape_naver_sise(url, pages=3):
    stocks = []

    for page in range(1, pages + 1):
        page_url = f"{url}&page={page}" if "?" in url else f"{url}?page={page}"

        try:
            res = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(res.text, "html.parser")

            for row in soup.select("table.type_2 tr"):
                cols = row.find_all("td")

                if len(cols) > 1:
                    try:
                        name = cols[1].text.strip()
                        link_tag = cols[1].find("a")

                        if not link_tag:
                            continue

                        code = link_tag["href"].split("=")[-1]

                        if not name or not code:
                            continue

                        if is_excluded(name):
                            continue

                        stocks.append((code, name))

                    except:
                        continue
        except:
            continue

    return stocks


def get_candidates():
    urls = [
        "https://finance.naver.com/sise/sise_quant.naver?sosok=0",
        "https://finance.naver.com/sise/sise_quant.naver?sosok=1",
        "https://finance.naver.com/sise/sise_rise.naver?sosok=0",
        "https://finance.naver.com/sise/sise_rise.naver?sosok=1",
    ]

    candidates = []

    for url in urls:
        candidates += scrape_naver_sise(url, pages=3)

    unique = {}
    for code, name in candidates:
        unique[code] = name

    return list(unique.items())[:400]


def fast_scan(date):
    theme_sector = infer_theme_sector(news_titles)
    start = (date - timedelta(days=45)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=1)).strftime("%Y-%m-%d")

    candidates = get_candidates()
    total = len(candidates)

    progress = st.progress(0)
    status = st.empty()
    found_box = st.empty()

    status.write(f"후보 종목 {total}개 분석 준비 중...")
    found_box.write("조건 통과 종목 0개")

    results = []

    if total == 0:
        status.write("후보 종목을 가져오지 못했습니다.")
        return pd.DataFrame()

    for idx, (code, name) in enumerate(candidates, start=1):
        try:
            df = fdr.DataReader(code, start, end)

            if df is not None and not df.empty:
                df = df[df.index <= pd.to_datetime(date)]

                if len(df) >= 25:
                    d = df.iloc[-1]

                    open_p = d["Open"]
                    high_p = d["High"]
                    close_p = d["Close"]
                    volume = d["Volume"]

                    if open_p != 0 and high_p != 0 and close_p != 0:
                        value = close_p * volume

                        change_rate = ((close_p - open_p) / open_p) * 100
                        close_near_high = ((high_p - close_p) / high_p) * 100
                        upper_tail = ((high_p - close_p) / close_p) * 100

                        ma5 = df["Close"].rolling(5).mean().iloc[-1]
                        ma20 = df["Close"].rolling(20).mean().iloc[-1]
                        high20 = df["High"].rolling(20).max().iloc[-2]
                        avg_volume20 = df["Volume"].rolling(20).mean().iloc[-2]
                        volume_power = volume / avg_volume20 if avg_volume20 > 0 else 0

                        candle = "양봉" if close_p > open_p else "음봉"
                        sector = get_sector(name)

                        if value >= 10000000000 and close_p >= 1000 and change_rate >= 3:
                            score = 0
                            reasons = []

                            if value >= 10000000000:
                                score += 10
                                reasons.append("거래대금 100억 이상")

                            if value >= 30000000000:
                                score += 15
                                reasons.append("거래대금 300억 이상")

                            if value >= 50000000000:
                                score += 20
                                reasons.append("거래대금 500억 이상")

                            if volume_power >= 2:
                                score += 15
                                reasons.append("20일 평균 거래량 2배 이상")

                            if volume_power >= 3:
                                score += 20
                                reasons.append("20일 평균 거래량 3배 이상")

                            if change_rate >= 5:
                                score += 15
                                reasons.append("5% 이상 상승")

                            if change_rate >= 8:
                                score += 20
                                reasons.append("8% 이상 상승")

                            if change_rate >= 15:
                                score += 20
                                reasons.append("15% 이상 급등")

                            if candle == "양봉":
                                score += 10
                                reasons.append("양봉 마감")
                            else:
                                score -= 15
                                reasons.append("음봉 마감")

                            if close_near_high <= 5:
                                score += 15
                                reasons.append("고가 5% 이내 마감")

                            if close_near_high <= 3:
                                score += 20
                                reasons.append("고가 3% 이내 마감")

                            if upper_tail <= 5:
                                score += 10
                                reasons.append("윗꼬리 짧음")

                            if close_p > ma5:
                                score += 10
                                reasons.append("5일선 위")

                            if close_p > ma20:
                                score += 10
                                reasons.append("20일선 위")

                            if ma5 > ma20:
                                score += 10
                                reasons.append("5일선 > 20일선")

                            if close_p >= high20:
                                score += 25
                                reasons.append("20일 신고가 돌파")

                            if change_rate >= 25 and close_near_high > 3:
                                score -= 15
                                reasons.append("과열 주의")

                            if score >= 45:
                                news_titles = fetch_news_titles(name)
                                news_material = infer_news_material(news_titles)
                                news_titles_text = " / ".join(news_titles[:5])

                                results.append({
                                    "관심": False,
                                    "종목코드": code,
                                    "종목명": name,
                                    "섹터": sector,
                                    "테마섹터": theme_sector,
                                    "뉴스재료": news_material,
                                    "뉴스건수": len(news_titles),
                                    "뉴스제목": news_titles_text,
                                    "차트": f"https://finance.naver.com/item/main.naver?code={code}",
                                    "뉴스": get_news_link(name),
                                    "캔들": candle,
                                    "등락률(%)": round(change_rate, 2),
                                    "거래대금(억)": round(value / 100000000, 1),
                                    "거래량폭증배수": round(volume_power, 2),
                                    "5일선": round(ma5, 0),
                                    "20일선": round(ma20, 0),
                                    "20일신고가돌파": "Y" if close_p >= high20 else "N",
                                    "고가대비종가거리(%)": round(close_near_high, 2),
                                    "점수": int(score),
                                    "이유": ", ".join(reasons)
                                })

        except:
            pass

        progress.progress(idx / total)
        status.write(f"분석 중... {idx}/{total}개 완료")
        found_box.write(f"조건 통과 종목 {len(results)}개")

    progress.progress(1.0)
    status.write(f"분석 완료: 총 {total}개 중 {len(results)}개 통과")

    result = pd.DataFrame(results)

    if not result.empty:
        result = result.sort_values(by="점수", ascending=False)

    return result


tab1, tab2 = st.tabs(["📊 분석", "⭐ 관심종목"])

with tab1:
    if "result" not in st.session_state:
        st.session_state.result = pd.DataFrame()

    if st.button("⚡ 분석 시작"):
        with st.spinner("분석 중입니다..."):
            st.session_state.result = fast_scan(selected_date)

    result = st.session_state.result

    if result.empty:
        st.info("분석 시작 버튼을 눌러주세요. 조건 만족 종목이 없으면 결과가 비어 있을 수 있습니다.")
    else:
        edited = st.data_editor(
            result.head(20),
            key="editor",
            column_config={
                "관심": st.column_config.CheckboxColumn("관심"),
                "차트": st.column_config.LinkColumn("차트", display_text="차트보기"),
                "뉴스": st.column_config.LinkColumn("뉴스", display_text="뉴스보기"),
            },
            use_container_width=True,
            hide_index=True
        )

        selected = edited[edited["관심"] == True]

        if st.button("관심종목 저장"):
            if selected.empty:
                st.warning("체크한 종목이 없습니다.")
            else:
                for _, row in selected.iterrows():
                    save_watchlist(row)
                st.success(f"{len(selected)}개 저장 완료")


with tab2:
    watch = load_watchlist()

    if watch.empty:
        st.info("관심종목 없음")
    else:
        for col in ["sector", "news_material", "news_titles"]:
            if col not in watch.columns:
                watch[col] = ""

        watch["차트"] = watch["code"].apply(
            lambda x: f"https://finance.naver.com/item/main.naver?code={x}"
        )

        st.dataframe(
            watch[["name", "sector", "score", "reason", "news_material", "news_titles", "차트"]],
            column_config={
                "차트": st.column_config.LinkColumn("차트", display_text="보기")
            },
            use_container_width=True
        )
