import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io
import os
import sys
import tempfile
import mimetypes
import magic

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

def detect_file_type(file_content, file_name):
    """检测文件的真实类型"""
    # 首先根据文件内容特征判断
    try:
        # 尝试检测Excel文件特征
        if file_content[:8] == b'\x50\x4b\x03\x04':  # ZIP header (Excel是ZIP文件)
            return 'excel'
        elif file_content[:4] == b'\xd0\xcf\x11\xe0':  # OLE header (旧版Excel)
            return 'excel'
        elif b'<worksheet' in file_content[:1000] or b'<Workbook' in file_content[:1000]:
            return 'excel'
    except:
        pass
    
    # 然后尝试根据扩展名判断
    file_name_lower = file_name.lower()
    if file_name_lower.endswith(('.xlsx', '.xls')):
        return 'excel'
    elif file_name_lower.endswith('.csv'):
        return 'csv'
    
    # 最后根据内容特征判断CSV
    try:
        # 检查是否包含逗号分隔符
        sample = file_content[:1000].decode('utf-8', errors='ignore')
        if ',' in sample or ';' in sample:
            return 'csv'
    except:
        pass
    
    return 'unknown'

def read_file_with_correct_type(file_content, file_name):
    """使用正确的类型读取文件"""
    file_type = detect_file_type(file_content, file_name)
    
    if file_type == 'excel':
        try:
            return pd.read_excel(io.BytesIO(file_content))
        except Exception as e:
            st.warning(f"Excel读取失败，尝试其他方法: {e}")
            # 尝试读取第一个sheet
            try:
                return pd.read_excel(io.BytesIO(file_content), sheet_name=0)
            except:
                # 尝试使用openpyxl引擎
                try:
                    return pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
                except:
                    raise ValueError(f"无法读取Excel文件: {file_name}")
    
    elif file_type == 'csv':
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1', 'iso-8859-1', 'cp1252']
        
        for enc in encodings:
            try:
                return pd.read_csv(io.BytesIO(file_content), encoding=enc)
            except Exception:
                continue
        
        # 如果所有编码都失败，尝试自动检测
        try:
            import chardet
            result = chardet.detect(file_content)
            return pd.read_csv(io.BytesIO(file_content), encoding=result['encoding'])
        except ImportError:
            # 最后的手段
            try:
                return pd.read_csv(io.BytesIO(file_content), encoding='utf-8', errors='ignore')
            except Exception as e:
                raise ValueError(f"无法读取CSV文件: {e}")
        except Exception as e:
            raise ValueError(f"无法读取CSV文件: {e}")
    
    else:
        raise ValueError(f"无法识别的文件类型: {file_name}")

def save_file_with_correct_extension(file_content, file_name, temp_dir):
    """根据文件类型保存为正确扩展名的文件"""
    file_type = detect_file_type(file_content, file_name)
    
    if file_type == 'excel':
        ext = '.xlsx' if file_name.lower().endswith('.xlsx') else '.xls'
        temp_path = os.path.join(temp_dir, f"paper_data{ext}")
    else:
        temp_path = os.path.join(temp_dir, "paper_data.csv")
    
    with open(temp_path, "wb") as f:
        f.write(file_content)
    
    return temp_path

# ==============================================================================
# 修复的引擎包装函数
# ==============================================================================

