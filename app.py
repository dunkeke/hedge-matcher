import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys

# ==============================================================================
# 导入核心引擎 - 修复版本
# ==============================================================================

# 首先确保能够找到 hedge_engine.py
sys.path.append(os.path.dirname(__file__))

# 创建增强版的读取函数
def read_file_fast_streamlit(file_obj, file_name):
    """
    增强版文件读取函数，支持Streamlit上传的文件对象
    """
    # 根据文件名后缀判断格式
    file_name_lower = file_name.lower()
    
    # 如果是Excel文件
    if file_name_lower.endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(file_obj)
        except Exception as e:
            # 尝试不同的读取方式
            file_obj.seek(0)  # 重置文件指针
            try:
                # 尝试读取第一个sheet
                return pd.read_excel(file_obj, sheet_name=0)
            except Exception:
                file_obj.seek(0)
                try:
                    # 尝试读取所有sheet
                    xls = pd.ExcelFile(file_obj)
                    return pd.read_excel(xls, sheet_name=xls.sheet_names[0])
                except Exception as e2:
                    raise ValueError(f"无法读取Excel文件: {str(e2)}")
    
    # 如果是CSV文件
    elif file_name_lower.endswith('.csv'):
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1', 'iso-8859-1']
        for enc in encodings:
            file_obj.seek(0)  # 重置文件指针
            try:
                return pd.read_csv(file_obj, encoding=enc)
            except Exception:
                continue
        
        # 如果所有编码都失败，尝试自动检测
        file_obj.seek(0)
        try:
            # 使用Python的chardet库尝试检测编码
            import chardet
            raw_data = file_obj.read()
            result = chardet.detect(raw_data)
            file_obj.seek(0)
            return pd.read_csv(file_obj, encoding=result['encoding'])
        except ImportError:
            # 如果没有chardet，使用最后的手段
            file_obj.seek(0)
            try:
                return pd.read_csv(file_obj, encoding='utf-8', errors='ignore')
            except Exception as e:
                raise ValueError(f"无法读取CSV文件: {str(e)}")
        except Exception as e:
            raise ValueError(f"无法读取CSV文件: {str(e)}")
    
    else:
        raise ValueError(f"不支持的文件格式: {file_name}")

# 修改load_data_v19函数以使用上传的文件对象
def load_data_v19_streamlit(paper_file_obj, paper_file_name, phys_file_obj, phys_file_name):
    """
    从Streamlit上传的文件对象加载数据
    """
    import hedge_engine as engine_raw
    
    # 读取纸货数据
    df_p = read_file_fast_streamlit(paper_file_obj, paper_file_name)
    
    # 读取实货数据
    df_ph = read_file_fast_streamlit(phys_file_obj, phys_file_name)
    
    # 使用原始引擎的预处理逻辑
    # 纸货数据预处理
    if 'Trade Date' in df_p.columns:
        df_p['Trade Date'] = pd.to_datetime(df_p['Trade Date'], errors='coerce')
    
    df_p['Volume'] = pd.to_numeric(df_p['Volume'], errors='coerce').fillna(0)
    
    if 'Commodity' in df_p.columns:
        df_p['Std_Commodity'] = df_p['Commodity'].astype(str).str.strip().str.upper().replace('NAN', '')
    elif 'Std_Commodity' in df_p.columns:
        df_p['Std_Commodity'] = df_p['Std_Commodity'].astype(str).str.strip().str.upper().replace('NAN', '')
    
    # 月份标准化
    if 'Month' in df_p.columns:
        df_p['Month'] = engine_raw.standardize_month_vectorized(df_p['Month'])
    else:
        df_p['Month'] = ''
    
    # Recap No 若不存在则用索引代替
    if 'Recap No' not in df_p.columns:
        df_p['Recap No'] = df_p.index.astype(str)
    
    df_p['_original_index'] = df_p.index
    
    # 初始化缺失金融字段
    for col in ['Price', 'Mtm Price', 'Total P/L']:
        if col not in df_p.columns:
            df_p[col] = 0
    
    # 实货数据预处理
    col_map = {'Target_Pricing_Month': 'Target_Contract_Month', 'Month': 'Target_Contract_Month'}
    df_ph.rename(columns=col_map, inplace=True)
    
    df_ph['Volume'] = pd.to_numeric(df_ph['Volume'], errors='coerce').fillna(0)
    df_ph['Unhedged_Volume'] = df_ph['Volume']
    
    if 'Hedge_Proxy' in df_ph.columns:
        df_ph['Hedge_Proxy'] = df_ph['Hedge_Proxy'].astype(str).str.strip().str.upper().replace('NAN', '')
    else:
        df_ph['Hedge_Proxy'] = ''
    
    # 合约月标准化
    if 'Target_Contract_Month' in df_ph.columns:
        df_ph['Target_Contract_Month'] = engine_raw.standardize_month_vectorized(df_ph['Target_Contract_Month'])
    
    # 指定日期
    date_cols = ['Designation_Date', 'Pricing_Start', 'Trade_Date']
    date_col_found = None
    for col in date_cols:
        if col in df_ph.columns:
            date_col_found = col
            break
    
    if date_col_found:
        df_ph['Designation_Date'] = pd.to_datetime(df_ph[date_col_found], errors='coerce')
    else:
        df_ph['Designation_Date'] = pd.NaT
    
    return df_p, df_ph

