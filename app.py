import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
from datetime import datetime
from collections import deque
import warnings

# 忽略警告
warnings.filterwarnings("ignore")

# ==============================================================================
# 1. 核心计算引擎 (v21 Core Engine - Robust & Safe)
# ==============================================================================

def clean_str(series):
    """字符串清洗：去空、转大写"""
    return series.astype(str).str.strip().str.upper().replace('NAN', '')

def standardize_month_vectorized(series):
    """批量标准化月份格式 (DEC 25)"""
    s = series.astype(str).str.strip().str.upper()
    s = s.replace('NAN', '')
    s = s.str.replace('-', ' ', regex=False).str.replace('/', ' ', regex=False)
    dates = pd.to_datetime(s, errors='coerce')
    return dates.dt.strftime('%b %y').str.upper().fillna(s)

def load_data_engine(paper_file, phys_file):
    """数据加载引擎 (带重试机制)"""
    try:
        # 读取纸货
        if paper_file.name.endswith(('.xlsx', '.xls')):
            df_p = pd.read_excel(paper_file)
        else:
            try:
                df_p = pd.read_csv(paper_file)
            except:
                paper_file.seek(0) # 关键：重置指针
                df_p = pd.read_csv(paper_file, encoding='gbk')

        # 读取实货
        if phys_file.name.endswith(('.xlsx', '.xls')):
            df_ph = pd.read_excel(phys_file)
        else:
            try:
                df_ph = pd.read_csv(phys_file)
            except:
                phys_file.seek(0) # 关键：重置指针
                df_ph = pd.read_csv(phys_file, encoding='gbk')
    except Exception as e:
        st.error(f"文件读取失败: {e}")
        return pd.DataFrame(), pd.DataFrame()

    # --- 清除列名空格 ---
    df_p.columns = df_p.columns.str.strip()
    df_ph.columns = df_ph.columns.str.strip()

    # --- 纸货清洗 ---
    df_p['Trade Date'] = pd.to_datetime(df_p['Trade Date'], errors='coerce')
    df_p['Volume'] = pd.to_numeric(df_p['Volume'], errors='coerce').fillna(0)
    df_p['Std_Commodity'] = clean_str(df_p['Commodity'])
    
    if 'Month' in df_p.columns:
        df_p['Month'] = standardize_month_vectorized(df_p['Month'])
    else:
        df_p['Month'] = ''
        
    if 'Recap No' not in df_p.columns:
        df_p['Recap No'] = df_p.index.astype(str)
    
    # 补全财务字段
    for col in ['Price', 'Mtm Price', 'Total P/L']:
        if col not in df_p.columns: df_p[col] = 0

    # --- 实货清洗 ---
    col_map = {
        'Target_Pricing_Month': 'Target_Contract_Month', 
        'Target Pricing Month': 'Target_Contract_Month', 
        'Month': 'Target_Contract_Month'
    }
    df_ph.rename(columns=col_map, inplace=True)
    
    df_ph['Volume'] = pd.to_numeric(df_ph['Volume'], errors='coerce').fillna(0)
    df_ph['Unhedged_Volume'] = df_ph['Volume']
    df_ph['Hedge_Proxy'] = clean_str(df_ph['Hedge_Proxy']) if 'Hedge_Proxy' in df_ph.columns else ''
    df_ph['Pricing_Benchmark'] = clean_str(df_ph['Pricing_Benchmark'])
    
    if 'Target_Contract_Month' in df_ph.columns:
        df_ph['Target_Contract_Month'] = standardize_month_vectorized(df_ph['Target_Contract_Month'])
    
    # 处理指定日
    if 'Designation_Date' in df_ph.columns:
        df_ph['Designation_Date'] = pd.to_datetime(df_ph['Designation_Date'], errors='coerce')
    elif 'Pricing_Start' in df_ph.columns:
        df_ph['Designation_Date'] = pd.to_datetime(df_ph['Pricing_Start'], errors='coerce')
    else:
        df_ph['Designation_Date'] = pd.NaT

    return df_p, df_ph

