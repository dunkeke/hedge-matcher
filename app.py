import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys

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
st.caption("Version: 3.0 | 直接调用引擎核心函数")
st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 核心修复：直接使用引擎函数但不解包返回值
# ==============================================================================

def run_hedge_engine_safely(paper_content, paper_name, phys_content, phys_name):
    """安全地运行对冲引擎，处理返回值问题"""
    try:
        # 导入引擎
        sys.path.append(os.path.dirname(__file__))
        import hedge_engine as engine
        
        # 显示引擎信息
        st.sidebar.info(f"引擎版本: {engine.__name__}")
        
        # 读取数据
        def read_file(file_content, file_name):
            file_name_lower = file_name.lower()
            if file_name_lower.endswith(('.xlsx', '.xls')):
                return pd.read_excel(io.BytesIO(file_content))
            else:
                # 尝试多种编码
                encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1']
                for enc in encodings:
                    try:
                        return pd.read_csv(io.BytesIO(file_content), encoding=enc)
                    except:
                        continue
                return pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
        
        # 读取原始数据
        df_paper_raw = read_file(paper_content, paper_name)
        df_physical_raw = read_file(phys_content, phys_name)
        
        # 显示数据信息
        with st.sidebar.expander("📊 数据信息"):
            st.write("**纸货数据:**")
            st.write(f"- 行数: {len(df_paper_raw)}")
            st.write(f"- 列名示例: {list(df_paper_raw.columns)[:5]}")
            
            st.write("**实货数据:**")
            st.write(f"- 行数: {len(df_physical_raw)}")
            st.write(f"- 列名示例: {list(df_physical_raw.columns)[:5]}")
        
        # 预处理数据 - 简化版本
        # 纸货数据
        df_paper = df_paper_raw.copy()
        
        # 确保有必需列
        if 'Trade Date' in df_paper.columns:
            df_paper['Trade Date'] = pd.to_datetime(df_paper['Trade Date'], errors='coerce')
        
        if 'Volume' not in df_paper.columns:
            # 尝试找到数量列
            for col in df_paper.columns:
                if 'vol' in col.lower() or '数量' in col:
                    df_paper['Volume'] = pd.to_numeric(df_paper[col], errors='coerce').fillna(0)
                    break
            else:
                df_paper['Volume'] = 0
        
        if 'Commodity' not in df_paper.columns:
            # 尝试找到品种列
            for col in df_paper.columns:
                if 'commodity' in col.lower() or '品种' in col:
                    df_paper['Commodity'] = df_paper[col].astype(str)
                    break
            else:
                df_paper['Commodity'] = 'UNKNOWN'
        
        # 创建 Std_Commodity
        df_paper['Std_Commodity'] = df_paper['Commodity'].astype(str).str.strip().str.upper()
        
        if 'Month' not in df_paper.columns:
            df_paper['Month'] = ''
        
        if 'Recap No' not in df_paper.columns:
            df_paper['Recap No'] = df_paper.index.astype(str)
        
        # 实货数据
        df_physical = df_physical_raw.copy()
        
        if 'Volume' not in df_physical.columns:
            # 尝试找到数量列
            for col in df_physical.columns:
                if 'vol' in col.lower() or '数量' in col:
                    df_physical['Volume'] = pd.to_numeric(df_physical[col], errors='coerce').fillna(0)
                    break
            else:
                df_physical['Volume'] = 0
        
        df_physical['Unhedged_Volume'] = df_physical['Volume']
        
        if 'Hedge_Proxy' not in df_physical.columns:
            # 尝试找到对冲品种列
            for col in df_physical.columns:
                if 'proxy' in col.lower() or '对冲' in col or '品种' in col:
                    df_physical['Hedge_Proxy'] = df_physical[col].astype(str)
                    break
            else:
                df_physical['Hedge_Proxy'] = 'UNKNOWN'
        
        df_physical['Hedge_Proxy'] = df_physical['Hedge_Proxy'].astype(str).str.strip().str.upper()
        
        if 'Target_Contract_Month' not in df_physical.columns:
            df_physical['Target_Contract_Month'] = ''
        
        # 关键修复：直接调用引擎函数但捕获所有返回值
        st.sidebar.info("正在执行净仓计算...")
        df_paper_net = engine.calculate_net_positions_corrected(df_paper)
        
        st.sidebar.info("正在执行实货匹配...")
        
        # 方法1：尝试直接调用并捕获所有返回值
        try:
            result = engine.auto_match_hedges(df_physical, df_paper_net)
            
            # 检查返回值类型
            if isinstance(result, tuple):
                if len(result) == 2:
                    df_rels, df_physical_updated = result
                elif len(result) == 3:
                    df_rels, df_physical_updated, extra = result
                    st.sidebar.warning(f"收到3个返回值，忽略第3个")
                else:
                    st.sidebar.error(f"意外的返回值数量: {len(result)}")
                    # 只取前两个
                    df_rels, df_physical_updated = result[0], result[1]
            elif isinstance(result, pd.DataFrame):
                # 如果只返回一个DataFrame
                df_rels = result
                df_physical_updated = df_physical.copy()
            else:
                raise ValueError(f"无法理解的返回值类型: {type(result)}")
                
        except ValueError as e:
            if "too many values to unpack" in str(e):
                st.sidebar.warning("检测到返回值解包问题，使用备用方案...")
                # 方法2：使用try-except处理
                try:
                    # 尝试接收3个返回值
                    df_rels, df_physical_updated, _ = engine.auto_match_hedges(df_physical, df_paper_net)
                except:
                    # 方法3：使用占位符
                    result = engine.auto_match_hedges(df_physical, df_paper_net)
                    df_rels = result[0] if len(result) > 0 else pd.DataFrame()
                    df_physical_updated = result[1] if len(result) > 1 else df_physical.copy()
            else:
                raise
        
        # 准备纸货最终数据
        df_paper_final = df_paper_net.copy()
        
        return df_rels, df_physical_updated, df_paper_final
        
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
    
    run_btn = st.button(
        "🚀 开始匹配分析", 
        type="primary", 
        use_container_width=True,
        disabled=not (ticket_file and phys_file)
    )

