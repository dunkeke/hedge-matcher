import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys
import tempfile
import struct

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
# 修复的文件读取函数
# ==============================================================================

def detect_file_type_simple(file_content, file_name):
    """简单检测文件类型"""
    file_name_lower = file_name.lower()
    
    # 首先检查文件头
    try:
        # Excel文件头检查
        if len(file_content) >= 8:
            # 检查ZIP文件头 (xlsx)
            if file_content[:4] == b'PK\x03\x04':
                return 'excel'
            # 检查OLE文件头 (xls)
            elif file_content[:8] == b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1':
                return 'excel'
            # 检查Office Open XML
            elif b'[Content_Types].xml' in file_content[:2000]:
                return 'excel'
    except:
        pass
    
    # 然后根据扩展名判断
    if file_name_lower.endswith(('.xlsx', '.xls')):
        return 'excel'
    elif file_name_lower.endswith('.csv'):
        return 'csv'
    
    # 最后根据内容特征
    try:
        # 尝试解码为文本，检查是否包含CSV特征
        sample = file_content[:1000].decode('utf-8', errors='ignore')
        lines = sample.split('\n')
        if len(lines) > 1:
            # 检查是否有逗号或分号分隔
            if any(',' in line for line in lines[:3]) or any(';' in line for line in lines[:3]):
                return 'csv'
    except:
        pass
    
    return 'unknown'

def read_file_smart(file_content, file_name):
    """智能读取文件"""
    file_type = detect_file_type_simple(file_content, file_name)
    
    if file_type == 'excel':
        try:
            # 尝试读取Excel
            return pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            # 尝试不同的Excel引擎
            try:
                return pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
            except:
                try:
                    return pd.read_excel(io.BytesIO(file_content), engine='xlrd')
                except:
                    raise ValueError(f"无法读取Excel文件: {str(e)}")
    
    elif file_type == 'csv':
        # 尝试多种编码
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1', 'iso-8859-1', 'cp1252']
        
        for enc in encodings:
            try:
                return pd.read_csv(io.BytesIO(file_content), encoding=enc)
            except Exception:
                continue
        
        # 尝试自动检测编码
        try:
            # 简单编码检测
            text_start = file_content[:1000]
            for enc in ['utf-8', 'gbk', 'latin1']:
                try:
                    text_start.decode(enc)
                    return pd.read_csv(io.BytesIO(file_content), encoding=enc)
                except:
                    continue
        except:
            pass
        
        # 最后的手段
        try:
            return pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
        except Exception as e:
            raise ValueError(f"无法读取CSV文件: {str(e)}")
    
    else:
        # 尝试自动检测
        try:
            return pd.read_excel(io.BytesIO(file_content))
        except:
            try:
                return pd.read_csv(io.BytesIO(file_content))
            except Exception as e:
                raise ValueError(f"无法识别文件类型: {file_name}")

# ==============================================================================
# 简化的引擎包装函数
# ==============================================================================

