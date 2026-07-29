import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from src.db_manager import init_db, sync_etf_universe, get_combined_flow_data
from src.collector import collect_historical_data
from src.processor import process_fund_flow_and_duration

# Streamlit Page Config
st.set_page_config(
    page_title="만기매칭형 ETF 수급(Fund Flow) 트래커",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Trading Desk Dark Theme
st.markdown("""
<style>
    /* Dark Theme styling */
    .main {
        background-color: #0E1117;
        color: #000000;
    }
    .stMetric {
        background-color: #1E222D;
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 12px 16px;
    }
    .stMetric label {
        color: #8B949E !important;
        font-size: 0.85rem !important;
    }
    .stMetric div[data-testid="stMetricValue"] {
        color: #38EF7D !important;
        font-size: 1.6rem !important;
        font-weight: 700;
    }
    h1, h2, h3 {
        color: #000000 !important;
        font-weight: 600;
    }
    .css-1d371fe {
        background-color: #161B22;
    }
</style>
""", unsafe_allow_html=True)

# Helper function to format currency in 100M KRW (억 원)
def format_eok(val):
    if pd.isna(val):
        return "0 억 원"
    eok = val / 100_000_000
    return f"{eok:,.2f} 억 원"

def main():
    # Initialize DB & Sync Universe if needed
    init_db()
    sync_etf_universe()

    st.title("📊 만기매칭형 ETF 수급(Fund Flow) 대시보드")
    st.caption("가격 평가 손익을 배제한 실질 자금 순유입액(Net Fund Flow) 종목별 집중 분석")

    # Sidebar Controls
    st.sidebar.header("⚙️ 트래커 설정")
    
    if st.sidebar.button("🔄 실시간 데이터 수집 및 갱신"):
        with st.spinner("KRX / 네이버 금융에서 최신 시장 데이터를 수집 및 처리 중입니다..."):
            collect_historical_data(days_back=30)
            process_fund_flow_and_duration()
            st.sidebar.success("데이터 수집 및 연산이 완료되었습니다!")
            st.rerun()

    # Load data from DB
    df = get_combined_flow_data()

    if df.empty:
        st.warning("⚠️ DB에 축적된 수급 데이터가 없습니다. 사이드바의 **[🔄 실시간 데이터 수집 및 갱신]** 버튼을 눌러 실제 시장 데이터를 가져오세요.")
        if st.button("지금 실시간 데이터 가져오기"):
            with st.spinner("실제 시장 데이터 수집 중..."):
                collect_historical_data(days_back=30)
                process_fund_flow_and_duration()
                st.rerun()
        return

    # Sidebar Filters
    st.sidebar.subheader("🔍 데이터 필터")
    
    # Asset Class Filter
    asset_classes = ["전체"] + sorted(list(df['asset_class'].dropna().unique()))
    selected_asset = st.sidebar.selectbox("기초자산 분류", asset_classes)

    # Date Range Filter
    min_date = pd.to_datetime(df['date']).min().date()
    max_date = pd.to_datetime(df['date']).max().date()
    
    date_range = st.sidebar.date_input(
        "조회 기간",
        value=(max(min_date, max_date - timedelta(days=20)), max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    if len(date_range) == 2:
        start_d, end_d = date_range
    else:
        start_d, end_d = min_date, max_date

    st.sidebar.subheader("🔄 정렬 기준")
    sort_option = st.sidebar.selectbox("종목 정렬", [
        "순자산(AUM) 큰 순", 
        "목표 만기일 빠른 순", 
        "목표 만기일 늦은 순"
    ])

    # Filter Data
    filtered_df = df.copy()
    filtered_df['date_dt'] = pd.to_datetime(filtered_df['date']).dt.date
    filtered_df = filtered_df[(filtered_df['date_dt'] >= start_d) & (filtered_df['date_dt'] <= end_d)]

    if selected_asset != "전체":
        filtered_df = filtered_df[filtered_df['asset_class'] == selected_asset]

    if filtered_df.empty:
        st.info("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    # Calculate Top KPI Cards
    total_flow = filtered_df['net_fund_flow'].sum()
    total_shares_change = filtered_df['net_shares_change'].sum()
    latest_date_str = filtered_df['date'].max()
    snapshot_df = filtered_df[filtered_df['date'] == latest_date_str].copy()
    active_etf_cnt = snapshot_df['ticker'].nunique()
    total_aum = snapshot_df['aum'].sum()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("총 순자산(AUM)", format_eok(total_aum))
    with col2:
        st.metric("기간 내 총 순유입액", format_eok(total_flow))
    with col3:
        st.metric("기간 내 상장좌수 변동", f"{total_shares_change:+,.0f} 좌")
    with col4:
        st.metric("최근 데이터 기준일", latest_date_str)

    st.markdown("---")

    # Prepare Ticker-Centric Summary Data
    summary_agg = filtered_df.groupby('ticker').agg({
        'net_fund_flow': 'sum',
        'net_shares_change': 'sum'
    }).reset_index()
    summary_df = pd.merge(snapshot_df, summary_agg, on='ticker', suffixes=('_latest', '_total'))

    # Apply Sorting
    if sort_option == "순자산(AUM) 큰 순":
        summary_df = summary_df.sort_values(by='aum', ascending=False)
    elif sort_option == "목표 만기일 빠른 순":
        summary_df = summary_df.sort_values(by='target_date', ascending=True)
    elif sort_option == "목표 만기일 늦은 순":
        summary_df = summary_df.sort_values(by='target_date', ascending=False)

    # Section 1: 종목별 현황 메인 테이블
    st.subheader("1. 종목별 수급 현황 및 듀레이션 요약")
    
    display_df = summary_df[['name', 'ticker', 'target_date', 'duration', 'aum', 'shares_outstanding', 'net_shares_change_total', 'net_fund_flow_total']].copy()
    display_df.rename(columns={
        'name': '종목명',
        'ticker': '종목코드',
        'target_date': '목표 만기일',
        'duration': '잔존 듀레이션(연)',
        'aum': '순자산총액(AUM)',
        'shares_outstanding': '현재 상장좌수',
        'net_shares_change_total': '기간 내 좌수 변동',
        'net_fund_flow_total': '총 누적 유입액(조회기간)'
    }, inplace=True)
    
    # Text formatting for the UI
    fmt_display_df = display_df.copy()
    fmt_display_df['잔존 듀레이션(연)'] = fmt_display_df['잔존 듀레이션(연)'].apply(lambda x: f"{x:.2f}년" if pd.notna(x) else "-")
    fmt_display_df['순자산총액(AUM)'] = fmt_display_df['순자산총액(AUM)'].apply(lambda x: f"{x/100000000:,.0f}억 원" if pd.notna(x) else "0")
    fmt_display_df['현재 상장좌수'] = fmt_display_df['현재 상장좌수'].apply(lambda x: f"{x:,.0f}좌" if pd.notna(x) else "0")
    fmt_display_df['기간 내 좌수 변동'] = fmt_display_df['기간 내 좌수 변동'].apply(lambda x: f"{x:+,.0f}좌" if pd.notna(x) else "0좌")
    fmt_display_df['총 누적 유입액(조회기간)'] = fmt_display_df['총 누적 유입액(조회기간)'].apply(lambda x: f"{x/100000000:,.2f}억 원" if pd.notna(x) else "0")
    
    st.dataframe(fmt_display_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Section 2: 종목별 누적 자금 유입액 막대 그래프
    st.subheader("2. 종목별 누적 자금 유입액 랭킹")
    
    summary_df['flow_total_eok'] = summary_df['net_fund_flow_total'] / 100000000
    
    fig_flow = go.Figure()
    fig_flow.add_trace(go.Bar(
        x=summary_df['name'],
        y=summary_df['flow_total_eok'],
        text=summary_df['flow_total_eok'].apply(lambda x: f"{x:,.1f}억"),
        textposition='outside',
        marker_color=summary_df['flow_total_eok'].apply(lambda x: '#00B0FF' if x >= 0 else '#FF5252')
    ))
    fig_flow.update_layout(
        template='plotly_dark',
        title="조회 기간 내 종목별 총 누적 순유입액 비교",
        xaxis_title="종목명 (정렬 기준에 따라 다름)",
        yaxis_title="순유입액 (억 원)",
        height=450,
        margin=dict(l=40, r=40, t=60, b=120)  # Extra bottom margin for long ticker names
    )
    st.plotly_chart(fig_flow, use_container_width=True)

    st.markdown("---")

    # Section 3: 개별 종목 시계열 상세 추이
    st.subheader("3. 개별 종목 시계열 추이 (좌수 및 유입액)")

    etf_options = summary_df[['ticker', 'name']].drop_duplicates()
    etf_dict = dict(zip(etf_options['ticker'], etf_options['name']))
    selected_ticker = st.selectbox(
        "분석 대상 종목 선택",
        options=list(etf_dict.keys()),
        format_func=lambda x: f"{etf_dict[x]} ({x})"
    )

    single_etf_df = filtered_df[filtered_df['ticker'] == selected_ticker].sort_values('date')

    if not single_etf_df.empty:
        fig_single = go.Figure()

        # Shares Line
        fig_single.add_trace(go.Scatter(
            x=single_etf_df['date'],
            y=single_etf_df['shares_outstanding'],
            name='상장좌수(Shares)',
            mode='lines+markers',
            line=dict(color='#00E676', width=2.5),
            yaxis='y1'
        ))

        # Fund Flow Bar (억 원)
        single_etf_df['flow_eok'] = single_etf_df['net_fund_flow'] / 100_000_000
        fig_single.add_trace(go.Bar(
            x=single_etf_df['date'],
            y=single_etf_df['flow_eok'],
            name='일별 순유입액(억 원)',
            marker_color=single_etf_df['flow_eok'].apply(lambda v: '#00B0FF' if v >= 0 else '#FF5252'),
            opacity=0.6,
            yaxis='y2'
        ))

        fig_single.update_layout(
            template='plotly_dark',
            title=f"{etf_dict[selected_ticker]} ({selected_ticker}) 시계열 추이",
            xaxis_title="날짜",
            yaxis=dict(title="상장좌수(좌)", side="left"),
            yaxis2=dict(title="일별 순유입액(억 원)", side="right", overlaying="y", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=420,
            margin=dict(l=40, r=40, t=60, b=40)
        )

        st.plotly_chart(fig_single, use_container_width=True)

if __name__ == "__main__":
    main()