def run_hedge_engine_directly(paper_content, paper_name, phys_content, phys_name):
    """直接运行对冲引擎"""
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存文件（使用正确的扩展名）
        paper_path = save_file_with_correct_extension(paper_content, paper_name, temp_dir)
        phys_path = save_file_with_correct_extension(phys_content, phys_name, temp_dir)
        
        # 导入引擎
        sys.path.append(os.path.dirname(__file__))
        import hedge_engine as engine
        
        # 手动读取数据（绕过引擎的文件读取）
        df_paper = read_file_with_correct_type(paper_content, paper_name)
        df_physical = read_file_with_correct_type(phys_content, phys_name)
        
        # 预处理数据以匹配引擎的格式
        # 纸货数据预处理
        if 'Trade Date' in df_paper.columns:
            df_paper['Trade Date'] = pd.to_datetime(df_paper['Trade Date'], errors='coerce')
        
        df_paper['Volume'] = pd.to_numeric(df_paper['Volume'], errors='coerce').fillna(0)
        
        if 'Commodity' in df_paper.columns:
            df_paper['Std_Commodity'] = df_paper['Commodity'].astype(str).str.strip().str.upper().replace('NAN', '')
        elif 'Std_Commodity' in df_paper.columns:
            df_paper['Std_Commodity'] = df_paper['Std_Commodity'].astype(str).str.strip().str.upper().replace('NAN', '')
        
        # 月份标准化
        if 'Month' in df_paper.columns:
            df_paper['Month'] = engine.standardize_month_vectorized(df_paper['Month'])
        else:
            df_paper['Month'] = ''
        
        # Recap No 若不存在则用索引代替
        if 'Recap No' not in df_paper.columns:
            df_paper['Recap No'] = df_paper.index.astype(str)
        
        df_paper['_original_index'] = df_paper.index
        
        # 初始化缺失金融字段
        for col in ['Price', 'Mtm Price', 'Total P/L']:
            if col not in df_paper.columns:
                df_paper[col] = 0
        
        # 实货数据预处理
        col_map = {'Target_Pricing_Month': 'Target_Contract_Month', 'Month': 'Target_Contract_Month'}
        df_physical.rename(columns=col_map, inplace=True)
        
        df_physical['Volume'] = pd.to_numeric(df_physical['Volume'], errors='coerce').fillna(0)
        df_physical['Unhedged_Volume'] = df_physical['Volume']
        
        if 'Hedge_Proxy' in df_physical.columns:
            df_physical['Hedge_Proxy'] = df_physical['Hedge_Proxy'].astype(str).str.strip().str.upper().replace('NAN', '')
        else:
            df_physical['Hedge_Proxy'] = ''
        
        # 合约月标准化
        if 'Target_Contract_Month' in df_physical.columns:
            df_physical['Target_Contract_Month'] = engine.standardize_month_vectorized(df_physical['Target_Contract_Month'])
        
        # 指定日期
        date_cols = ['Designation_Date', 'Pricing_Start', 'Trade_Date']
        date_col_found = None
        for col in date_cols:
            if col in df_physical.columns:
                date_col_found = col
                break
        
        if date_col_found:
            df_physical['Designation_Date'] = pd.to_datetime(df_physical[date_col_found], errors='coerce')
        else:
            df_physical['Designation_Date'] = pd.NaT
        
        # 运行引擎核心函数
        if not df_physical.empty:
            # 先内部净额化纸货
            df_paper_net = engine.calculate_net_positions_corrected(df_paper)
            
            # 实货匹配
            df_rels, df_physical_updated = engine.auto_match_hedges(df_physical, df_paper_net)
            
            # 计算纸货分配情况
            df_paper_final = df_paper_net.copy()
            if 'Allocated_To_Phy' not in df_paper_final.columns:
                df_paper_final['Allocated_To_Phy'] = 0
            
            if not df_rels.empty and 'Ticket_ID' in df_rels.columns:
                # 汇总分配量
                alloc_summary = df_rels.groupby('Ticket_ID')['Allocated_Vol'].sum().reset_index()
                alloc_summary.rename(columns={'Allocated_Vol': 'Allocated_To_Phy'}, inplace=True)
                
                # 合并分配量到纸货数据
                if 'Recap No' in df_paper_final.columns:
                    df_paper_final = pd.merge(
                        df_paper_final, 
                        alloc_summary, 
                        left_on='Recap No', 
                        right_on='Ticket_ID', 
                        how='left'
                    )
                    df_paper_final['Allocated_To_Phy'] = df_paper_final['Allocated_To_Phy'].fillna(0)
                    
                    # 清理临时列
                    if 'Ticket_ID' in df_paper_final.columns:
                        df_paper_final = df_paper_final.drop(columns=['Ticket_ID'])
            
            return df_rels, df_physical_updated, df_paper_final
        else:
            return pd.DataFrame(), df_physical, df_paper
            
    except Exception as e:
        raise e
    finally:
        # 清理临时文件
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

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
    
    # 显示文件信息
    if ticket_file:
        file_type = detect_file_type(ticket_file.getvalue(), ticket_file.name)
        st.info(f"📄 纸货文件: {ticket_file.name} ({file_type.upper()}, {ticket_file.size:,} bytes)")
    
    if phys_file:
        file_type = detect_file_type(phys_file.getvalue(), phys_file.name)
        st.info(f"📦 实货文件: {phys_file.name} ({file_type.upper()}, {phys_file.size:,} bytes)")
    
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

