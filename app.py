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
from plotly.subplots import make_subplots

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
    dates = pd.to_datetime(s, errors='coerce')
    result = dates.dt.strftime('%b %y').str.upper()
    mask_invalid = dates.isna()
    if mask_invalid.any():
        invalid = s[mask_invalid]
        import re
        def swap_if_match(val):
            m = re.match(r'^(\d{2})\s*([A-Z]{3})$', val)
            if m:
                yr, mon = m.groups()
                return f"{mon} {yr}"
            return val
        swapped = invalid.map(swap_if_match)
        swapped_dates = pd.to_datetime(swapped, errors='coerce')
        swapped_formatted = swapped_dates.dt.strftime('%b %y').str.upper()
        result.loc[mask_invalid & swapped_dates.notna()] = swapped_formatted.loc[swapped_dates.notna()]
        result.loc[mask_invalid & swapped_dates.isna()] = swapped.loc[swapped_dates.isna()]
    return result

# ---------------------------------------------------------
# 2. 可视化分析函数
# ---------------------------------------------------------

def create_summary_metrics(df_relations, df_physical):
    """创建概览指标卡片"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_matched = abs(df_relations['Allocated_Vol']).sum()
        total_physical = abs(df_physical['Volume']).sum()
        match_rate = (total_matched / total_physical * 100) if total_physical > 0 else 0
        st.metric("📊 匹配率", f"{match_rate:.1f}%", 
                 delta=f"{total_matched:,.0f}/{total_physical:,.0f}")
    
    with col2:
        matched_cargos = df_relations['Cargo_ID'].nunique()
        total_cargos = df_physical['Cargo_ID'].nunique()
        st.metric("📦 匹配实货数", f"{matched_cargos}/{total_cargos}",
                 delta=f"覆盖率{matched_cargos/total_cargos*100:.1f}%" if total_cargos > 0 else "0%")
    
    with col3:
        total_pl = df_relations['Alloc_Total_PL'].sum()
        unrealized_mtm = df_relations['Alloc_Unrealized_MTM'].sum()
        st.metric("💰 总P/L", f"${total_pl:,.2f}",
                 delta=f"未实现: ${unrealized_mtm:,.2f}")
    
    with col4:
        avg_time_lag = df_relations['Time_Lag'].abs().mean() if 'Time_Lag' in df_relations.columns and not df_relations['Time_Lag'].isna().all() else 0
        st.metric("⏱️ 平均时间差", f"{avg_time_lag:.1f}天")

def create_match_volume_chart(df_relations):
    """创建匹配量分布图表"""
    # 按Cargo_ID的匹配量
    cargo_summary = df_relations.copy()
    cargo_summary['Allocated_Vol_Abs'] = abs(cargo_summary['Allocated_Vol'])
    cargo_summary = cargo_summary.groupby('Cargo_ID')['Allocated_Vol_Abs'].sum().reset_index()
    
    fig = px.bar(cargo_summary.sort_values('Allocated_Vol_Abs', ascending=False).head(20), 
                 x='Cargo_ID', y='Allocated_Vol_Abs',
                 title='📈 各Cargo_ID匹配量TOP20',
                 labels={'Allocated_Vol_Abs': '匹配量', 'Cargo_ID': '实货编号'},
                 color='Allocated_Vol_Abs',
                 color_continuous_scale='Viridis')
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_pl_distribution_chart(df_relations):
    """创建P/L分布图表"""
    fig = px.histogram(df_relations, x='Alloc_Total_PL',
                       title='💰 P/L分布直方图',
                       labels={'Alloc_Total_PL': 'P/L值'},
                       nbins=30,
                       color_discrete_sequence=['#636EFA'])
    fig.add_vline(x=0, line_dash="dash", line_color="red")
    return fig

def create_time_lag_chart(df_relations):
    """创建时间差分析图表"""
    if 'Time_Lag' in df_relations.columns:
        time_lag_data = df_relations['Time_Lag'].dropna()
        if not time_lag_data.empty:
            fig = px.histogram(time_lag_data,
                             title='⏱️ 匹配时间差分布',
                             labels={'value': '时间差(天)'},
                             nbins=30)
            fig.add_vline(x=0, line_dash="dash", line_color="green",
                         annotation_text="完美匹配", 
                         annotation_position="top right")
            return fig
    return None

def create_month_distribution_chart(df_relations):
    """创建月份分布图表"""
    if 'Month' in df_relations.columns:
        month_summary = df_relations.groupby('Month')['Allocated_Vol'].sum().reset_index()
        month_summary['Allocated_Vol_Abs'] = abs(month_summary['Allocated_Vol'])
        
        fig = px.bar(month_summary.sort_values('Allocated_Vol_Abs', ascending=False),
                     x='Month', y='Allocated_Vol_Abs',
                     title='📅 各月份匹配量分布',
                     labels={'Allocated_Vol_Abs': '匹配量', 'Month': '合约月份'},
                     color='Allocated_Vol_Abs',
                     color_continuous_scale='Plasma')
        fig.update_layout(xaxis_tickangle=-45)
        return fig
    return None

def create_price_analysis_chart(df_relations):
    """创建价格分析图表"""
    if 'Open_Price' in df_relations.columns and 'MTM_Price' in df_relations.columns:
        # 计算价格差异
        price_data = df_relations.copy()
        price_data['Price_Diff'] = price_data['MTM_Price'] - price_data['Open_Price']
        price_data['Price_Diff_Pct'] = (price_data['Price_Diff'] / price_data['Open_Price'] * 100).fillna(0)
        
        fig = px.scatter(price_data, x='Open_Price', y='MTM_Price',
                         size='Allocated_Vol',
                         color='Price_Diff_Pct',
                         title='💹 开仓价 vs 当前价分析',
                         labels={'Open_Price': '开仓价', 'MTM_Price': '当前价'},
                         hover_data=['Cargo_ID', 'Ticket_ID', 'Allocated_Vol'])
        fig.add_trace(go.Scatter(x=[price_data['Open_Price'].min(), price_data['Open_Price'].max()],
                                y=[price_data['Open_Price'].min(), price_data['Open_Price'].max()],
                                mode='lines',
                                name='平价线',
                                line=dict(color='red', dash='dash')))
        return fig
    return None

def create_detailed_match_table(df_relations):
    """创建详细的匹配表格"""
    # 选择要显示的列
    display_columns = [
        'Cargo_ID', 'Ticket_ID', 'Month', 'Allocated_Vol',
        'Open_Price', 'MTM_Price', 'Alloc_Total_PL', 'Alloc_Unrealized_MTM'
    ]
    
    if 'Time_Lag' in df_relations.columns:
        display_columns.insert(4, 'Time_Lag')
    
    # 确保列存在
    available_columns = [col for col in display_columns if col in df_relations.columns]
    
    # 格式化数字列
    formatted_df = df_relations[available_columns].copy()
    
    # 应用格式化
    def format_number(x):
        if isinstance(x, (int, float)):
            return f"{x:,.2f}"
        return x
    
    for col in ['Allocated_Vol', 'Open_Price', 'MTM_Price', 'Alloc_Total_PL', 'Alloc_Unrealized_MTM']:
        if col in formatted_df.columns:
            formatted_df[col] = formatted_df[col].apply(format_number)
    
    return formatted_df

def create_export_data(df_relations, df_physical, df_paper_net):
    """创建导出的数据集"""
    export_data = {
        '匹配明细': df_relations,
        '实货数据': df_physical,
        '纸货净仓': df_paper_net
    }
    return export_data

# ---------------------------------------------------------
# 3. Streamlit 主应用
# ---------------------------------------------------------

def main():
    st.set_page_config(
        page_title="实纸货套保匹配分析系统",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # 自定义CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #374151;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #F3F4F6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3B82F6;
    }
    .success-box {
        background-color: #D1FAE5;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #10B981;
        margin: 1rem 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 标题
    st.markdown('<h1 class="main-header">📈 实纸货套保匹配分析系统</h1>', unsafe_allow_html=True)
    st.markdown("### 专业套保匹配与风险分析工具")
    
    # 初始化session state
    if 'match_results' not in st.session_state:
        st.session_state.match_results = None
    if 'processed_data' not in st.session_state:
        st.session_state.processed_data = None
    
    # 侧边栏
    with st.sidebar:
        st.markdown("### 📁 数据上传")
        
        paper_file = st.file_uploader(
            "纸货数据文件",
            type=["csv", "xlsx", "xls"],
            help="包含交易日期、交易量、商品、月份、价格等字段"
        )
        
        physical_file = st.file_uploader(
            "实货数据文件",
            type=["csv", "xlsx", "xls"],
            help="包含Cargo_ID、交易量、套保代理、目标月份、方向等字段"
        )
        
        st.markdown("---")
        st.markdown("### ⚙️ 分析设置")
        
        show_charts = st.checkbox("显示分析图表", value=True)
        chart_theme = st.selectbox("图表主题", ["plotly", "plotly_white", "plotly_dark", "seaborn"])
        max_rows_display = st.slider("表格显示行数", 10, 100, 50)
        
        st.markdown("---")
        st.markdown("### 💾 数据导出")
        export_format = st.radio("导出格式", ["CSV", "Excel"])
        
        st.markdown("---")
        st.markdown("#### 📊 系统信息")
        st.caption(f"Streamlit v{st.__version__}")
        st.caption(f"Pandas v{pd.__version__}")
    
    # 主内容区
    if paper_file is not None and physical_file is not None:
        # 处理数据（使用你原来的引擎代码）
        try:
            # 这里应该调用你的匹配引擎
            # 为了演示，我假设已经有了匹配结果
            st.success("✅ 数据上传成功！")
            
            # 显示数据预览
            with st.expander("📋 数据预览", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**纸货数据**")
                    if paper_file.name.endswith(('.xlsx', '.xls')):
                        df_paper_preview = pd.read_excel(paper_file, nrows=10)
                    else:
                        df_paper_preview = pd.read_csv(paper_file, nrows=10)
                    st.dataframe(df_paper_preview, use_container_width=True)
                
                with col2:
                    st.markdown("**实货数据**")
                    if physical_file.name.endswith(('.xlsx', '.xls')):
                        df_physical_preview = pd.read_excel(physical_file, nrows=10)
                    else:
                        df_physical_preview = pd.read_csv(physical_file, nrows=10)
                    st.dataframe(df_physical_preview, use_container_width=True)
            
            # 模拟匹配按钮
            if st.button("🚀 执行套保匹配分析", type="primary", use_container_width=True):
                with st.spinner("正在执行套保匹配分析..."):
                    # 这里应该调用你的匹配引擎
                    # 为了演示，创建示例数据
                    time.sleep(2)  # 模拟处理时间
                    
                    # 创建示例匹配结果
                    example_data = {
                        'Cargo_ID': [f'PHY-2026-{i:03d}' for i in range(1, 11)],
                        'Ticket_ID': [f'TKT-2025-{i:03d}' for i in range(100, 110)],
                        'Month': ['JAN 26', 'FEB 26', 'MAR 26', 'APR 26', 'MAY 26',
                                 'JUN 26', 'JUL 26', 'AUG 26', 'SEP 26', 'OCT 26'],
                        'Allocated_Vol': np.random.uniform(-100000, 100000, 10),
                        'Open_Price': np.random.uniform(70, 85, 10),
                        'MTM_Price': np.random.uniform(75, 90, 10),
                        'Alloc_Total_PL': np.random.uniform(-50000, 50000, 10),
                        'Alloc_Unrealized_MTM': np.random.uniform(-20000, 20000, 10),
                        'Time_Lag': np.random.randint(-30, 30, 10),
                        'Proxy': ['BRENT']*5 + ['JCC']*5
                    }
                    
                    df_relations = pd.DataFrame(example_data)
                    df_physical = pd.DataFrame({
                        'Cargo_ID': [f'PHY-2026-{i:03d}' for i in range(1, 16)],
                        'Volume': np.random.uniform(100000, 500000, 15)
                    })
                    
                    # 保存到session state
                    st.session_state.match_results = df_relations
                    st.session_state.physical_data = df_physical
                    
                    st.success("✅ 套保匹配分析完成！")
        
        except Exception as e:
            st.error(f"❌ 数据处理错误: {str(e)}")
    
    # 显示分析结果
    if st.session_state.match_results is not None:
        st.markdown("---")
        st.markdown('<h2 class="sub-header">📊 匹配分析结果</h2>', unsafe_allow_html=True)
        
        df_relations = st.session_state.match_results
        df_physical = st.session_state.physical_data
        
        # 1. 概览指标
        create_summary_metrics(df_relations, df_physical)
        
        # 2. 详细匹配表格
        st.markdown('<h3 class="sub-header">📋 匹配明细表</h3>', unsafe_allow_html=True)
        detailed_table = create_detailed_match_table(df_relations)
        st.dataframe(detailed_table.head(max_rows_display), use_container_width=True)
        
        # 显示总数
        st.caption(f"显示 {min(len(detailed_table), max_rows_display)} 条记录，共 {len(detailed_table)} 条")
        
        # 3. 分析图表
        if show_charts:
            st.markdown('<h3 class="sub-header">📈 可视化分析</h3>', unsafe_allow_html=True)
            
            # 设置图表主题
            px.defaults.template = chart_theme
            
            # 创建图表选项卡
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 匹配量分析", "💰 P/L分析", "⏱️ 时间分析", 
                "📅 月份分布", "💹 价格分析"
            ])
            
            with tab1:
                fig1 = create_match_volume_chart(df_relations)
                st.plotly_chart(fig1, use_container_width=True)
            
            with tab2:
                fig2 = create_pl_distribution_chart(df_relations)
                st.plotly_chart(fig2, use_container_width=True)
                
                # P/L汇总
                pl_summary = df_relations['Alloc_Total_PL'].describe()
                st.dataframe(pl_summary, use_container_width=True)
            
            with tab3:
                fig3 = create_time_lag_chart(df_relations)
                if fig3:
                    st.plotly_chart(fig3, use_container_width=True)
                else:
                    st.info("无时间差数据")
            
            with tab4:
                fig4 = create_month_distribution_chart(df_relations)
                if fig4:
                    st.plotly_chart(fig4, use_container_width=True)
                else:
                    st.info("无月份数据")
            
            with tab5:
                fig5 = create_price_analysis_chart(df_relations)
                if fig5:
                    st.plotly_chart(fig5, use_container_width=True)
                else:
                    st.info("无价格数据")
        
        # 4. 数据导出
        st.markdown("---")
        st.markdown('<h3 class="sub-header">💾 数据导出</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # 导出匹配结果
            csv_data = df_relations.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 下载匹配结果 (CSV)",
                data=csv_data,
                file_name="hedge_matching_results.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # 导出汇总报告
            summary_report = f"""
            套保匹配分析报告
            生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            匹配统计:
            - 总匹配量: {abs(df_relations['Allocated_Vol']).sum():,.0f}
            - 匹配率: {abs(df_relations['Allocated_Vol']).sum()/abs(df_physical['Volume']).sum()*100:.1f}%
            - 总P/L: ${df_relations['Alloc_Total_PL'].sum():,.2f}
            - 未实现MTM: ${df_relations['Alloc_Unrealized_MTM'].sum():,.2f}
            - 匹配交易数: {len(df_relations)}
            - 涉及Cargo_ID数: {df_relations['Cargo_ID'].nunique()}
            """
            
            st.download_button(
                label="📄 下载汇总报告 (TXT)",
                data=summary_report.encode('utf-8'),
                file_name="hedge_matching_summary.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # 5. 高级分析选项
        with st.expander("🔍 高级分析选项", expanded=False):
            st.markdown("#### 自定义分析")
            
            analysis_type = st.selectbox(
                "选择分析类型",
                ["按月份分析", "按Cargo_ID分析", "按价格区间分析", "自定义分组"]
            )
            
            if analysis_type == "按月份分析" and 'Month' in df_relations.columns:
                selected_month = st.multiselect(
                    "选择月份",
                    options=df_relations['Month'].unique(),
                    default=df_relations['Month'].unique()[:3]
                )
                
                if selected_month:
                    filtered_data = df_relations[df_relations['Month'].isin(selected_month)]
                    st.dataframe(filtered_data, use_container_width=True)
            
            elif analysis_type == "按Cargo_ID分析":
                selected_cargos = st.multiselect(
                    "选择Cargo_ID",
                    options=df_relations['Cargo_ID'].unique(),
                    default=df_relations['Cargo_ID'].unique()[:5]
                )
                
                if selected_cargos:
                    filtered_data = df_relations[df_relations['Cargo_ID'].isin(selected_cargos)]
                    st.dataframe(filtered_data, use_container_width=True)
    
    else:
        # 欢迎页面
        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            ### 🎯 系统功能
            
            **核心功能：**
            1. **智能匹配** - 基于FIFO算法的实纸货套保匹配
            2. **风险分析** - P/L分析、时间差分析、价格分析
            3. **可视化报表** - 丰富的图表展示匹配效果
            4. **数据导出** - 支持多种格式的数据导出
            
            **支持的数据类型：**
            - CSV文件 (UTF-8, GBK等编码)
            - Excel文件 (.xlsx, .xls)
            
            **分析维度：**
            - 📊 匹配率与覆盖率分析
            - 💰 P/L与MTM分析
            - ⏱️ 时间差与效率分析
            - 📅 月份分布分析
            - 💹 价格走势分析
            """)
        
        with col2:
            st.markdown("""
            ### 🚀 快速开始
            
            1. **上传文件**
               - 纸货交易数据
               - 实货持仓数据
            
            2. **执行匹配**
               - 点击"执行套保匹配分析"
               - 等待系统处理
            
            3. **查看结果**
               - 查看匹配明细
               - 分析图表
               - 下载报告
            
            4. **导出数据**
               - 匹配结果CSV
               - 汇总报告TXT
            """)
        
        st.markdown("---")
        st.markdown("### 📚 使用示例")
        
        # 示例数据
        example_data = {
            '字段': ['Trade Date', 'Volume', 'Commodity', 'Month', 'Price', 'Cargo_ID', 'Hedge_Proxy', 'Target_Contract_Month'],
            '说明': ['交易日期', '交易量(正买负卖)', '商品品种', '合约月份', '交易价格', '实货编号', '套保代理', '目标月份'],
            '示例': ['2024-01-15', '1000', 'BRENT', 'JAN 25', '75.50', 'PHY-2025-001', 'BRENT', 'JAN 25']
        }
        
        st.table(pd.DataFrame(example_data))

if __name__ == "__main__":
    main()
