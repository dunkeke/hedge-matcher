import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys
import tempfile
import importlib

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

# 侧边栏
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
    
    # 显示文件信息
    if ticket_file:
        st.info(f"📄 纸货文件: {ticket_file.name} ({ticket_file.size:,} bytes)")
    
    if phys_file:
        st.info(f"📦 实货文件: {phys_file.name} ({phys_file.size:,} bytes)")
    
    st.markdown("---")
    
    # 分析选项
    st.subheader("⚙️ 分析选项")
    show_detailed_logs = st.checkbox("显示详细日志", value=True)
    
    st.markdown("---")
    
    run_btn = st.button(
        "🚀 开始全景分析", 
        type="primary", 
        use_container_width=True,
        disabled=not (ticket_file and phys_file)
    )
    
    if not (ticket_file and phys_file):
        st.warning("请先上传两个文件")
    
    st.caption("Engine: v19 Logic with FIFO Netting")

# 主内容区域
if run_btn and ticket_file and phys_file:
    with st.spinner('正在执行匹配运算...'):
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 步骤1: 保存文件到临时位置
            status_text.text("步骤 1/3: 准备数据文件...")
            progress_bar.progress(20)
            
            # 创建临时目录
            temp_dir = tempfile.mkdtemp()
            paper_path = os.path.join(temp_dir, "paper_data.csv")
            phys_path = os.path.join(temp_dir, "phys_data.csv")
            
            # 保存上传的文件（保持原始格式）
            with open(paper_path, "wb") as f:
                f.write(ticket_file.getvalue())
            
            with open(phys_path, "wb") as f:
                f.write(phys_file.getvalue())
            
            # 步骤2: 运行原始引擎
            status_text.text("步骤 2/3: 执行套保匹配引擎...")
            progress_bar.progress(50)
            
            start_t = time.time()
            
            # 动态导入引擎模块
            sys.path.append(os.path.dirname(__file__))
            
            # 尝试不同的导入方式
            try:
                # 方法1: 直接导入
                import hedge_engine as engine
                
                # 检查是否有main函数
                if hasattr(engine, 'main'):
                    # 运行main函数
                    engine.main(paper_path, phys_path)
                else:
                    # 方法2: 手动调用引擎函数
                    st.info("使用手动调用引擎函数...")
                    
                    # 加载数据
                    df_paper, df_physical = engine.load_data_v19(paper_path, phys_path)
                    
                    if not df_physical.empty:
                        # 先内部净额化纸货
                        df_paper_net = engine.calculate_net_positions_corrected(df_paper)
                        # 实货匹配
                        df_rels, df_physical_updated = engine.auto_match_hedges(df_physical, df_paper_net)
                        
                        # 导出结果
                        engine.export_results(df_rels)
                    else:
                        st.warning("实货文件为空")
                        
            except ImportError as e:
                st.error(f"无法导入引擎模块: {e}")
                st.stop()
            
            calc_time = time.time() - start_t
            
            # 步骤3: 读取和分析结果
            status_text.text("步骤 3/3: 生成分析报告...")
            progress_bar.progress(90)
            
            # 检查输出文件
            output_files = [
                "hedge_allocation_v19_optimized.csv",
                "hedge_allocation_details.csv",
                os.path.join(temp_dir, "output.csv")
            ]
            
            df_rels = pd.DataFrame()
            output_file_path = None
            
            for file_path in output_files:
                if os.path.exists(file_path):
                    df_rels = pd.read_csv(file_path)
                    output_file_path = file_path
                    break
            
            # 重新加载原始数据用于分析
            ticket_file.seek(0)
            phys_file.seek(0)
            
            # 读取原始数据用于展示
            if ticket_file.name.lower().endswith(('.xlsx', '.xls')):
                df_p_original = pd.read_excel(ticket_file)
            else:
                df_p_original = pd.read_csv(ticket_file)
            
            if phys_file.name.lower().endswith(('.xlsx', '.xls')):
                df_ph_original = pd.read_excel(phys_file)
            else:
                df_ph_original = pd.read_csv(phys_file)
            
            progress_bar.progress(100)
            status_text.text("✅ 分析完成！")
            
            st.markdown(f'<div class="success-message">分析完成！耗时 {calc_time:.2f} 秒</div>', unsafe_allow_html=True)
            
            # --- 显示原始引擎输出 ---
            st.markdown("## 📊 引擎输出结果")
            
            if not df_rels.empty:
                st.success(f"✅ 成功匹配 {len(df_rels)} 笔交易")
                
                # 显示关键指标
                if 'Allocated_Vol' in df_rels.columns:
                    total_allocated = df_rels['Allocated_Vol'].abs().sum()
                    st.metric("总匹配量", f"{total_allocated:,.0f} BBL")
                
                # 显示匹配结果
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
                
                # 显示匹配统计
                st.markdown("### 📈 匹配统计")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    if 'Proxy' in df_rels.columns:
                        unique_proxies = df_rels['Proxy'].nunique()
                        st.metric("涉及品种", unique_proxies)
                
                with col2:
                    if 'Month' in df_rels.columns:
                        unique_months = df_rels['Month'].nunique()
                        st.metric("涉及合约月", unique_months)
                
                with col3:
                    if 'Alloc_Unrealized_MTM' in df_rels.columns:
                        total_mtm = df_rels['Alloc_Unrealized_MTM'].sum()
                        st.metric("总MTM", f"${total_mtm:,.0f}")
                
                with col4:
                    if 'Alloc_Total_PL' in df_rels.columns:
                        total_pl = df_rels['Alloc_Total_PL'].sum()
                        st.metric("总P/L", f"${total_pl:,.0f}")
                
            else:
                st.warning("⚠️ 引擎未产生匹配结果")
                
                # 显示数据预览以帮助调试
                st.markdown("## 🔍 数据预览与调试")
                
                tab1, tab2, tab3 = st.tabs(["📄 纸货数据", "📦 实货数据", "🔧 匹配诊断"])
                
                with tab1:
                    st.subheader("纸货数据预览")
                    st.write(f"数据形状: {df_p_original.shape}")
                    st.write("前10行数据:")
                    st.dataframe(df_p_original.head(10), use_container_width=True)
                    
                    # 显示关键列
                    st.subheader("关键列检查")
                    required_cols = ['Trade Date', 'Commodity', 'Month', 'Volume', 'Price']
                    
                    # 尝试查找列名（不区分大小写）
                    col_mapping = {}
                    available_cols = list(df_p_original.columns)
                    
                    for req_col in required_cols:
                        found = False
                        # 精确匹配
                        if req_col in available_cols:
                            col_mapping[req_col] = req_col
                            found = True
                        else:
                            # 尝试不区分大小写匹配
                            req_lower = req_col.lower()
                            for avail_col in available_cols:
                                if avail_col.lower() == req_lower:
                                    col_mapping[req_col] = avail_col
                                    found = True
                                    break
                        
                        if not found:
                            st.error(f"缺失列: {req_col}")
                    
                    if len(col_mapping) == len(required_cols):
                        st.success("所有关键列都存在（或通过映射找到）")
                        st.write("列映射:", col_mapping)
                        
                        # 显示数据摘要
                        st.subheader("数据摘要")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("总交易数", len(df_p_original))
                        with col2:
                            vol_col = col_mapping.get('Volume', 'Volume')
                            if vol_col in df_p_original.columns:
                                total_volume = df_p_original[vol_col].sum()
                                st.metric("总交易量", f"{total_volume:,.0f} BBL")
                        with col3:
                            month_col = col_mapping.get('Month', 'Month')
                            if month_col in df_p_original.columns:
                                unique_months = df_p_original[month_col].nunique()
                                st.metric("合约月份数", unique_months)
                                
                                # 显示月份分布
                                st.write("月份分布:")
                                month_counts = df_p_original[month_col].value_counts().head(10)
                                st.dataframe(month_counts)
                
                with tab2:
                    st.subheader("实货数据预览")
                    st.write(f"数据形状: {df_ph_original.shape}")
                    st.write("前10行数据:")
                    st.dataframe(df_ph_original.head(10), use_container_width=True)
                    
                    # 显示关键列
                    st.subheader("关键列检查")
                    required_cols = ['Cargo_ID', 'Volume', 'Hedge_Proxy', 'Target_Contract_Month']
                    
                    # 尝试查找列名（不区分大小写）
                    col_mapping = {}
                    available_cols = list(df_ph_original.columns)
                    
                    for req_col in required_cols:
                        found = False
                        # 精确匹配
                        if req_col in available_cols:
                            col_mapping[req_col] = req_col
                            found = True
                        else:
                            # 尝试不区分大小写匹配
                            req_lower = req_col.lower()
                            for avail_col in available_cols:
                                if avail_col.lower() == req_lower:
                                    col_mapping[req_col] = avail_col
                                    found = True
                                    break
                        
                        if not found:
                            st.error(f"缺失列: {req_col}")
                    
                    if len(col_mapping) >= 3:  # 至少需要大部分关键列
                        st.success("关键列检查通过")
                        st.write("列映射:", col_mapping)
                        
                        # 显示数据摘要
                        st.subheader("数据摘要")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("实货笔数", len(df_ph_original))
                        with col2:
                            vol_col = col_mapping.get('Volume', 'Volume')
                            if vol_col in df_ph_original.columns:
                                total_volume = df_ph_original[vol_col].sum()
                                st.metric("总敞口", f"{total_volume:,.0f} BBL")
                        with col3:
                            proxy_col = col_mapping.get('Hedge_Proxy', 'Hedge_Proxy')
                            if proxy_col in df_ph_original.columns:
                                unique_proxies = df_ph_original[proxy_col].nunique()
                                st.metric("对冲品种数", unique_proxies)
                                
                                # 显示品种分布
                                st.write("品种分布:")
                                proxy_counts = df_ph_original[proxy_col].value_counts().head(10)
                                st.dataframe(proxy_counts)
                
                with tab3:
                    st.subheader("匹配诊断")
                    st.markdown("""
                    ### 可能的原因:
                    
                    1. **品种不匹配**: 纸货的 `Commodity` 和实货的 `Hedge_Proxy` 不一致
                    2. **月份不匹配**: 纸货的 `Month` 和实货的 `Target_Contract_Month` 不一致
                    3. **数据格式问题**: 日期或数字格式不正确
                    4. **方向不匹配**: 买卖方向不一致
                    
                    ### 解决方案:
                    
                    1. **检查品种名称**: 确保大小写一致（引擎会自动转换为大写）
                    2. **检查月份格式**: 确保都是标准格式如 `JAN 24`
                    3. **检查数据完整性**: 确保没有空值或错误数据
                    4. **检查文件编码**: 确保文件编码正确
                    """)
                    
                    # 提供数据修正建议
                    st.subheader("数据修正建议")
                    
                    if 'Commodity' in df_p_original.columns and 'Hedge_Proxy' in df_ph_original.columns:
                        paper_commodities = df_p_original['Commodity'].unique()
                        phys_proxies = df_ph_original['Hedge_Proxy'].unique()
                        
                        st.write("纸货品种:", paper_commodities[:10])
                        st.write("实货对冲品种:", phys_proxies[:10])
                        
                        # 检查是否有交集
                        paper_set = set(str(x).upper().strip() for x in paper_commodities)
                        phys_set = set(str(x).upper().strip() for x in phys_proxies)
                        intersection = paper_set.intersection(phys_set)
                        
                        if intersection:
                            st.success(f"找到 {len(intersection)} 个共同品种: {list(intersection)[:5]}")
                        else:
                            st.error("没有找到共同的品种！")
            
            # --- 清理临时文件 ---
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
            
            # --- 显示调试信息 ---
            if show_detailed_logs:
                with st.expander("📋 查看详细日志"):
                    st.markdown("### 执行日志")
                    st.markdown(f"""
                    - 临时文件目录: {temp_dir}
                    - 纸货文件: {paper_path}
                    - 实货文件: {phys_path}
                    - 输出文件: {output_file_path if output_file_path else '未找到'}
                    - 执行时间: {calc_time:.2f}秒
                    - 匹配记录数: {len(df_rels)}
                    """)
                    
                    if not df_rels.empty:
                        st.markdown("### 匹配结果摘要")
                        if 'Allocated_Vol' in df_rels.columns:
                            st.write(f"总匹配量: {df_rels['Allocated_Vol'].abs().sum():,.0f} BBL")
                        
                        if 'Open_Price' in df_rels.columns and 'MTM_Price' in df_rels.columns:
                            avg_open = df_rels['Open_Price'].mean()
                            avg_mtm = df_rels['MTM_Price'].mean()
                            st.write(f"平均开仓价: ${avg_open:.2f}")
                            st.write(f"平均MTM价: ${avg_mtm:.2f}")
                
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            st.markdown('<div class="error-message">错误详情:</div>', unsafe_allow_html=True)
            import traceback
            st.code(traceback.format_exc())
            
            st.info("💡 调试建议:")
            st.markdown("""
            1. 检查上传文件格式是否正确
            2. 确保文件包含引擎需要的列名
            3. 尝试在本地运行原始引擎检查是否工作
            4. 检查数据中是否有空值或格式错误
            """)
            
            # 显示文件预览
            with st.expander("🔍 查看上传文件预览"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("纸货文件预览")
                    try:
                        ticket_file.seek(0)
                        if ticket_file.name.lower().endswith(('.xlsx', '.xls')):
                            preview_df = pd.read_excel(ticket_file, nrows=5)
                        else:
                            ticket_file.seek(0)
                            preview_df = pd.read_csv(ticket_file, nrows=5)
                        st.write(f"形状: {preview_df.shape}")
                        st.write("列名:", list(preview_df.columns))
                        st.dataframe(preview_df)
                    except Exception as e:
                        st.error(f"无法预览: {str(e)}")
                
                with col2:
                    st.subheader("实货文件预览")
                    try:
                        phys_file.seek(0)
                        if phys_file.name.lower().endswith(('.xlsx', '.xls')):
                            preview_df = pd.read_excel(phys_file, nrows=5)
                        else:
                            phys_file.seek(0)
                            preview_df = pd.read_csv(phys_file, nrows=5)
                        st.write(f"形状: {preview_df.shape}")
                        st.write("列名:", list(preview_df.columns))
                        st.dataframe(preview_df)
                    except Exception as e:
                        st.error(f"无法预览: {str(e)}")
else:
    # 显示欢迎界面
    st.markdown("""
    ## 👋 欢迎使用 Hedge Master Analytics
    
    这是一个专业的套保匹配与分析平台，基于先进的 v19 引擎算法。
    
    ### 🚀 快速开始
    
    1. **上传数据**: 在左侧边栏上传纸货水单和实货台账
    2. **开始分析**: 点击"开始全景分析"按钮
    3. **查看结果**: 系统将自动计算并展示套保匹配结果
    
    ### 📁 支持的文件格式
    
    - **纸货水单**: CSV, Excel (.xlsx, .xls)
    - **实货台账**: CSV, Excel (.xlsx, .xls)
    
    ### 🔧 核心功能
    
    - **智能匹配**: 使用开放式时间排序算法
    - **FIFO净仓**: 自动计算纸货内部对冲
    - **可视化分析**: 丰富的图表展示
    - **风险监控**: 实时MTM估值和敞口分析
    
    ### 📊 输出结果
    
    - 详细的套保匹配明细
    - 剩余敞口分析
    - 套保有效性评估
    - 可下载的报告和数据
    
    ---
    
    **📌 重要提示**: 
    
    为了确保匹配成功，请确认您的数据文件包含以下列：
    
    **纸货文件必须包含**:
    - `Trade Date`: 交易日期
    - `Commodity`: 品种（如 BRENT, WTI）
    - `Month`: 合约月份
    - `Volume`: 交易数量
    - `Price`: 价格
    
    **实货文件必须包含**:
    - `Cargo_ID`: 实货编号
    - `Volume`: 实货数量
    - `Hedge_Proxy`: 对冲品种（如 BRENT, WTI）
    - `Target_Contract_Month`: 目标合约月份
    
    ---
    
    **🔄 如果匹配失败**:
    
    如果分析后没有匹配结果，请检查:
    1. 品种名称是否一致（大小写敏感）
    2. 合约月份格式是否正确
    3. 数据中是否有空值
    4. 列名是否正确
    """)
    
    # 显示示例数据结构
    with st.expander("📋 查看示例数据结构"):
        col_ex1, col_ex2 = st.columns(2)
        
        with col_ex1:
            st.markdown("**纸货数据示例:**")
            st.code("""
Recap No,Trade Date,Commodity,Month,Volume,Price
T001,2024-01-15,BRENT,JAN 24,10000,85.50
T002,2024-01-16,WTI,JAN 24,5000,82.30
T003,2024-01-17,BRENT,FEB 24,8000,86.20
            """)
        
        with col_ex2:
            st.markdown("**实货数据示例:**")
            st.code("""
Cargo_ID,Volume,Direction,Hedge_Proxy,Target_Contract_Month,Designation_Date
C001,5000,Buy,BRENT,JAN 24,2024-01-10
C002,3000,Sell,WTI,JAN 24,2024-01-12
C003,7000,Buy,BRENT,FEB 24,2024-01-15
            """)

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    <p>Hedge Master Analytics v2.0 | 基于 v19 套保引擎 | 专业套保管理工具</p>
    <p>© 2024 版权所有 | 仅供内部使用</p>
</div>
""", unsafe_allow_html=True)

# 导入必要的模块（在文件末尾避免循环导入）
import shutil