# ==============================================================================
# 主内容区域
# ==============================================================================

if run_btn and ticket_file and phys_file:
    with st.spinner('正在执行匹配运算...'):
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 步骤1: 准备数据
            status_text.text("步骤 1/3: 准备数据文件...")
            progress_bar.progress(20)
            
            # 获取文件内容
            paper_content = ticket_file.getvalue()
            paper_name = ticket_file.name
            phys_content = phys_file.getvalue()
            phys_name = phys_file.name
            
            # 步骤2: 运行引擎
            status_text.text("步骤 2/3: 执行套保匹配引擎...")
            progress_bar.progress(50)
            
            start_t = time.time()
            
            # 直接运行引擎
            df_rels, df_ph_final, df_p_final = run_hedge_engine_directly(
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
            st.markdown("## 📊 分析结果摘要")
            
            if not df_rels.empty:
                st.success(f"✅ 成功匹配 {len(df_rels)} 笔交易")
                
                # 显示关键指标
                if 'Allocated_Vol' in df_rels.columns:
                    total_allocated = df_rels['Allocated_Vol'].abs().sum()
                    
                    # 计算实货总敞口
                    if 'Volume' in df_ph_final.columns:
                        total_exposure = df_ph_final['Volume'].abs().sum()
                        coverage_rate = (total_allocated / total_exposure * 100) if total_exposure > 0 else 0
                    else:
                        total_exposure = 0
                        coverage_rate = 0
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("实货总敞口", f"{total_exposure:,.0f} BBL")
                    
                    with col2:
                        st.metric("套保覆盖率", f"{coverage_rate:.1f}%", f"{total_allocated:,.0f} BBL")
                    
                    with col3:
                        if 'Alloc_Unrealized_MTM' in df_rels.columns:
                            total_mtm = df_rels['Alloc_Unrealized_MTM'].sum()
                            st.metric("套保组合 MTM", f"${total_mtm:,.0f}")
                    
                    with col4:
                        if 'Alloc_Total_PL' in df_rels.columns:
                            total_pl = df_rels['Alloc_Total_PL'].sum()
                            st.metric("套保组合 P/L", f"${total_pl:,.0f}")
                
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
                
                # 显示匹配统计
                st.markdown("### 📈 匹配统计")
                
                tab1, tab2, tab3 = st.tabs(["按品种", "按月份", "按日期"])
                
                with tab1:
                    if 'Proxy' in df_rels.columns:
                        proxy_summary = df_rels.groupby('Proxy')['Allocated_Vol'].agg(['sum', 'count']).reset_index()
                        proxy_summary.columns = ['品种', '匹配量', '匹配笔数']
                        proxy_summary = proxy_summary.sort_values('匹配量', ascending=False)
                        
                        fig = px.bar(proxy_summary, x='品种', y='匹配量', 
                                    title="各品种匹配量", color='品种')
                        st.plotly_chart(fig, use_container_width=True)
                
                with tab2:
                    if 'Month' in df_rels.columns:
                        month_summary = df_rels.groupby('Month')['Allocated_Vol'].agg(['sum', 'count']).reset_index()
                        month_summary.columns = ['合约月', '匹配量', '匹配笔数']
                        month_summary = month_summary.sort_values('合约月')
                        
                        fig = px.bar(month_summary, x='合约月', y='匹配量', 
                                    title="各合约月匹配量", color='合约月')
                        st.plotly_chart(fig, use_container_width=True)
                
                with tab3:
                    if 'Open_Date' in df_rels.columns:
                        # 按日期统计
                        df_rels['Open_Date'] = pd.to_datetime(df_rels['Open_Date'])
                        date_summary = df_rels.groupby(df_rels['Open_Date'].dt.date)['Allocated_Vol'].sum().reset_index()
                        date_summary.columns = ['日期', '匹配量']
                        date_summary = date_summary.sort_values('日期')
                        
                        fig = px.line(date_summary, x='日期', y='匹配量', 
                                     title="每日匹配量趋势", markers=True)
                        st.plotly_chart(fig, use_container_width=True)
                
            else:
                st.warning("⚠️ 未找到匹配结果")
                
                # 显示数据诊断
                st.markdown("## 🔍 数据诊断")
                
                # 读取原始数据用于诊断
                df_paper_original = read_file_with_correct_type(paper_content, paper_name)
                df_phys_original = read_file_with_correct_type(phys_content, phys_name)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📄 纸货数据")
                    st.write(f"数据形状: {df_paper_original.shape}")
                    
                    # 检查关键列
                    required_paper_cols = ['Trade Date', 'Commodity', 'Month', 'Volume']
                    missing_paper = [col for col in required_paper_cols if col not in df_paper_original.columns]
                    
                    if missing_paper:
                        st.error(f"缺失列: {missing_paper}")
                    else:
                        st.success("✓ 关键列完整")
                        
                        # 显示数据摘要
                        st.write("数据摘要:")
                        summary_data = {
                            '指标': ['总交易数', '总交易量', '品种数', '合约月数'],
                            '数值': [
                                len(df_paper_original),
                                f"{df_paper_original['Volume'].sum():,.0f}",
                                df_paper_original['Commodity'].nunique(),
                                df_paper_original['Month'].nunique()
                            ]
                        }
                        st.table(pd.DataFrame(summary_data))
                
                with col2:
                    st.subheader("📦 实货数据")
                    st.write(f"数据形状: {df_phys_original.shape}")
                    
                    # 检查关键列
                    required_phys_cols = ['Cargo_ID', 'Volume', 'Hedge_Proxy', 'Target_Contract_Month']
                    missing_phys = [col for col in required_phys_cols if col not in df_phys_original.columns]
                    
                    if missing_phys:
                        st.error(f"缺失列: {missing_phys}")
                        
                        # 显示可用列
                        st.write("可用列:")
                        st.write(list(df_phys_original.columns))
                    else:
                        st.success("✓ 关键列完整")
                        
                        # 显示数据摘要
                        st.write("数据摘要:")
                        summary_data = {
                            '指标': ['实货笔数', '总敞口', '对冲品种数', '目标合约月数'],
                            '数值': [
                                len(df_phys_original),
                                f"{df_phys_original['Volume'].sum():,.0f}",
                                df_phys_original['Hedge_Proxy'].nunique(),
                                df_phys_original['Target_Contract_Month'].nunique()
                            ]
                        }
                        st.table(pd.DataFrame(summary_data))
                
                # 匹配诊断
                st.markdown("### 🔧 匹配诊断")
                
                if 'Commodity' in df_paper_original.columns and 'Hedge_Proxy' in df_phys_original.columns:
                    paper_commodities = set(df_paper_original['Commodity'].astype(str).str.upper().str.strip().unique())
                    phys_proxies = set(df_phys_original['Hedge_Proxy'].astype(str).str.upper().str.strip().unique())
                    
                    common = paper_commodities.intersection(phys_proxies)
                    
                    if common:
                        st.success(f"✓ 找到 {len(common)} 个共同品种: {list(common)[:5]}")
                    else:
                        st.error(f"✗ 没有共同品种！纸货品种: {list(paper_commodities)[:5]}，实货品种: {list(phys_proxies)[:5]}")
                
                if 'Month' in df_paper_original.columns and 'Target_Contract_Month' in df_phys_original.columns:
                    paper_months = set(df_paper_original['Month'].astype(str).str.upper().str.strip().unique())
                    phys_months = set(df_phys_original['Target_Contract_Month'].astype(str).str.upper().str.strip().unique())
                    
                    common_months = paper_months.intersection(phys_months)
                    
                    if common_months:
                        st.success(f"✓ 找到 {len(common_months)} 个共同合约月: {list(common_months)[:5]}")
                    else:
                        st.error(f"✗ 没有共同合约月！")
            
            # --- 显示剩余数据 ---
            st.markdown("## 📊 剩余敞口分析")
            
            tab_phy, tab_paper = st.tabs(["实货剩余", "纸货剩余"])
            
            with tab_phy:
                if not df_ph_final.empty and 'Unhedged_Volume' in df_ph_final.columns:
                    remaining_phy = df_ph_final[abs(df_ph_final['Unhedged_Volume']) > 0.1].copy()
                    
                    if not remaining_phy.empty:
                        st.info(f"还有 {len(remaining_phy)} 笔实货存在未对冲敞口")
                        
                        # 计算剩余敞口
                        total_remaining = remaining_phy['Unhedged_Volume'].abs().sum()
                        st.metric("总剩余敞口", f"{total_remaining:,.0f} BBL")
                        
                        # 显示剩余实货
                        display_cols = ['Cargo_ID', 'Volume', 'Unhedged_Volume', 'Hedge_Proxy', 'Target_Contract_Month']
                        available_cols = [col for col in display_cols if col in remaining_phy.columns]
                        
                        if available_cols:
                            st.dataframe(remaining_phy[available_cols], use_container_width=True)
                    else:
                        st.success("🎉 所有实货敞口均已完全对冲！")
                else:
                    st.info("无实货剩余数据")
            
            with tab_paper:
                if not df_p_final.empty and 'Allocated_To_Phy' in df_p_final.columns:
                    # 计算剩余量
                    df_p_final['Remaining'] = df_p_final['Volume'] - df_p_final['Allocated_To_Phy']
                    remaining_paper = df_p_final[abs(df_p_final['Remaining']) > 0.1].copy()
                    
                    if not remaining_paper.empty:
                        st.info(f"还有 {len(remaining_paper)} 笔纸货交易未完全分配")
                        
                        # 计算剩余纸货
                        total_remaining = remaining_paper['Remaining'].abs().sum()
                        st.metric("总剩余纸货", f"{total_remaining:,.0f} BBL")
                        
                        # 显示剩余纸货
                        display_cols = ['Recap No', 'Std_Commodity', 'Month', 'Volume', 'Allocated_To_Phy', 'Remaining']
                        available_cols = [col for col in display_cols if col in remaining_paper.columns]
                        
                        if available_cols:
                            st.dataframe(remaining_paper[available_cols], use_container_width=True)
                    else:
                        st.success("📊 所有纸货交易均已完全分配！")
                else:
                    st.info("无纸货剩余数据")
                
        except Exception as e:
            st.error(f"❌ 运行时错误: {str(e)}")
            st.markdown('<div class="error-message">错误详情:</div>', unsafe_allow_html=True)
            import traceback
            st.code(traceback.format_exc())
            
            st.info("💡 调试建议:")
            st.markdown("""
            1. 检查上传文件格式是否正确
            2. 确保文件包含引擎需要的列名
            3. 检查数据中是否有空值或格式错误
            4. 检查文件编码
            """)
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