def calculate_net_positions(df_paper):
    """Step 1: 纸货内部 FIFO 净仓计算"""
    # 确保按时间排序
    df_paper = df_paper.sort_values(by='Trade Date').reset_index(drop=True)
    df_paper['Group_Key'] = df_paper['Std_Commodity'] + "_" + df_paper['Month']
    
    records = df_paper.to_dict('records')
    groups = {}
    for i, row in enumerate(records):
        key = row['Group_Key']
        if key not in groups: groups[key] = []
        groups[key].append(i)
    
    for key, indices in groups.items():
        open_queue = deque()
        for idx in indices:
            row = records[idx]
            current_vol = row.get('Volume', 0)
            
            # 初始化关键字段
            records[idx]['Net_Open_Vol'] = current_vol
            records[idx]['Closed_Vol'] = 0
            records[idx]['Close_Events'] = [] 
            
            if abs(current_vol) < 0.0001: continue
            current_sign = 1 if current_vol > 0 else -1
            
            while open_queue:
                q_idx, q_vol, q_sign = open_queue[0]
                if q_sign != current_sign:
                    offset = min(abs(current_vol), abs(q_vol))
                    
                    # 记录平仓事件
                    close_event = {
                        'Ref': str(records[idx].get('Recap No', '')),
                        'Date': records[idx].get('Trade Date'),
                        'Vol': offset,
                        'Price': records[idx].get('Price', 0)
                    }
                    records[q_idx]['Close_Events'].append(close_event)
                    
                    # 净额抵消 (减法)
                    current_vol -= (current_sign * offset)
                    q_vol -= (q_sign * offset)
                    
                    records[q_idx]['Closed_Vol'] += offset
                    records[q_idx]['Net_Open_Vol'] = q_vol
                    records[idx]['Closed_Vol'] += offset
                    records[idx]['Net_Open_Vol'] = current_vol
                    
                    if abs(q_vol) < 0.0001: open_queue.popleft()
                    else: open_queue[0] = (q_idx, q_vol, q_sign)
                    
                    if abs(current_vol) < 0.0001: break
                else:
                    break
            
            if abs(current_vol) > 0.0001:
                open_queue.append((idx, current_vol, current_sign))
                
    return pd.DataFrame(records)

def format_close_details(events):
    if not events: return "", 0
    details = []
    total_vol = 0
    total_val = 0
    sorted_events = sorted(events, key=lambda x: x['Date'] if pd.notna(x['Date']) else pd.Timestamp.min)
    for e in sorted_events:
        d_str = e['Date'].strftime('%Y-%m-%d') if pd.notna(e['Date']) else 'N/A'
        p_str = f"@{e['Price']}" if pd.notna(e['Price']) else ""
        details.append(f"[{d_str} #{e['Ref']} V:{e['Vol']:.0f} {p_str}]")
        if pd.notna(e['Price']):
            total_vol += e['Vol']
            total_val += (e['Vol'] * e['Price'])
    return " -> ".join(details), total_vol

