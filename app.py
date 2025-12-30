import streamlit as st
import pandas as pd
import numpy as np
import io
import time
import warnings
from datetime import datetime
from collections import deque
import plotly.express as px
import plotly.graph_objects as go

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------
# 1. 基础工具 (Utils)
# ---------------------------------------------------------

def clean_str(series):
    """清洗字符串：去除前后空格，转大写，替换 'NAN' 为''。"""
    return series.astype(str).str.strip().str.upper().replace('NAN', '')

def standardize_month_vectorized(series):
    """将字符串月份标准化为统一的 `MON YY` 格式（例如 'JAN 24'）。"""
    s = series.astype(str).str.strip().str.upper()
    s = s.str.replace('-', ' ', regex=False).str.replace('/', ' ', regex=False)
    # 首先尝试直接解析
    dates = pd.to_datetime(s, errors='coerce')
    # 提取正常解析的结果
    result = dates.dt.strftime('%b %y').str.upper()
    # 处理无法解析的情况
    mask_invalid = dates.isna()
    if mask_invalid.any():
        invalid = s[mask_invalid]
        # 尝试匹配反转形式，例如 '26 APR' -> 'APR 26'
        import re
        def swap_if_match(val):
            m = re.match(r'^(\d{2})\s*([A-Z]{3})$', val)
            if m:
                yr, mon = m.groups()
                return f"{mon} {yr}"
            return val
        swapped = invalid.map(swap_if_match)
        # 尝试再次解析
        swapped_dates = pd.to_datetime(swapped, errors='coerce')
        # 格式化
        swapped_formatted = swapped_dates.dt.strftime('%b %y').str.upper()
        # 对成功解析的部分用新值
        result.loc[mask_invalid & swapped_dates.notna()] = swapped_formatted.loc[
            swapped_dates.notna()
        ]
        # 对仍然无法解析的部分保持原样
        result.loc[mask_invalid & swapped_dates.isna()] = swapped.loc[
            swapped_dates.isna()
        ]
    return result

# ---------------------------------------------------------
# 2. 核心：FIFO 净仓计算引擎 (Corrected Netting Engine)
# ---------------------------------------------------------

def calculate_net_positions_corrected(df_paper):
    """修正后的 FIFO 净仓引擎：内部开仓和平仓抵消。"""
    start_time = time.time()
    st.info("执行纸货内部对冲 (FIFO Netting)...")
    progress_bar = st.progress(0)
    
    # 按交易日期排序，确保 FIFO
    df_paper = df_paper.sort_values(by='Trade Date').reset_index(drop=True)
    # 组合键：品种+合约月
    df_paper['Group_Key'] = df_paper['Std_Commodity'] + "_" + df_paper['Month']
    # 转字典记录加速
    records = df_paper.to_dict('records')
    groups = {}
    # 按组合键分组交易
    for i, row in enumerate(records):
        key = row['Group_Key']
        if key not in groups:
            groups[key] = []
        groups[key].append(i)
        if i % 100 == 0:
            progress_bar.progress(min(i / len(records) * 0.5, 0.5))
    
    st.info(f"数据分组完成，共 {len(groups)} 个组。")
    
    # 遍历每个组，进行FIFO平仓
    group_count = 0
    for key, indices in groups.items():
        open_queue = deque()
        for idx in indices:
            row = records[idx]
            current_vol = row.get('Volume', 0)
            # 初始化净开仓量和已平仓量
            records[idx]['Net_Open_Vol'] = current_vol
            records[idx]['Closed_Vol'] = 0
            records[idx]['Close_Events'] = []
            if abs(current_vol) < 0.0001:
                continue
            current_sign = 1 if current_vol > 0 else -1
            while open_queue:
                q_idx, q_vol, q_sign = open_queue[0]
                # 方向相反才能抵消
                if q_sign != current_sign:
                    offset = min(abs(current_vol), abs(q_vol))
                    # 更新当前交易和队列交易的剩余量
                    current_vol -= (current_sign * offset)
                    q_vol -= (q_sign * offset)
                    # 记录平仓事件到原交易
                    close_event = {
                        'Ref': str(records[idx].get('Recap No', '')),
                        'Date': records[idx].get('Trade Date'),
                        'Vol': offset,
                        'Price': records[idx].get('Price', 0)
                    }
                    records[q_idx]['Close_Events'].append(close_event)
                    records[q_idx]['Closed_Vol'] += offset
                    records[q_idx]['Net_Open_Vol'] = q_vol
                    records[idx]['Closed_Vol'] += offset
                    records[idx]['Net_Open_Vol'] = current_vol
                    if abs(q_vol) < 0.0001:
                        open_queue.popleft()
                    else:
                        open_queue[0] = (q_idx, q_vol, q_sign)
                    if abs(current_vol) < 0.0001:
                        break
                else:
                    break
            # 如果还有未抵消净额，入队
            if abs(current_vol) > 0.0001:
                open_queue.append((idx, current_vol, current_sign))
        group_count += 1
        progress_bar.progress(0.5 + (group_count / len(groups)) * 0.5)
    
    elapsed = time.time() - start_time
    progress_bar.progress(1.0)
    st.success(f"纸货内部对冲完成，耗时 {round(elapsed, 2)} 秒。")
    return pd.DataFrame(records)

