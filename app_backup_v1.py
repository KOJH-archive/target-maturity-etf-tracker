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
    page_title="만기매칭형 ETF 듀레이션별 수급(Fund Flow) 트래커",
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

    st.title("📊 만기매칭형 ETF 듀레이션별 수급(Fund Flow) 트래커")
    st.caption("가격 평가 손익을 배제한 실질 자금 순유입액(Net Fund Flow) 및 잔존 듀레이션 버킷 분석")

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

    # Filter Data
    filtered_df = df.copy()
    filtered_df['date_dt'] = pd.to_datetime(filtered_df['date']).dt.date
    filtered_df = filtered_df[(filtered_df['date_dt'] >= start_d) & (filtered_df['date_dt'] <= end_d)]

    if selected_asset != "전체":
        filtered_df = filtered_df[filtered_df['asset_class'] == selected_asset]

    if filtered_df.empty:
        st.info("선택한 조건에 해당하는 데이터가 없습니다.")
        return

    # Top KPI Cards
    total_flow = filtered_df['net_fund_flow'].sum()
    bucket_flow = filtered_df.groupby('duration_bucket')['net_fund_flow'].sum()
    top_bucket = bucket_flow.idxmax() if not bucket_flow.empty else "N/A"
    active_etf_cnt = filtered_df['ticker'].nunique()
    latest_date_str = filtered_df['date'].max()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("총 순유입액 (기간)", format_eok(total_flow))
    with col2:
        st.metric("최다 유입 듀레이션", top_bucket)
    with col3:
        st.metric("추적 ETF 수", f"{active_etf_cnt} 개")
    with col4:
        st.metric("최근 수집 일자", latest_date_str)

    st.markdown("---")

    # Section 1: 듀레이션 버킷별 일별 순유입액 Chart
    st.subheader("1. 듀레이션 버킷별 일별 순유입액 (Fund Flow)")

    bucket_daily = filtered_df.groupby(['date', 'duration_bucket'])['net_fund_flow'].sum().reset_index()
    bucket_daily['net_fund_flow_eok'] = bucket_daily['net_fund_flow'] / 100_000_000

    # Total 3-Day Moving Average
    total_daily = filtered_df.groupby('date')['net_fund_flow'].sum().reset_index()
    total_daily['flow_ma3_eok'] = (total_daily['net_fund_flow'].rolling(3, min_periods=1).mean()) / 100_000_000

    fig_bucket = go.Figure()

    # Bucket Color map
    color_map = {
        "0.5Y 이하": "#00E676",
        "1.0Y 구간": "#00B0FF",
        "1.5Y 구간": "#651FFF",
        "2.0Y 이상": "#FF4081"
    }

    buckets = ["0.5Y 이하", "1.0Y 구간", "1.5Y 구간", "2.0Y 이상"]
    for b in buckets:
        b_data = bucket_daily[bucket_daily['duration_bucket'] == b]
        if not b_data.empty:
            fig_bucket.add_trace(go.Bar(
                x=b_data['date'],
                y=b_data['net_fund_flow_eok'],
                name=b,
                marker_color=color_map.get(b, '#888888')
            ))

    # Add 3D Moving Average line
    fig_bucket.add_trace(go.Scatter(
        x=total_daily['date'],
        y=total_daily['flow_ma3_eok'],
        name='전체 3일 이동평균 (MA3)',
        mode='lines+markers',
        line=dict(color='#FFD700', width=2, dash='dot'),
        yaxis='y1'
    ))

    fig_bucket.update_layout(
        template='plotly_dark',
        barmode='stack',
        title="일별 듀레이션 버킷 순유입액 (단위: 억 원)",
        xaxis_title="날짜",
        yaxis_title="순유입액 (억 원)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        margin=dict(l=40, r=40, t=60, b=40)
    )

    st.plotly_chart(fig_bucket, use_container_width=True)

    st.markdown("---")

    # Section 2: 개별 ETF 상세 분석
    st.subheader("2. 개별 ETF 좌수 추이 및 실질 자금 유입액")

    etf_options = filtered_df[['ticker', 'name']].drop_duplicates()
    etf_dict = dict(zip(etf_options['ticker'], etf_options['name']))
    selected_ticker = st.selectbox(
        "분석 대상 ETF 선택",
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
            name='일별 실질 순유입액(억 원)',
            marker_color=single_etf_df['flow_eok'].apply(lambda v: '#00B0FF' if v >= 0 else '#FF5252'),
            opacity=0.6,
            yaxis='y2'
        ))

        fig_single.update_layout(
            template='plotly_dark',
            title=f"{etf_dict[selected_ticker]} ({selected_ticker}) 좌수 추이 & 일별 자금 수급",
            xaxis_title="날짜",
            yaxis=dict(title="상장좌수(좌)", side="left"),
            yaxis2=dict(title="실질 순유입액(억 원)", side="right", overlaying="y", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=420,
            margin=dict(l=40, r=40, t=60, b=40)
        )

        st.plotly_chart(fig_single, use_container_width=True)

    st.markdown("---")

    # Section 3: 최근 5일간 듀레이션별 자금 유입 합계 요약
    st.subheader("3. 최근 5일간 듀레이션 버킷별 수급 요약")

    recent_dates = sorted(df['date'].unique())[-5:]
    recent_df = df[df['date'].isin(recent_dates)]

    if not recent_df.empty:
        summary = recent_df.groupby(['duration_bucket', 'date'])['net_fund_flow'].sum().unstack(fill_value=0)
        summary_eok = summary / 100_000_000

        # Calculate Total and 5-Day Mean
        summary_eok['5일 합계(억)'] = summary_eok.sum(axis=1)
        summary_eok['5일 평균(억)'] = summary_eok.iloc[:, :-1].mean(axis=1)

        # Formatting
        formatted_summary = summary_eok.map(lambda v: f"{v:,.2f}")
        
        st.dataframe(formatted_summary, use_container_width=True)

if __name__ == "__main__":
    main()