def auto_match_hedges(physical_df, paper_df):
    """Step 2: 实货匹配 (Safe Update Version)"""
    hedge_relations = []
    
    # 强制初始化，防止 KeyError
    paper_df['Allocated_To_Phy'] = 0.0
    
    # 索引构建 (只取有净敞口的单子)
    active_paper = paper_df[abs(paper_df['Net_Open_Vol']) > 0.0001].copy()
    active_paper['Allocated_To_Phy'] = 0.0
    active_paper['_original_index'] = active_paper.index

    # 实货排序 (抢单公平性)
    physical_df['Sort_Date'] = physical_df['Designation_Date'].fillna(pd.Timestamp.max)
    physical_df_sorted = physical_df.sort_values(by=['Sort_Date', 'Cargo_ID'])

    for idx, cargo in physical_df_sorted.iterrows():
        cargo_id = cargo['Cargo_ID']
        phy_vol = cargo['Unhedged_Volume']
        proxy = str(cargo['Hedge_Proxy'])
        target_month = cargo.get('Target_Contract_Month', None)
        phy_dir = cargo.get('Direction', 'Buy')
        desig_date = cargo.get('Designation_Date', pd.NaT)
        
        required_open_sign = -1 if 'BUY' in str(phy_dir).upper() else 1
        
        # 筛选：品种 + 月份 + 方向
        mask = (
            (active_paper['Std_Commodity'].str.contains(proxy, regex=False)) & 
            (active_paper['Month'] == target_month) &
            (np.sign(active_paper['Net_Open_Vol']) == required_open_sign)
        )
        candidates_df = active_paper[mask].copy()
        
        if candidates_df.empty: continue
        
        # 排序策略 (v19 开放式匹配: Abs_Lag 最小优先)
        if pd.notna(desig_date) and not candidates_df['Trade Date'].isnull().all():
            candidates_df['Time_Lag_Days'] = (candidates_df['Trade Date'] - desig_date).dt.days
            candidates_df['Abs_Lag'] = candidates_df['Time_Lag_Days'].abs()
            candidates_df = candidates_df.sort_values(by=['Abs_Lag', 'Trade Date'])
        else:
            candidates_df['Time_Lag_Days'] = np.nan
            candidates_df = candidates_df.sort_values(by='Trade Date')
            
        candidates = candidates_df.to_dict('records')
        
        for ticket in candidates:
            if abs(phy_vol) < 1: break
            
            orig_idx = ticket['_original_index']
            
            # 实时查余额
            curr_allocated = active_paper.at[orig_idx, 'Allocated_To_Phy']
            curr_net_open = active_paper.at[orig_idx, 'Net_Open_Vol']
            net_avail = curr_net_open - curr_allocated
            
            if abs(net_avail) < 0.0001: continue
            
            # 分配量
            if abs(net_avail) >= abs(phy_vol):
                alloc_amt = (1 if net_avail > 0 else -1) * abs(phy_vol)
            else:
                alloc_amt = net_avail
                
            phy_vol -= (-alloc_amt)
            active_paper.at[orig_idx, 'Allocated_To_Phy'] += alloc_amt
            
            # 财务数据
            open_price = ticket.get('Price', 0)
            mtm_price = ticket.get('Mtm Price', 0)
            total_pl = ticket.get('Total P/L', 0)
            close_path, _ = format_close_details(ticket.get('Close_Events', []))
            
            unrealized_mtm = (mtm_price - open_price) * alloc_amt
            
            ratio = 0
            if abs(ticket.get('Volume', 0)) > 0:
                ratio = abs(alloc_amt) / abs(ticket['Volume'])
            alloc_total_pl = total_pl * ratio
            
            hedge_relations.append({
                'Cargo_ID': cargo_id,
                'Ticket_ID': ticket.get('Recap No'),
                'Month': ticket.get('Month'),
                'Trade_Date': ticket.get('Trade Date'),
                'Allocated_Vol': alloc_amt,
                'Open_Price': open_price,
                'MTM_PL': round(unrealized_mtm, 2),
                'Total_PL_Alloc': round(alloc_total_pl, 2),
                'Time_Lag': ticket.get('Time_Lag_Days'),
                'Close_Path': close_path
            })
            
        physical_df_sorted.at[idx, 'Unhedged_Volume'] = phy_vol
        
    # --- 安全回写分配量 ---
    if not active_paper.empty:
        # 使用 map 进行回写，比 update 更稳健
        alloc_series = active_paper.set_index('_original_index')['Allocated_To_Phy']
        paper_df['Allocated_To_Phy'] = paper_df.index.map(alloc_series).fillna(0.0)
    else:
        paper_df['Allocated_To_Phy'] = 0.0
        
    return pd.DataFrame(hedge_relations), physical_df_sorted, paper_df

# ==============================================================================
# 2. Streamlit UI 界面逻辑
# ==============================================================================