# ---------------------------------------------------------
# 3. 匹配逻辑 (v19 开放式时间排序)
# ---------------------------------------------------------

def format_close_details(events):
    """整理平仓路径：返回字符串描述、加权平仓价格、平仓量。"""
    if not events:
        return "", 0, 0
    details = []
    total_vol = 0
    total_val = 0
    # 按日期排序平仓事件
    sorted_events = sorted(events, key=lambda x: x['Date'] if pd.notna(x['Date']) else pd.Timestamp.min)
    for e in sorted_events:
        d_str = e['Date'].strftime('%Y-%m-%d') if pd.notna(e['Date']) else 'N/A'
        p_str = f"@{e['Price']}" if pd.notna(e['Price']) else ""
        details.append(f"[{d_str} Tkt#{e['Ref']} Vol:{e['Vol']:.0f} {p_str}]")
        if pd.notna(e['Price']):
            total_vol += e['Vol']
            total_val += (e['Vol'] * e['Price'])
    weighted_close_price = (total_val / total_vol) if total_vol > 0 else 0
    return " -> ".join(details), weighted_close_price, total_vol

def auto_match_hedges(physical_df, paper_df):
    """实货匹配逻辑"""
    hedge_relations = []
    st.info("开始实货匹配...")
    progress_bar = st.progress(0)
    
    active_paper = paper_df.copy()
    active_paper['Allocated_To_Phy'] = 0.0
    active_paper['_original_index'] = active_paper.index
    
    df_phy = physical_df.copy()
    df_phy['_orig_idx'] = df_phy.index
    
    # 根据定价基准优先级对实货排序：BRENT 优先匹配
    if 'Pricing_Benchmark' in df_phy.columns:
        def bench_prio(x):
            x_str = str(x).upper()
            return 0 if 'BRENT' in x_str else 1
        df_phy['_priority'] = df_phy['Pricing_Benchmark'].apply(bench_prio)
        df_phy = df_phy.sort_values(by=['_priority', '_orig_idx']).reset_index(drop=True)
        df_phy = df_phy.drop(columns=['_priority'])
    else:
        df_phy = df_phy.reset_index(drop=True)
    
    total_cargos = len(df_phy)
    for idx, (_, cargo) in enumerate(df_phy.iterrows()):
        cargo_id = cargo.get('Cargo_ID')
        phy_vol = cargo.get('Unhedged_Volume', 0)
        if abs(phy_vol) < 0.0001:
            continue
            
        proxy = str(cargo.get('Hedge_Proxy', ''))
        target_month = cargo.get('Target_Contract_Month', None)
        phy_dir = cargo.get('Direction', 'Buy')
        desig_date = cargo.get('Designation_Date', pd.NaT)
        
        # 基础筛选: 品种、合约月
        candidates_df = active_paper[
            (active_paper['Std_Commodity'].str.contains(proxy, regex=False)) &
            (active_paper['Month'] == target_month)
        ].copy()
        
        if candidates_df.empty:
            continue
            
        # 如果有指定日期, 计算时间差绝对值
        if pd.notna(desig_date) and not candidates_df['Trade Date'].isnull().all():
            candidates_df['Time_Lag_Days'] = (candidates_df['Trade Date'] - desig_date).dt.days
            candidates_df['Abs_Lag'] = candidates_df['Time_Lag_Days'].abs()
            candidates_df = candidates_df.sort_values(by=['Abs_Lag', 'Trade Date'])
        else:
            candidates_df['Time_Lag_Days'] = np.nan
            candidates_df = candidates_df.sort_values(by='Trade Date')
        
        # 分配
        for _, ticket in candidates_df.iterrows():
            if abs(phy_vol) < 1:
                break
                
            original_index = ticket['_original_index']
            curr_allocated = active_paper.at[original_index, 'Allocated_To_Phy']
            curr_total_vol = ticket.get('Volume', 0)
            avail = curr_total_vol - curr_allocated
            
            if abs(avail) < 0.0001:
                continue
                
            alloc_amt_abs = abs(phy_vol) if abs(avail) >= abs(phy_vol) else abs(avail)
            alloc_amt = np.sign(avail) * alloc_amt_abs
            phy_vol -= alloc_amt_abs
            active_paper.at[original_index, 'Allocated_To_Phy'] += alloc_amt
            
            # 计算 P/L 和 MTM
            open_price = ticket.get('Price', 0)
            mtm_price = ticket.get('Mtm Price', 0)
            total_pl_raw = ticket.get('Total P/L', 0)
            close_events = ticket.get('Close_Events', [])
            close_path_str, avg_close_price, _ = format_close_details(close_events)
            unrealized_mtm = (mtm_price - open_price) * alloc_amt
            ratio = 0
            if abs(ticket.get('Volume', 0)) > 0:
                ratio = abs(alloc_amt) / abs(ticket['Volume'])
            allocated_total_pl = total_pl_raw * ratio
            
            hedge_relations.append({
                'Cargo_ID': cargo_id,
                'Proxy': proxy,
                'Designation_Date': desig_date.strftime('%Y-%m-%d') if pd.notna(desig_date) else '',
                'Open_Date': ticket.get('Trade Date'),
                'Time_Lag': ticket.get('Time_Lag_Days'),
                'Ticket_ID': ticket.get('Recap No'),
                'Month': ticket.get('Month'),
                'Allocated_Vol': alloc_amt,
                'Trade_Volume': ticket.get('Volume', 0),
                'Trade_Net_Open': ticket.get('Net_Open_Vol', 0),
                'Trade_Closed_Vol': ticket.get('Closed_Vol', 0),
                'Open_Price': open_price,
                'MTM_Price': mtm_price,
                'Alloc_Unrealized_MTM': round(unrealized_mtm, 2),
                'Alloc_Total_PL': round(allocated_total_pl, 2),
                'Close_Path_Details': close_path_str,
            })
            
            # 更新实货未对冲量
            orig_idx = cargo.get('_orig_idx')
            if orig_idx in physical_df.index:
                physical_df.at[orig_idx, 'Unhedged_Volume'] = phy_vol
        
        progress_bar.progress((idx + 1) / total_cargos)
    
    # 将分配量写回 paper_df
    cols_to_update = active_paper[['_original_index', 'Allocated_To_Phy']].set_index('_original_index')
    paper_df.update(cols_to_update)
    
    return pd.DataFrame(hedge_relations), physical_df

