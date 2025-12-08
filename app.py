import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys
import tempfile

# ==============================================================================
# Streamlit 应用界面
# ==============================================================================

st.set_page_config(page_title="Hedge Master Analytics", page_icon="📈", layout="wide")

# CSS 样式
st.markdown("""
<style>
    .stDataFrame { 
        border: 1px solid #ddd; 
        border-radius: 5px; 
        font-size: 14px;
    }
    .metric-card { 
        background-color: #f8f9fa; 
        padding: 15px; 
        border-radius: 8px; 
        margin-bottom: 10px;
        border-left: 4px solid #4e73df;
    }
    .header-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        margin-bottom: 20px;
    }
    .success-message {
        background-color: #d4edda;
        border-color: #c3e6cb;
        color: #155724;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .warning-message {
        background-color: #fff3cd;
        border-color: #ffeaa7;
        color: #856404;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .error-message {
        background-color: #f8d7da;
        border-color: #f5c6cb;
        color: #721c24;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# 标题区域
st.markdown('<div class="header-card">', unsafe_allow_html=True)
st.title("🛡️ Hedge Master Analytics")
st.markdown("**基于 v19 引擎的智能套保有效性分析系统**")
st.caption("Version: 2.0 | 支持开放式时间匹配算法")
st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 修复的数据预处理函数
# ==============================================================================

def preprocess_paper_data(df_paper):
    """预处理纸货数据，确保包含引擎所需的所有列"""
    
    # 创建副本
    df = df_paper.copy()
    
    # 1. 确保有 Trade Date 列
    if 'Trade Date' not in df.columns:
        # 尝试找到日期列
        date_cols = [col for col in df.columns if 'date' in col.lower() or '日期' in col]
        if date_cols:
            df['Trade Date'] = pd.to_datetime(df[date_cols[0]], errors='coerce')
        else:
            df['Trade Date'] = pd.NaT
    
    # 2. 确保有 Volume 列
    if 'Volume' not in df.columns:
        # 尝试找到数量列
        vol_cols = [col for col in df.columns if 'vol' in col.lower() or '数量' in col or 'volume' in col.lower()]
        if vol_cols:
            df['Volume'] = pd.to_numeric(df[vol_cols[0]], errors='coerce').fillna(0)
        else:
            df['Volume'] = 0
    
    # 3. 确保有 Commodity 列
    if 'Commodity' not in df.columns:
        # 尝试找到品种列
        comm_cols = [col for col in df.columns if 'commodity' in col.lower() or '品种' in col or 'product' in col.lower()]
        if comm_cols:
            df['Commodity'] = df[comm_cols[0]].astype(str)
        else:
            df['Commodity'] = 'UNKNOWN'
    
    # 4. 确保有 Month 列
    if 'Month' not in df.columns:
        # 尝试找到月份列
        month_cols = [col for col in df.columns if 'month' in col.lower() or '月份' in col or '合约' in col]
        if month_cols:
            df['Month'] = df[month_cols[0]].astype(str)
        else:
            df['Month'] = ''
    
    # 5. 确保有 Price 列
    if 'Price' not in df.columns:
        # 尝试找到价格列
        price_cols = [col for col in df.columns if 'price' in col.lower() or '价格' in col or 'price' in col.lower()]
        if price_cols:
            df['Price'] = pd.to_numeric(df[price_cols[0]], errors='coerce').fillna(0)
        else:
            df['Price'] = 0
    
    # 6. 创建 Std_Commodity 列（引擎必需）
    df['Std_Commodity'] = df['Commodity'].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', 'NULL', ''], 'UNKNOWN')
    
    # 7. 创建 Recap No 列（引擎必需）
    if 'Recap No' not in df.columns:
        df['Recap No'] = df.index.astype(str)
    
    # 8. 其他引擎需要的列
    df['_original_index'] = df.index
    
    # 9. 初始化缺失金融字段
    for col in ['Mtm Price', 'Total P/L']:
        if col not in df.columns:
            df[col] = 0
    
    return df

def preprocess_physical_data(df_physical):
    """预处理实货数据，确保包含引擎所需的所有列"""
    
    # 创建副本
    df = df_physical.copy()
    
    # 1. 确保有 Cargo_ID 列
    if 'Cargo_ID' not in df.columns:
        # 尝试找到ID列
        id_cols = [col for col in df.columns if 'id' in col.lower() or '编号' in col or 'cargo' in col.lower()]
        if id_cols:
            df['Cargo_ID'] = df[id_cols[0]].astype(str)
        else:
            df['Cargo_ID'] = df.index.astype(str)
    
    # 2. 确保有 Volume 列
    if 'Volume' not in df.columns:
        # 尝试找到数量列
        vol_cols = [col for col in df.columns if 'vol' in col.lower() or '数量' in col or 'volume' in col.lower()]
        if vol_cols:
            df['Volume'] = pd.to_numeric(df[vol_cols[0]], errors='coerce').fillna(0)
        else:
            df['Volume'] = 0
    
    # 3. 确保有 Hedge_Proxy 列
    if 'Hedge_Proxy' not in df.columns:
        # 尝试找到对冲品种列
        proxy_cols = [col for col in df.columns if 'proxy' in col.lower() or '对冲' in col or '品种' in col]
        if proxy_cols:
            df['Hedge_Proxy'] = df[proxy_cols[0]].astype(str)
        else:
            df['Hedge_Proxy'] = 'UNKNOWN'
    
    # 4. 确保有 Target_Contract_Month 列
    if 'Target_Contract_Month' not in df.columns:
        # 尝试找到目标合约月列
        target_cols = [col for col in df.columns if 'target' in col.lower() or 'month' in col.lower() or '合约' in col or '月份' in col]
        if target_cols:
            df['Target_Contract_Month'] = df[target_cols[0]].astype(str)
        else:
            df['Target_Contract_Month'] = ''
    
    # 5. 确保有 Direction 列
    if 'Direction' not in df.columns:
        df['Direction'] = 'Buy'  # 默认值
    
    # 6. 初始化 Unhedged_Volume
    df['Unhedged_Volume'] = df['Volume']
    
    # 7. 清理 Hedge_Proxy
    df['Hedge_Proxy'] = df['Hedge_Proxy'].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', 'NULL', ''], 'UNKNOWN')
    
    # 8. 指定日期列
    if 'Designation_Date' not in df.columns:
        # 尝试找到日期列
        date_cols = [col for col in df.columns if 'date' in col.lower() or '日期' in col or 'pricing' in col.lower()]
        if date_cols:
            df['Designation_Date'] = pd.to_datetime(df[date_cols[0]], errors='coerce')
        else:
            df['Designation_Date'] = pd.NaT
    
    return df

def read_file_smart(file_content, file_name):
    """智能读取文件"""
    file_name_lower = file_name.lower()
    
    try:
        if file_name_lower.endswith(('.xlsx', '.xls')):
            # 读取Excel
            return pd.read_excel(io.BytesIO(file_content))
        else:
            # 尝试读取CSV，使用多种编码
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1']
            for enc in encodings:
                try:
                    return pd.read_csv(io.BytesIO(file_content), encoding=enc)
                except:
                    continue
            # 最后尝试
            return pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
    except Exception as e:
        st.error(f"读取文件失败: {str(e)}")
        raise

# ==============================================================================
# 引擎包装函数
# ==============================================================================

def run_hedge_engine(paper_content, paper_name, phys_content, phys_name):
    """运行对冲引擎"""
    try:
        # 导入引擎
        sys.path.append(os.path.dirname(__file__))
        import hedge_engine as engine
        
        # 读取原始数据
        df_paper_raw = read_file_smart(paper_content, paper_name)
        df_physical_raw = read_file_smart(phys_content, phys_name)
        
        # 在侧边栏显示原始数据信息
        with st.sidebar.expander("📊 原始数据信息"):
            st.write("**纸货数据:**")
            st.write(f"- 行数: {len(df_paper_raw)}")
            st.write(f"- 列数: {len(df_paper_raw.columns)}")
            st.write(f"- 列名: {list(df_paper_raw.columns)[:10]}")
            
            st.write("**实货数据:**")
            st.write(f"- 行数: {len(df_physical_raw)}")
            st.write(f"- 列数: {len(df_physical_raw.columns)}")
            st.write(f"- 列名: {list(df_physical_raw.columns)[:10]}")
        
        # 预处理数据
        df_paper = preprocess_paper_data(df_paper_raw)
        df_physical = preprocess_physical_data(df_physical_raw)
        
        # 显示预处理后的数据信息
        with st.sidebar.expander("🔄 预处理后数据"):
            st.write("**纸货关键列:**")
            paper_key_cols = ['Trade Date', 'Volume', 'Commodity', 'Month', 'Price', 'Std_Commodity']
            for col in paper_key_cols:
                if col in df_paper.columns:
                    st.write(f"- ✓ {col}")
                else:
                    st.write(f"- ✗ {col} (缺失)")
            
            st.write("**实货关键列:**")
            phys_key_cols = ['Cargo_ID', 'Volume', 'Hedge_Proxy', 'Target_Contract_Month', 'Unhedged_Volume']
            for col in phys_key_cols:
                if col in df_physical.columns:
                    st.write(f"- ✓ {col}")
                else:
                    st.write(f"- ✗ {col} (缺失)")
        
        # 运行引擎核心函数
        if not df_physical.empty:
            # Step 1: 净仓计算
            df_paper_net = engine.calculate_net_positions_corrected(df_paper)
            
            # Step 2: 实货匹配
            df_rels, df_physical_updated = engine.auto_match_hedges(df_physical, df_paper_net)
            
            # Step 3: 准备纸货最终数据
            df_paper_final = df_paper_net.copy()
            
            return df_rels, df_physical_updated, df_paper_final
        else:
            return pd.DataFrame(), df_physical, df_paper
            
    except Exception as e:
        raise e

# ==============================================================================
# 侧边栏
# ==============================================================================

with st.sidebar:
    st.header("📂 数据接入")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("引擎状态", "就绪", "✓")
    with col2:
        st.metric("版本", "v19", "")
    
    st.markdown("---")
    
    ticket_file = st.file_uploader(
        "📄 上传纸货水单", 
        type=['xlsx', 'csv', 'xls'],
        help="支持 CSV 或 Excel 格式的纸货交易数据"
    )
    
    phys_file = st.file_uploader(
        "📦 上传实货台账", 
        type=['xlsx', 'csv', 'xls'],
        help="支持 CSV 或 Excel 格式的实货数据"
    )
    
    st.markdown("---")
    
    if ticket_file:
        st.info(f"📄 纸货文件: {ticket_file.name}")
    
    if phys_file:
        st.info(f"📦 实货文件: {phys_file.name}")
    
    st.markdown("---")
    
    # 调试选项
    debug_mode = st.checkbox("调试模式", value=False)
    
    st.markdown("---")
    
    run_btn = st.button(
        "🚀 开始全景分析", 
        type="primary", 
        use_container_width=True,
        disabled=not (ticket_file and phys_file)
    )
    
    if not (ticket_file and phys_file):
        st.warning("请先上传两个文件")

# ==============================================================================
# 主内容区域
# ==============================================================================

if run_btn and ticket_file and phys_file:
    with st.spinner('正在执行匹配运算...'):
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 步骤1: 准备数据
            status_text.text("步骤 1/3: 读取和预处理数据...")
            progress_bar.progress(30)
            
            # 获取文件内容
            paper_content = ticket_file.getvalue()
            paper_name = ticket_file.name
            phys_content = phys_file.getvalue()
            phys_name = phys_file.name
            
            # 步骤2: 运行引擎
            status_text.text("步骤 2/3: 执行套保匹配引擎...")
            progress_bar.progress(60)
            
            start_t = time.time()
            
            # 运行引擎
            df_rels, df_ph_final, df_p_final = run_hedge_engine(
                paper_content, paper_name, phys_content, phys_name
            )
            
            calc_time = time.time() - start_t
            
            # 步骤3: 显示结果
            status_text.text("步骤 3/3: 生成分析报告...")
            progress_bar.progress(90)
            
            progress_bar.progress(100)
            status_text.text("✅ 分析完成！")
            
            st.markdown(f'<div class="success-message">分析完成！耗时 {calc_time:.2f} 秒</div>', unsafe_allow_html=True)
            
            # --- 显示结果 ---
            st.markdown("## 📊 分析结果")
            
            if not df_rels.empty:
                st.success(f"✅ 成功匹配 {len(df_rels)} 笔交易")
                
                # 显示关键指标
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if 'Allocated_Vol' in df_rels.columns:
                        total = df_rels['Allocated_Vol'].abs().sum()
                        st.metric("总匹配量", f"{total:,.0f} BBL")
                
                with col2:
                    if 'Proxy' in df_rels.columns:
                        unique = df_rels['Proxy'].nunique()
                        st.metric("涉及品种", unique)
                
                with col3:
                    if 'Month' in df_rels.columns:
                        unique = df_rels['Month'].nunique()
                        st.metric("涉及合约月", unique)
                
                with col4:
                    if 'Alloc_Unrealized_MTM' in df_rels.columns:
                        total_mtm = df_rels['Alloc_Unrealized_MTM'].sum()
                        st.metric("总MTM", f"${total_mtm:,.0f}")
                
                # 显示匹配结果
                st.markdown("### 📋 匹配明细")
                st.dataframe(df_rels, use_container_width=True)
                
                # 下载按钮
                csv = df_rels.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 下载匹配明细 CSV",
                    data=csv,
                    file_name="hedge_allocation_details.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # 显示匹配统计图表
                st.markdown("### 📈 匹配统计")
                
                if 'Proxy' in df_rels.columns and 'Allocated_Vol' in df_rels.columns:
                    proxy_summary = df_rels.groupby('Proxy')['Allocated_Vol'].abs().sum().reset_index()
                    proxy_summary = proxy_summary.sort_values('Allocated_Vol', ascending=False)
                    
                    fig1 = px.bar(proxy_summary, x='Proxy', y='Allocated_Vol',
                                 title="各品种匹配量",
                                 color='Proxy')
                    st.plotly_chart(fig1, use_container_width=True)
                
                if 'Month' in df_rels.columns and 'Allocated_Vol' in df_rels.columns:
                    month_summary = df_rels.groupby('Month')['Allocated_Vol'].abs().sum().reset_index()
                    month_summary = month_summary.sort_values('Month')
                    
                    fig2 = px.bar(month_summary, x='Month', y='Allocated_Vol',
                                 title="各合约月匹配量",
                                 color='Month')
                    st.plotly_chart(fig2, use_container_width=True)
                
            else:
                st.warning("⚠️ 未找到匹配结果")
                
                # 显示详细诊断信息
                if debug_mode:
                    st.markdown("## 🔍 详细诊断")
                    
                    # 重新读取原始数据
                    df_paper_raw = read_file_smart(paper_content, paper_name)
                    df_physical_raw = read_file_smart(phys_content, phys_name)
                    
                    # 显示原始数据
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("📄 原始纸货数据")
                        st.write("前5行:")
                        st.dataframe(df_paper_raw.head(), use_container_width=True)
                        
                        st.write("数据统计:")
                        st.write(f"- 总行数: {len(df_paper_raw)}")
                        st.write(f"- 列数: {len(df_paper_raw.columns)}")
                        if 'Commodity' in df_paper_raw.columns:
                            st.write(f"- 品种数: {df_paper_raw['Commodity'].nunique()}")
                            st.write(f"- 品种列表: {list(df_paper_raw['Commodity'].unique())[:10]}")
                    
                    with col2:
                        st.subheader("📦 原始实货数据")
                        st.write("前5行:")
                        st.dataframe(df_physical_raw.head(), use_container_width=True)
                        
                        st.write("数据统计:")
                        st.write(f"- 总行数: {len(df_physical_raw)}")
                        st.write(f"- 列数: {len(df_physical_raw.columns)}")
                        if 'Hedge_Proxy' in df_physical_raw.columns:
                            st.write(f"- 对冲品种数: {df_physical_raw['Hedge_Proxy'].nunique()}")
                            st.write(f"- 对冲品种列表: {list(df_physical_raw['Hedge_Proxy'].unique())[:10]}")
                    
                    # 匹配可能性分析
                    st.markdown("### 🔧 匹配可能性分析")
                    
                    if 'Commodity' in df_paper_raw.columns and 'Hedge_Proxy' in df_physical_raw.columns:
                        paper_commodities = set(str(x).upper().strip() for x in df_paper_raw['Commodity'].dropna().unique())
                        phys_proxies = set(str(x).upper().strip() for x in df_physical_raw['Hedge_Proxy'].dropna().unique())
                        
                        st.write(f"纸货品种数: {len(paper_commodities)}")
                        st.write(f"实货对冲品种数: {len(phys_proxies)}")
                        
                        common = paper_commodities.intersection(phys_proxies)
                        
                        if common:
                            st.success(f"✅ 找到 {len(common)} 个共同品种")
                            st.write(f"共同品种: {list(common)}")
                        else:
                            st.error("❌ 没有共同品种！")
                            st.write(f"纸货品种: {list(paper_commodities)}")
                            st.write(f"实货对冲品种: {list(phys_proxies)}")
                    
                    # 数据质量检查
                    st.markdown("### 📊 数据质量检查")
                    
                    check_col1, check_col2 = st.columns(2)
                    
                    with check_col1:
                        st.write("**纸货数据检查:**")
                        if 'Volume' in df_paper_raw.columns:
                            zero_volume = (df_paper_raw['Volume'] == 0).sum()
                            st.write(f"- 零数量交易: {zero_volume}")
                        
                        if 'Commodity' in df_paper_raw.columns:
                            empty_commodity = df_paper_raw['Commodity'].isna().sum()
                            st.write(f"- 空品种: {empty_commodity}")
                    
                    with check_col2:
                        st.write("**实货数据检查:**")
                        if 'Volume' in df_physical_raw.columns:
                            zero_volume = (df_physical_raw['Volume'] == 0).sum()
                            st.write(f"- 零数量实货: {zero_volume}")
                        
                        if 'Hedge_Proxy' in df_physical_raw.columns:
                            empty_proxy = df_physical_raw['Hedge_Proxy'].isna().sum()
                            st.write(f"- 空对冲品种: {empty_proxy}")
            
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            
            # 显示详细的错误信息
            with st.expander("🔍 查看详细错误信息"):
                import traceback
                st.code(traceback.format_exc())
            
            st.info("💡 解决方案:")
            st.markdown("""
            1. **检查文件格式**: 确保上传的是正确的Excel或CSV文件
            2. **检查列名**: 确保文件包含必要的列名
            3. **检查数据**: 确保数据格式正确，没有空值
            4. **联系支持**: 如果问题持续，请提供文件样本以便调试
            """)
else:
    # 显示欢迎界面
    st.markdown("""
    ## 👋 欢迎使用 Hedge Master Analytics
    
    ### 🚀 快速开始
    
    1. **上传数据**: 在左侧上传纸货水单和实货台账
    2. **开始分析**: 点击"开始全景分析"按钮
    3. **查看结果**: 系统将自动计算匹配结果
    
    ### 📁 支持的文件格式
    
    - **纸货水单**: Excel (.xlsx, .xls), CSV
    - **实货台账**: Excel (.xlsx, .xls), CSV
    
    ### 📋 必需的列名（或类似列名）
    
    **纸货文件**:
    - `Trade Date` (或包含"date"的列)
    - `Commodity` (或包含"commodity"、"品种"的列)
    - `Month` (或包含"month"、"月份"的列)
    - `Volume` (或包含"volume"、"数量"的列)
    
    **实货文件**:
    - `Cargo_ID` (或包含"id"、"编号"的列)
    - `Volume` (或包含"volume"、"数量"的列)
    - `Hedge_Proxy` (或包含"proxy"、"对冲"、"品种"的列)
    - `Target_Contract_Month` (或包含"target"、"month"、"合约"的列)
    
    ### ⚙️ 系统特性
    
    - **智能列名识别**: 系统会自动识别常见的中英文列名
    - **数据预处理**: 自动处理缺失值和格式问题
    - **详细调试**: 开启调试模式查看详细处理过程
    """)

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    <p>Hedge Master Analytics v2.0 | 基于 v19 套保引擎</p>
</div>
""", unsafe_allow_html=True)
