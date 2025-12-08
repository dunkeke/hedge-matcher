import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import time
import io

# ==============================================================================
# 导入核心引擎 (模块化调用)
# ==============================================================================
try:
    import hedge_engine as engine
except ImportError:
    st.error("❌ 严重错误: 找不到 hedge_engine.py 模块！请确保该文件在同一目录下。")
    st.stop()

# ==============================================================================
# Streamlit UI
# ==============================================================================

st.set_page_config(page_title="Hedge Master Analytics", page_icon="📈", layout="wide")

# CSS 样式
st.markdown("""
<style>
    .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

col_title = st.columns([1])[0]
with col_title:
    st.title("Hedge Master Analytics 📊")
    st.markdown("**基于 v22 引擎 (模块化版) 的智能套保有效性分析系统**")

st.divider()

# --- 侧边栏 ---
with st.sidebar:
    st.header("📂 数据接入")
    ticket_file = st.file_uploader("上传纸货水单 (Ticket Data)", type=['xlsx', 'csv'])
    phys_file = st.file_uploader("上传实货台账 (Physical Ledger)", type=['xlsx', 'csv'])
    
    st.markdown("---")
    run_btn = st.button("🚀 开始全景分析", type="primary", use_container_width=True)
    st.caption("Engine: hedge_engine.py v22")

# --- 主逻辑 ---
if run_btn:
    if ticket_file and phys_file:
        with st.spinner('正在调用 hedge_engine 执行计算...'):
            try:
                # 1. 加载 (直接传 Streamlit 的 UploadedFile 对象给引擎的 read_file_fast)
                # 注意：read_file_fast 需要支持 seek(0)
                # 引擎里的 load_data_v19 调用了 read_file_fast
                df_p, df_ph = engine.load_data_v19(ticket_file, phys_file)
                
                if not df_ph.empty and not df_p.empty:
                    # 2. 核心计算
                    start_t = time.time()
                    
                    # Step 1: 净仓
                    df_p_net = engine.calculate_net_positions_corrected(df_p)
                    
                    # Step 2: 匹配
                    df_rels, df_ph_final, df_p_final = engine.auto_match_hedges(df_ph, df_p_net)
                    
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
                    tab1, tab2, tab3 = st.tabs(["✅ 匹配明细", "⚠️ 实货剩余", "📦 纸货剩余"])
                    
                    with tab1:
                        if not df_rels.empty:
                            st.dataframe(df_rels, use_container_width=True)
                            csv = df_rels.to_csv(index=False).encode('utf-8')
                            st.download_button("📥 下载明细 CSV", csv, "hedge_allocation.csv", "text/csv")
                        else:
                            st.info("无匹配记录")
                            
                    with tab2:
                        st.dataframe(df_ph_final[abs(df_ph_final['Unhedged_Volume']) > 1], use_container_width=True)
                        
                    with tab3:
                        if 'Allocated_To_Phy' in df_p_final.columns:
                            df_p_final['Implied_Remaining'] = df_p_final['Volume'] - df_p_final['Allocated_To_Phy']
                            unused = df_p_final[abs(df_p_final['Implied_Remaining']) > 1]
                            cols_show = ['Recap No', 'Std_Commodity', 'Month', 'Volume', 'Allocated_To_Phy', 'Implied_Remaining', 'Price']
                            final_cols = [c for c in cols_show if c in unused.columns]
                            st.dataframe(unused[final_cols], use_container_width=True)
                        else:
                            st.error("无法计算剩余纸货 (列丢失)")
                else:
                    st.error("数据加载后为空")
            except Exception as e:
                st.error(f"运行时错误: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
    else:
        st.warning("请上传文件")