def run_engine_with_streamlit(paper_file_obj, paper_file_name, phys_file_obj, phys_file_name):
    """
    使用Streamlit文件对象运行引擎
    """
    import hedge_engine as engine_raw
    
    # 1. 加载数据
    df_p, df_ph = load_data_v19_streamlit(paper_file_obj, paper_file_name, phys_file_obj, phys_file_name)
    
    if not df_ph.empty and not df_p.empty:
        # 2. 核心计算
        # Step 1: 净仓
        df_p_net = engine_raw.calculate_net_positions_corrected(df_p)
        
        # Step 2: 匹配
        df_rels, df_ph_updated = engine_raw.auto_match_hedges(df_ph, df_p_net)
        
        # 我们需要创建一个增强的纸货DataFrame，显示分配情况
        if not df_rels.empty and 'Ticket_ID' in df_rels.columns:
            # 按纸货交易分组汇总分配量
            alloc_summary = df_rels.groupby('Ticket_ID')['Allocated_Vol'].sum().reset_index()
            alloc_summary.rename(columns={'Allocated_Vol': 'Allocated_To_Phy'}, inplace=True)
            
            # 合并到纸货数据
            df_p_final = df_p_net.copy()
            
            # 确保Recap No存在
            if 'Recap No' not in df_p_final.columns:
                df_p_final['Recap No'] = df_p_final.index.astype(str)
            
            # 进行合并
            df_p_final = pd.merge(
                df_p_final, 
                alloc_summary, 
                left_on='Recap No', 
                right_on='Ticket_ID', 
                how='left'
            )
            df_p_final['Allocated_To_Phy'] = df_p_final['Allocated_To_Phy'].fillna(0)
            
            # 清理临时列
            if 'Ticket_ID' in df_p_final.columns:
                df_p_final = df_p_final.drop(columns=['Ticket_ID'])
        else:
            df_p_final = df_p_net.copy()
            df_p_final['Allocated_To_Phy'] = 0
        
        return df_rels, df_ph_updated, df_p_final
    else:
        # 返回空DataFrame但保持结构
        return pd.DataFrame(), df_ph, df_p

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
    auto_download = st.checkbox("自动生成报告", value=True)
    
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
            
            # 步骤1: 数据加载
            status_text.text("步骤 1/3: 加载数据...")
            progress_bar.progress(20)
            time.sleep(0.5)
            
            # 步骤2: 运行引擎
            status_text.text("步骤 2/3: 执行套保匹配引擎...")
            progress_bar.progress(50)
            time.sleep(0.5)
            
            start_t = time.time()
            
            # 使用修复版的引擎函数
            df_rels, df_ph_final, df_p_final = run_engine_with_streamlit(
                io.BytesIO(ticket_file.getvalue()),
                ticket_file.name,
                io.BytesIO(phys_file.getvalue()),
                phys_file.name
            )
            
            calc_time = time.time() - start_t
            
            # 步骤3: 计算结果
            status_text.text("步骤 3/3: 生成分析报告...")
            progress_bar.progress(90)
            time.sleep(0.5)
            
            progress_bar.progress(100)
            status_text.text("✅ 分析完成！")
            
            st.markdown(f'<div class="success-message">分析完成！耗时 {calc_time:.2f} 秒</div>', unsafe_allow_html=True)
            
            # --- KPI 指标 ---
            st.markdown("## 📊 关键指标概览")
            
            # 计算指标
            if not df_ph_final.empty and 'Volume' in df_ph_final.columns:
                total_exp = df_ph_final['Volume'].abs().sum()
                unhedged = df_ph_final['Unhedged_Volume'].abs().sum()
                hedged_vol = total_exp - unhedged
                coverage = (hedged_vol / total_exp * 100) if total_exp > 0 else 0
                
                # 计算MTM和PL
                if not df_rels.empty:
                    total_mtm = df_rels['Alloc_Unrealized_MTM'].sum() if 'Alloc_Unrealized_MTM' in df_rels.columns else 0
                    total_pl = df_rels['Alloc_Total_PL'].sum() if 'Alloc_Total_PL' in df_rels.columns else 0
                else:
                    total_mtm = 0
                    total_pl = 0
                
                # 匹配交易数量
                match_count = len(df_rels) if not df_rels.empty else 0
                
                kpi_cols = st.columns(5)
                
                with kpi_cols[0]:
                    st.metric(
                        "实货总敞口", 
                        f"{total_exp:,.0f}",
                        "BBL",
                        delta_color="off"
                    )
                
                with kpi_cols[1]:
                    st.metric(
                        "套保覆盖率", 
                        f"{coverage:.1f}%",
                        f"{hedged_vol:,.0f} BBL"
                    )
                
                with kpi_cols[2]:
                    st.metric(
                        "风险裸露敞口", 
                        f"{unhedged:,.0f}",
                        "BBL",
                        delta_color="inverse"
                    )
                
                with kpi_cols[3]:
                    st.metric(
                        "套保组合 MTM", 
                        f"${total_mtm:,.0f}",
                        f"PL: ${total_pl:,.0f}"
                    )
                
                with kpi_cols[4]:
                    st.metric(
                        "匹配交易数", 
                        f"{match_count}",
                        "笔"
                    )
                
                st.markdown("---")
                
                # --- 图表区域 ---
                st.markdown("## 📈 可视化分析")
                
                if 'Target_Contract_Month' in df_ph_final.columns:
                    col_chart1, col_chart2 = st.columns([2, 1])
                    
                    with col_chart1:
                        st.subheader("📅 月度敞口覆盖情况")
                        # 准备图表数据
                        chart_data = df_ph_final.copy()
                        chart_data['Hedged'] = chart_data['Volume'].abs() - chart_data['Unhedged_Volume'].abs()
                        chart_data['Unhedged'] = chart_data['Unhedged_Volume'].abs()
                        
                        # 按月份分组
                        monthly_summary = chart_data.groupby('Target_Contract_Month').agg({
                            'Hedged': 'sum',
                            'Unhedged': 'sum',
                            'Volume': 'sum'
                        }).reset_index()
                        
                        # 排序月份（如果可能）
                        try:
                            # 尝试转换为日期排序
                            monthly_summary['Month_Sort'] = pd.to_datetime(monthly_summary['Target_Contract_Month'], format='%b %y', errors='coerce')
                            monthly_summary = monthly_summary.sort_values('Month_Sort')
                        except:
                            # 如果不能转换，按字母排序
                            monthly_summary = monthly_summary.sort_values('Target_Contract_Month')
                        
                        if not monthly_summary.empty:
                            fig_bar = px.bar(
                                monthly_summary, 
                                x='Target_Contract_Month', 
                                y=['Hedged', 'Unhedged'], 
                                title="每月敞口 vs 套保覆盖",
                                template="plotly_white",
                                color_discrete_map={
                                    'Hedged': '#2E86AB', 
                                    'Unhedged': '#A23B72'
                                },
                                labels={
                                    'value': 'Volume (BBL)',
                                    'Target_Contract_Month': '合约月份',
                                    'variable': '状态'
                                }
                            )
                            fig_bar.update_layout(
                                hovermode='x unified',
                                barmode='stack',
                                legend=dict(
                                    orientation="h",
                                    yanchor="bottom",
                                    y=1.02,
                                    xanchor="right",
                                    x=1
                                )
                            )
                            st.plotly_chart(fig_bar, use_container_width=True)
                    
                    with col_chart2:
                        st.subheader("📊 套保占比分析")
                        
                        # 饼图数据
                        labels = ['已套保', '未套保']
                        values = [hedged_vol, unhedged]
                        
                        if total_exp > 0:
                            fig_pie = px.pie(
                                values=values, 
                                names=labels,
                                color_discrete_sequence=['#2E86AB', '#A23B72'],
                                hole=0.4,
                                title=f"套保覆盖率: {coverage:.1f}%"
                            )
                            fig_pie.update_traces(
                                textposition='inside', 
                                textinfo='percent+label',
                                hovertemplate='<b>%{label}</b><br>' +
                                            '数量: %{value:,.0f} BBL<br>' +
                                            '占比: %{percent}'
                            )
                            st.plotly_chart(fig_pie, use_container_width=True)
                        else:
                            st.info("无敞口数据")
                else:
                    st.warning("实货数据中缺少 Target_Contract_Month 列，无法生成月度图表")
                
                # --- 数据表格区域 ---
                st.markdown("---")
                st.markdown("## 📋 详细数据")
                
                tab1, tab2, tab3 = st.tabs(["✅ 匹配明细", "⚠️ 实货剩余", "📦 纸货剩余"])
                
                with tab1:
                    if not df_rels.empty:
                        # 显示匹配明细
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
                    else:
                        st.markdown('<div class="warning-message">无匹配记录</div>', unsafe_allow_html=True)
                
                with tab2:
                    if not df_ph_final.empty:
                        # 只显示还有未对冲敞口的实货
                        remaining_phy = df_ph_final[abs(df_ph_final['Unhedged_Volume']) > 0.1].copy()
                        
                        if not remaining_phy.empty:
                            st.info(f"还有 {len(remaining_phy)} 笔实货存在未对冲敞口")
                            st.dataframe(remaining_phy, use_container_width=True)
                        else:
                            st.success("🎉 所有实货敞口均已完全对冲！")
                    else:
                        st.warning("实货数据为空")
                
                with tab3:
                    if not df_p_final.empty and 'Allocated_To_Phy' in df_p_final.columns:
                        # 计算剩余量
                        df_p_final['Implied_Remaining'] = df_p_final['Volume'] - df_p_final['Allocated_To_Phy']
                        
                        # 只显示还有剩余量的纸货
                        remaining_paper = df_p_final[abs(df_p_final['Implied_Remaining']) > 0.1].copy()
                        
                        if not remaining_paper.empty:
                            st.info(f"还有 {len(remaining_paper)} 笔纸货交易未完全分配")
                            st.dataframe(remaining_paper, use_container_width=True)
                        else:
                            st.success("📊 所有纸货交易均已完全分配！")
                    else:
                        st.warning("纸货数据为空或缺少分配信息")
                
                # --- 总结报告 ---
                st.markdown("---")
                st.markdown("## 📄 分析总结报告")
                
                report_col1, report_col2 = st.columns([3, 1])
                
                with report_col1:
                    st.markdown(f"""
                    ### 执行摘要
                    
                    **分析时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
                    **处理速度**: {calc_time:.2f} 秒
                    
                    **核心发现**:
                    - 成功匹配 **{match_count}** 笔套保交易
                    - 实现 **{coverage:.1f}%** 的敞口覆盖率
                    - 剩余 **{unhedged:,.0f} BBL** 风险暴露
                    - 套保组合当前估值为 **${total_mtm:,.0f}**
                    
                    **建议**:
                    {f"✅ 套保覆盖率良好，建议维持当前策略" if coverage > 70 else 
                      f"⚠️ 套保覆盖率偏低({coverage:.1f}%)，建议增加对冲比例" if coverage > 30 else 
                      "❌ 套保严重不足，建议立即采取对冲措施"}
                    """)
                
                with report_col2:
                    # 生成综合报告文件
                    report_data = {
                        '指标': ['总敞口', '已对冲', '未对冲', '覆盖率', 'MTM估值', '匹配交易数'],
                        '数值': [
                            f"{total_exp:,.0f} BBL",
                            f"{hedged_vol:,.0f} BBL",
                            f"{unhedged:,.0f} BBL",
                            f"{coverage:.1f}%",
                            f"${total_mtm:,.0f}",
                            f"{match_count} 笔"
                        ]
                    }
                    report_df = pd.DataFrame(report_data)
                    st.dataframe(report_df, use_container_width=True)
                    
                    # 生成综合报告下载
                    report_summary = f"""套保分析报告
生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
数据处理耗时: {calc_time:.2f}秒

关键指标:
总敞口: {total_exp:,.0f} BBL
已对冲: {hedged_vol:,.0f} BBL
未对冲: {unhedged:,.0f} BBL
覆盖率: {coverage:.1f}%
MTM估值: ${total_mtm:,.0f}
匹配交易数: {match_count}笔

建议:
{f"套保覆盖率良好，建议维持当前策略" if coverage > 70 else 
 f"套保覆盖率偏低({coverage:.1f}%)，建议增加对冲比例" if coverage > 30 else 
 "套保严重不足，建议立即采取对冲措施"}
"""
                    
                    st.download_button(
                        "📄 下载分析报告",
                        data=report_summary.encode('utf-8'),
                        file_name="hedge_analysis_report.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                
            else:
                st.error("实货数据加载后为空或缺少必要列")
                
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            st.markdown('<div class="error-message">错误详情:</div>', unsafe_allow_html=True)
            import traceback
            st.code(traceback.format_exc())
            
            st.info("💡 调试建议:")
            st.markdown("""
            1. 检查上传文件格式是否正确
            2. 确保文件包含必要的列名
            3. 查看文件编码是否正确（CSV文件常见问题）
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
    
    **📌 提示**: 请确保上传的文件包含必要的列，如：
    - 纸货: `Trade Date`, `Volume`, `Commodity`, `Month`, `Price`
    - 实货: `Cargo_ID`, `Volume`, `Hedge_Proxy`, `Target_Contract_Month`
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
            """)
        
        with col_ex2:
            st.markdown("**实货数据示例:**")
            st.code("""
Cargo_ID,Volume,Direction,Hedge_Proxy,Target_Contract_Month
C001,5000,Buy,BRENT,JAN 24
C002,3000,Sell,WTI,JAN 24
            """)

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    <p>Hedge Master Analytics v2.0 | 基于 v19 套保引擎 | 专业套保管理工具</p>
    <p>© 2024 版权所有 | 仅供内部使用</p>
</div>
""", unsafe_allow_html=True)