# ---------------------------------------------------------
# 4. Streamlit 主应用
# ---------------------------------------------------------

def main():
    st.set_page_config(
        page_title="实纸货套保匹配系统",
        page_icon="📊",
        layout="wide"
    )
    
    # 标题和介绍
    st.title("📈 实纸货套保匹配系统")
    st.markdown("""
    本系统用于执行实货与纸货的套保匹配，采用 FIFO 内部对冲算法和开放式时间排序匹配逻辑。
    """)
    
    # 文件上传区域
    st.sidebar.header("📁 数据上传")
    
    paper_file = st.sidebar.file_uploader(
        "上传纸货数据 (CSV/Excel)",
        type=["csv", "xlsx", "xls"],
        help="包含 Trade Date, Volume, Commodity, Month, Price 等字段"
    )
    
    physical_file = st.sidebar.file_uploader(
        "上传实货数据 (CSV/Excel)",
        type=["csv", "xlsx", "xls"],
        help="包含 Cargo_ID, Volume, Hedge_Proxy, Target_Contract_Month, Direction 等字段"
    )
    
    # 配置选项
    st.sidebar.header("⚙️ 配置选项")
    show_raw_data = st.sidebar.checkbox("显示原始数据", value=False)
    show_analysis = st.sidebar.checkbox("显示分析图表", value=True)
    
    if paper_file is not None and physical_file is not None:
        try:
            # 读取数据
            with st.spinner("正在读取数据..."):
                # 读取纸货数据
                if paper_file.name.endswith(('.xlsx', '.xls')):
                    df_paper = pd.read_excel(paper_file)
                else:
                    df_paper = pd.read_csv(paper_file)
                
                # 读取实货数据
                if physical_file.name.endswith(('.xlsx', '.xls')):
                    df_physical = pd.read_excel(physical_file)
                else:
                    df_physical = pd.read_csv(physical_file)
            
            # 显示数据预览
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📄 纸货数据预览")
                st.write(f"记录数: {len(df_paper)}")
                st.dataframe(df_paper.head(), use_container_width=True)
            
            with col2:
                st.subheader("📦 实货数据预览")
                st.write(f"记录数: {len(df_physical)}")
                st.dataframe(df_physical.head(), use_container_width=True)
            
            # 数据处理
            with st.spinner("正在处理数据..."):
                # 纸货数据预处理
                if 'Trade Date' in df_paper.columns:
                    df_paper['Trade Date'] = pd.to_datetime(df_paper['Trade Date'])
                if 'Volume' in df_paper.columns:
                    df_paper['Volume'] = pd.to_numeric(df_paper['Volume'], errors='coerce').fillna(0)
                if 'Commodity' in df_paper.columns:
                    df_paper['Std_Commodity'] = clean_str(df_paper['Commodity'])
                if 'Month' in df_paper.columns:
                    df_paper['Month'] = standardize_month_vectorized(df_paper['Month'])
                if 'Recap No' not in df_paper.columns:
                    df_paper['Recap No'] = df_paper.index.astype(str)
                
                # 实货数据预处理
                col_map = {'Target_Pricing_Month': 'Target_Contract_Month', 'Month': 'Target_Contract_Month'}
                df_physical.rename(columns=col_map, inplace=True)
                if 'Volume' in df_physical.columns:
                    df_physical['Volume'] = pd.to_numeric(df_physical['Volume'], errors='coerce').fillna(0)
                    df_physical['Unhedged_Volume'] = df_physical['Volume']
                if 'Hedge_Proxy' in df_physical.columns:
                    df_physical['Hedge_Proxy'] = clean_str(df_physical['Hedge_Proxy'])
                if 'Target_Contract_Month' in df_physical.columns:
                    df_physical['Target_Contract_Month'] = standardize_month_vectorized(df_physical['Target_Contract_Month'])
                
                # 指定日期处理
                if 'Designation_Date' in df_physical.columns:
                    df_physical['Designation_Date'] = pd.to_datetime(df_physical['Designation_Date'], errors='coerce')
                elif 'Pricing_Start' in df_physical.columns:
                    df_physical['Designation_Date'] = pd.to_datetime(df_physical['Pricing_Start'], errors='coerce')
                else:
                    df_physical['Designation_Date'] = pd.NaT
            
            # 执行匹配
            if st.button("🚀 开始套保匹配", type="primary"):
                with st.spinner("正在执行套保匹配..."):
                    # 1. 纸货内部对冲
                    df_paper_net = calculate_net_positions_corrected(df_paper)
                    
                    # 2. 实货匹配
                    df_relations, df_physical_updated = auto_match_hedges(df_physical, df_paper_net)
                    
                    # 显示结果
                    st.subheader("📊 匹配结果概览")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        total_matched = df_relations['Allocated_Vol'].abs().sum()
                        total_physical = df_physical['Volume'].abs().sum()
                        match_rate = (total_matched / total_physical * 100) if total_physical > 0 else 0
                        st.metric("匹配率", f"{match_rate:.1f}%")
                    
                    with col2:
                        st.metric("匹配交易数", len(df_relations))
                    
                    with col3:
                        total_pl = df_relations['Alloc_Total_PL'].sum()
                        st.metric("总P/L", f"${total_pl:,.2f}")
                    
                    # 显示匹配明细
                    st.subheader("📋 匹配明细")
                    st.dataframe(df_relations, use_container_width=True)
                    
                    # 分析图表
                    if show_analysis and not df_relations.empty:
                        st.subheader("📈 分析图表")
                        
                        tab1, tab2, tab3 = st.tabs(["匹配量分布", "P/L分布", "时间差分析"])
                        
                        with tab1:
                            # 按Cargo_ID的匹配量
                            cargo_summary = df_relations.groupby('Cargo_ID', as_index=False).agg(
                                Allocated_Vol=('Allocated_Vol', lambda series: series.abs().sum())
                            )
                            fig1 = px.bar(cargo_summary, x='Cargo_ID', y='Allocated_Vol',
                                         title='各Cargo_ID匹配量',
                                         labels={'Allocated_Vol': '匹配量', 'Cargo_ID': 'Cargo ID'})
                            st.plotly_chart(fig1, use_container_width=True)
                        
                        with tab2:
                            # P/L分布
                            fig2 = px.histogram(df_relations, x='Alloc_Total_PL',
                                               title='P/L分布直方图',
                                               labels={'Alloc_Total_PL': 'P/L值'})
                            st.plotly_chart(fig2, use_container_width=True)
                        
                        with tab3:
                            # 时间差分析
                            if 'Time_Lag' in df_relations.columns:
                                time_lag_data = df_relations['Time_Lag'].dropna()
                                if not time_lag_data.empty:
                                    fig3 = px.histogram(time_lag_data,
                                                       title='匹配时间差分布',
                                                       labels={'value': '时间差(天)'})
                                    st.plotly_chart(fig3, use_container_width=True)
                    
                    # 下载结果
                    st.subheader("💾 下载结果")
                    csv = df_relations.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="下载匹配结果CSV",
                        data=csv,
                        file_name="hedge_matching_results.csv",
                        mime="text/csv"
                    )
                    
                    # 显示原始数据（如果选择）
                    if show_raw_data:
                        with st.expander("查看处理后数据"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write("纸货数据（处理后）")
                                st.dataframe(df_paper_net.head(20), use_container_width=True)
                            with col2:
                                st.write("实货数据（更新后）")
                                st.dataframe(df_physical_updated.head(20), use_container_width=True)
        
        except Exception as e:
            st.error(f"处理过程中出现错误: {str(e)}")
            st.exception(e)
    
    else:
        # 显示使用说明
        st.info("👈 请在左侧上传纸货和实货数据文件开始匹配")
        
        with st.expander("📖 使用说明"):
            st.markdown("""
            ### 数据格式要求
            
            #### 纸货数据（必填字段）:
            - **Trade Date**: 交易日期
            - **Volume**: 交易量（正数表示买入，负数表示卖出）
            - **Commodity**: 商品品种
            - **Month**: 合约月份
            - **Price**: 价格
            
            #### 实货数据（必填字段）:
            - **Cargo_ID**: 实货编号
            - **Volume**: 实货量
            - **Hedge_Proxy**: 套保代理（与纸货Commodity匹配）
            - **Target_Contract_Month**: 目标合约月份
            - **Direction**: 方向（Buy/Sell）
            
            ### 匹配算法说明
            
            1. **内部对冲**: 先对纸货进行FIFO内部对冲，减少冗余头寸
            2. **时间优先匹配**: 根据指定日期（Designation_Date）的时间差进行匹配
            3. **BRENT优先**: BRENT基准的实货优先匹配
            4. **开放式分配**: 允许同一纸货交易匹配给多个实货
            
            ### 输出结果
            
            - 匹配明细表
            - 匹配率统计
            - P/L分析
            - 可下载的CSV结果文件
            """)

if __name__ == "__main__":
    main()