st.set_page_config(page_title="Hedge Master Analytics", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

col_title = st.columns([1])[0]
with col_title:
    st.title("Hedge Master Analytics 📊")
    st.markdown("**基于 v21 引擎 (Robust) 的智能套保有效性分析系统** | *Designed for Energy Trading*")

st.divider()

with st.sidebar:
    st.header("📂 数据接入")
    ticket_file = st.file_uploader("上传纸货水单 (Ticket Data)", type=['xlsx', 'csv'])
    phys_file = st.file_uploader("上传实货台账 (Physical Ledger)", type=['xlsx', 'csv'])
    run_btn = st.button("🚀 开始全景分析", type="primary", use_container_width=True)
    st.caption("Engine: v21 Logic (Fix Key Error)")

if run_btn:
    if ticket_file and phys_file:
        with st.spinner('正在运行核心引擎...'):
            # 1. 加载
            df_p, df_ph = load_data_engine(ticket_file, phys_file)
            
            if not df_ph.empty and not df_p.empty:
                # 2. 核心计算
                start_t = time.time()
                
                # Step 1: 净仓计算
                df_p_net = calculate_net_positions(df_p)
                
                # Step 2: 匹配
                df_rels, df_ph_final, df_p_final = auto_match_hedges(df_ph, df_p_net)
                
                calc_time = time.time() - start_t
                st.success(f"分析完成！耗时 {calc_time:.2f} 秒")
                
                # --- KPI ---
                total_exp = df_ph_final['Volume'].abs().sum()
                unhedged = df_ph_final['Unhedged_Volume'].abs().sum()
                hedged_vol = total_exp - unhedged
                coverage = (hedged_vol / total_exp * 100) if total_exp > 0 else 0
                total_mtm = df_rels['MTM_PL'].sum() if not df_rels.empty else 0
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("实货总敞口", f"{total_exp:,.0f} BBL")
                kpi2.metric("套保覆盖率", f"{coverage:.1f}%")
                kpi3.metric("风险裸露敞口", f"{unhedged:,.0f} BBL")
                kpi4.metric("套保组合 MTM", f"${total_mtm:,.0f}")
                
                st.markdown("---")

                # --- Charts ---
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.subheader("📅 月度覆盖")
                    if 'Target_Contract_Month' in df_ph_final.columns:
                        chart_data = df_ph_final.groupby('Target_Contract_Month')[['Volume', 'Unhedged_Volume']].sum().abs().reset_index()
                        chart_data['Hedged'] = chart_data['Volume'] - chart_data['Unhedged_Volume']
                        fig = px.bar(chart_data, x='Target_Contract_Month', y=['Hedged', 'Unhedged_Volume'], 
                                     title="Monthly Exposure vs Hedge", template="plotly_white",
                                     color_discrete_map={'Hedged': '#00CC96', 'Unhedged_Volume': '#EF553B'})
                        st.plotly_chart(fig, use_container_width=True)
                
                with c2:
                    st.subheader("🍰 占比")
                    fig_pie = px.pie(values=[hedged_vol, unhedged], names=['Hedged', 'Unhedged'], 
                                     color_discrete_sequence=['#00CC96', '#EF553B'])
                    st.plotly_chart(fig_pie, use_container_width=True)

                # --- Tables ---
                st.subheader("📋 数据账本")
                # 修复引号
                tab1, tab2, tab3 = st.tabs(["✅ 匹配明细", "⚠️ 实货剩余", "📦 纸货剩余"])
                
                with tab1:
                    if not df_rels.empty and len(df_rels) > 0:
                        st.dataframe(df_rels, use_container_width=True)
                        csv = df_rels.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 下载明细", csv, "hedge_allocation.csv", "text/csv")
                    else:
                        st.info("无匹配记录 (请检查实货Proxy和纸货Commodity名称是否包含关系)")
                        
                with tab2:
                    st.dataframe(df_ph_final[abs(df_ph_final['Unhedged_Volume']) > 1], use_container_width=True)
                    
                with tab3:
                    # 容错：防止 Allocated_To_Phy 列依然丢失
                    if 'Allocated_To_Phy' not in df_p_final.columns:
                        df_p_final['Allocated_To_Phy'] = 0.0
                    
                    df_p_final['Implied_Remaining'] = df_p_final['Volume'] - df_p_final['Allocated_To_Phy']
                    unused = df_p_final[abs(df_p_final['Implied_Remaining']) > 1]
                    
                    cols_show = ['Recap No', 'Std_Commodity', 'Month', 'Volume', 'Allocated_To_Phy', 'Implied_Remaining', 'Price']
                    final_cols = [c for c in cols_show if c in unused.columns]
                    st.dataframe(unused[final_cols], use_container_width=True)
            else:
                st.error("数据加载为空，请检查文件编码或格式 (支持 .xlsx, .csv)")
    else:
        st.warning("请上传文件")