def run_hedge_engine_simple(paper_content, paper_name, phys_content, phys_name):
    """简化的引擎运行函数"""
    try:
        # 导入引擎
        sys.path.append(os.path.dirname(__file__))
        import hedge_engine as engine
        
        # 读取数据
        df_paper = read_file_smart(paper_content, paper_name)
        df_physical = read_file_smart(phys_content, phys_name)
        
        # 显示数据预览
        st.sidebar.markdown("### 📊 数据预览")
        with st.sidebar.expander("纸货数据"):
            st.write(f"形状: {df_paper.shape}")
            st.write("列:", list(df_paper.columns)[:10])
        
        with st.sidebar.expander("实货数据"):
            st.write(f"形状: {df_physical.shape}")
            st.write("列:", list(df_physical.columns)[:10])
        
        # 运行引擎
        if not df_physical.empty:
            # 先内部净额化纸货
            df_paper_net = engine.calculate_net_positions_corrected(df_paper)
            
            # 实货匹配
            df_rels, df_physical_updated = engine.auto_match_hedges(df_physical, df_paper_net)
            
            # 计算纸货分配情况
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
            
            # 步骤1: 准备数据
            progress_bar.progress(20)
            
            # 获取文件内容
            paper_content = ticket_file.getvalue()
            paper_name = ticket_file.name
            phys_content = phys_file.getvalue()
            phys_name = phys_file.name
            
            # 步骤2: 运行引擎
            progress_bar.progress(50)
            
            start_t = time.time()
            
            # 运行引擎
            df_rels, df_ph_final, df_p_final = run_hedge_engine_simple(
                paper_content, paper_name, phys_content, phys_name
            )
            
            calc_time = time.time() - start_t
            
            # 步骤3: 显示结果
            progress_bar.progress(90)
            
            progress_bar.progress(100)
            
            st.markdown(f'<div class="success-message">分析完成！耗时 {calc_time:.2f} 秒</div>', unsafe_allow_html=True)
            
            # --- 显示结果 ---
            st.markdown("## 📊 分析结果")
            
            if not df_rels.empty:
                st.success(f"✅ 成功匹配 {len(df_rels)} 笔交易")
                
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
                
                # 显示摘要
                col1, col2, col3 = st.columns(3)
                
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
                
            else:
                st.warning("⚠️ 未找到匹配结果")
                
                # 显示原始数据帮助调试
                st.markdown("## 🔍 数据检查")
                
                # 重新读取数据
                df_paper = read_file_smart(paper_content, paper_name)
                df_physical = read_file_smart(phys_content, phys_name)
                
                tab1, tab2 = st.tabs(["纸货数据", "实货数据"])
                
                with tab1:
                    st.write("纸货数据预览:")
                    st.dataframe(df_paper.head(), use_container_width=True)
                    
                    # 检查关键列
                    st.write("关键列检查:")
                    required = ['Trade Date', 'Commodity', 'Month', 'Volume']
                    for col in required:
                        if col in df_paper.columns:
                            st.success(f"✓ {col}")
                        else:
                            st.error(f"✗ {col} (缺失)")
                
                with tab2:
                    st.write("实货数据预览:")
                    st.dataframe(df_physical.head(), use_container_width=True)
                    
                    # 检查关键列
                    st.write("关键列检查:")
                    required = ['Cargo_ID', 'Volume', 'Hedge_Proxy', 'Target_Contract_Month']
                    for col in required:
                        if col in df_physical.columns:
                            st.success(f"✓ {col}")
                        else:
                            st.error(f"✗ {col} (缺失)")
                            
                # 匹配诊断
                st.markdown("### 🔧 匹配诊断")
                
                if 'Commodity' in df_paper.columns and 'Hedge_Proxy' in df_physical.columns:
                    paper_com = set(str(x).upper().strip() for x in df_paper['Commodity'].dropna().unique())
                    phys_proxy = set(str(x).upper().strip() for x in df_physical['Hedge_Proxy'].dropna().unique())
                    
                    common = paper_com.intersection(phys_proxy)
                    
                    if common:
                        st.success(f"✓ 找到共同品种: {list(common)[:5]}")
                    else:
                        st.error(f"✗ 无共同品种！纸货: {list(paper_com)[:5]}，实货: {list(phys_proxy)[:5]}")
            
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            st.markdown('<div class="error-message">错误详情:</div>', unsafe_allow_html=True)
            
            # 显示简化的错误信息
            st.code(str(e))
            
            st.info("💡 常见问题:")
            st.markdown("""
            1. **文件格式问题**: 确保上传的是正确的Excel或CSV文件
            2. **列名问题**: 检查文件是否包含必要的列名
            3. **数据格式**: 检查日期、数字格式是否正确
            4. **文件编码**: CSV文件可能有编码问题
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
    
    ### 📋 必需的列名
    
    **纸货文件**:
    - `Trade Date`: 交易日期
    - `Commodity`: 品种（如 BRENT, WTI）
    - `Month`: 合约月份
    - `Volume`: 交易数量
    
    **实货文件**:
    - `Cargo_ID`: 实货编号
    - `Volume`: 实货数量
    - `Hedge_Proxy`: 对冲品种
    - `Target_Contract_Month`: 目标合约月份
    """)

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9em;">
    <p>Hedge Master Analytics v2.0 | 基于 v19 套保引擎</p>
</div>
""", unsafe_allow_html=True)