# ==============================================================================
# 主内容区域
# ==============================================================================

if run_btn and ticket_file and phys_file:
    with st.spinner('正在执行匹配运算...'):
        try:
            # 获取文件内容
            paper_content = ticket_file.getvalue()
            paper_name = ticket_file.name
            phys_content = phys_file.getvalue()
            phys_name = phys_file.name
            
            # 运行引擎
            start_t = time.time()
            
            df_rels, df_ph_final, df_p_final = run_hedge_engine_safely(
                paper_content, paper_name, phys_content, phys_name
            )
            
            calc_time = time.time() - start_t
            
            st.markdown(f'<div class="success-message">✅ 分析完成！耗时 {calc_time:.2f} 秒</div>', unsafe_allow_html=True)
            
            # 显示结果
            if not df_rels.empty:
                st.success(f"🎉 成功匹配 {len(df_rels)} 笔交易")
                
                # 显示摘要
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    total_allocated = df_rels['Allocated_Vol'].abs().sum() if 'Allocated_Vol' in df_rels.columns else 0
                    st.metric("总匹配量", f"{total_allocated:,.0f} BBL")
                
                with col2:
                    total_exposure = df_ph_final['Volume'].abs().sum() if 'Volume' in df_ph_final.columns else 0
                    coverage = (total_allocated / total_exposure * 100) if total_exposure > 0 else 0
                    st.metric("套保覆盖率", f"{coverage:.1f}%")
                
                with col3:
                    total_mtm = df_rels['Alloc_Unrealized_MTM'].sum() if 'Alloc_Unrealized_MTM' in df_rels.columns else 0
                    st.metric("组合MTM", f"${total_mtm:,.0f}")
                
                # 显示匹配明细
                st.markdown("### 📋 匹配明细")
                st.dataframe(df_rels, use_container_width=True)
                
                # 下载按钮
                csv = df_rels.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 下载匹配明细",
                    data=csv,
                    file_name="hedge_matches.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # 显示剩余敞口
                st.markdown("### 📊 剩余敞口分析")
                
                if 'Unhedged_Volume' in df_ph_final.columns:
                    remaining = df_ph_final[abs(df_ph_final['Unhedged_Volume']) > 0.1]
                    if not remaining.empty:
                        st.warning(f"⚠️ 还有 {len(remaining)} 笔实货未完全对冲")
                        st.dataframe(remaining[['Cargo_ID', 'Volume', 'Unhedged_Volume', 'Hedge_Proxy']], 
                                   use_container_width=True)
                    else:
                        st.success("✅ 所有实货均已完全对冲")
                
            else:
                st.warning("⚠️ 未找到匹配结果")
                
                # 显示数据预览帮助诊断
                st.markdown("### 🔍 数据预览")
                
                # 重新读取数据
                def quick_read(content, name):
                    if name.lower().endswith(('.xlsx', '.xls')):
                        return pd.read_excel(io.BytesIO(content))
                    else:
                        return pd.read_csv(io.BytesIO(content), encoding='utf-8', errors='ignore')
                
                df_paper_preview = quick_read(paper_content, paper_name)
                df_phys_preview = quick_read(phys_content, phys_name)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**纸货数据前5行:**")
                    st.dataframe(df_paper_preview.head(), use_container_width=True)
                    st.write(f"总行数: {len(df_paper_preview)}")
                    if 'Commodity' in df_paper_preview.columns:
                        st.write(f"品种数: {df_paper_preview['Commodity'].nunique()}")
                
                with col2:
                    st.write("**实货数据前5行:**")
                    st.dataframe(df_phys_preview.head(), use_container_width=True)
                    st.write(f"总行数: {len(df_phys_preview)}")
                    if 'Hedge_Proxy' in df_phys_preview.columns:
                        st.write(f"对冲品种数: {df_phys_preview['Hedge_Proxy'].nunique()}")
                
                # 匹配诊断
                st.markdown("### 🔧 匹配诊断")
                
                if 'Commodity' in df_paper_preview.columns and 'Hedge_Proxy' in df_phys_preview.columns:
                    paper_com = set(str(x).upper().strip() for x in df_paper_preview['Commodity'].dropna().unique())
                    phys_proxy = set(str(x).upper().strip() for x in df_phys_preview['Hedge_Proxy'].dropna().unique())
                    
                    if paper_com and phys_proxy:
                        common = paper_com.intersection(phys_proxy)
                        if common:
                            st.success(f"✅ 找到 {len(common)} 个共同品种: {list(common)[:5]}")
                        else:
                            st.error(f"❌ 没有共同品种！")
                            st.write(f"纸货品种: {list(paper_com)[:10]}")
                            st.write(f"实货品种: {list(phys_proxy)[:10]}")
                
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            
            # 显示简化的错误信息
            with st.expander("查看错误详情"):
                import traceback
                st.code(str(e))
            
            st.info("💡 建议检查:")
            st.markdown("""
            1. 文件格式是否正确
            2. 是否包含必需的列名
            3. 数据是否有空值或格式错误
            4. 品种名称是否匹配
            """)
else:
    # 显示欢迎界面
    st.markdown("""
    ## 👋 欢迎使用 Hedge Master Analytics
    
    ### 🚀 快速开始
    
    1. **上传数据**: 在左侧上传纸货水单和实货台账
    2. **开始分析**: 点击"开始匹配分析"按钮
    3. **查看结果**: 系统将自动计算匹配结果
    
    ### 📋 必需的数据列
    
    **纸货水单需要包含:**
    - `Trade Date`: 交易日期
    - `Commodity`: 交易品种
    - `Month`: 合约月份
    - `Volume`: 交易数量
    
    **实货台账需要包含:**
    - `Cargo_ID`: 实货编号
    - `Volume`: 实货数量
    - `Hedge_Proxy`: 对冲品种
    - `Target_Contract_Month`: 目标合约月
    
    ### ⚡ 系统特性
    
    - **智能匹配**: 使用先进的匹配算法
    - **自动处理**: 自动识别数据格式
    - **实时分析**: 快速生成匹配结果
    - **详细报告**: 提供完整的匹配明细
    """)

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    <p>Hedge Master Analytics v3.0 | 专业套保匹配工具</p>
</div>
""", unsafe_allow_html=True)
