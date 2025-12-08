import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from datetime import datetime
import matplotlib.ticker as ticker
import io

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(layout="wide")
st.title("📊 实货持仓数据分析")

# 文件上传
uploaded_file = st.file_uploader("上传CSV文件", type="csv")

if uploaded_file is not None:
    # 读取CSV文件
    df = pd.read_csv(uploaded_file)
    
    # 清理数据：去除完全为空的行
    df = df.dropna(how='all')
    
    # 清理列名中的不可见字符
    df.columns = df.columns.str.strip()
    
    st.write("### 📋 数据概览")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总记录数", len(df))
    with col2:
        st.metric("数据列数", len(df.columns))
    with col3:
        st.metric("Cargo_ID数量", df['Cargo_ID'].nunique() if 'Cargo_ID' in df.columns else 0)
    
    # 显示前几行数据
    with st.expander("查看数据预览"):
        st.dataframe(df.head())
    
    # 确保Volume列是数值类型
    if 'Volume' in df.columns:
        df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
    
    # 解析日期列
    date_columns = ['Pricing_Start', 'Pricing_End']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', format='mixed')
    
    # 将Target_Pricing_Month转换为月份名称和年份
    def parse_target_month(month_str):
        try:
            if isinstance(month_str, str):
                month_str = month_str.strip()
                # 处理"May 26"这样的格式
                if ' ' in month_str:
                    parts = month_str.split()
                    month_part = parts[0]
                    year_part = parts[1] if len(parts) > 1 else '26'
                else:
                    # 处理"26-Jan"这样的格式
                    if '-' in month_str:
                        parts = month_str.split('-')
                        if len(parts) == 2:
                            year_part = parts[0]
                            month_part = parts[1]
                        else:
                            return None
                    else:
                        return None
                
                # 将月份缩写转换为数字
                month_dict = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                
                if month_part in month_dict:
                    month_num = month_dict[month_part]
                else:
                    month_dict_full = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4,
                        'May': 5, 'June': 6, 'July': 7, 'August': 8,
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    if month_part in month_dict_full:
                        month_num = month_dict_full[month_part]
                    else:
                        return None
                
                year_num = int('20' + year_part) if len(year_part) == 2 else int(year_part)
                return datetime(year_num, month_num, 1)
            return None
        except Exception as e:
            return None
    
    if 'Target_Pricing_Month' in df.columns:
        df['Target_Month_Date'] = df['Target_Pricing_Month'].apply(parse_target_month)
    
    # 侧边栏筛选器
    st.sidebar.header("🔍 筛选选项")
    
    # 商品类型筛选
    if 'Commodity_Type' in df.columns:
        commodity_types = df['Commodity_Type'].dropna().unique().tolist()
        selected_commodities = st.sidebar.multiselect(
            "选择商品类型",
            options=commodity_types,
            default=commodity_types
        )
        
        if selected_commodities:
            filtered_df = df[df['Commodity_Type'].isin(selected_commodities)]
        else:
            filtered_df = df
    else:
        filtered_df = df
    
    # Cargo_ID筛选
    if 'Cargo_ID' in filtered_df.columns:
        cargo_ids = filtered_df['Cargo_ID'].dropna().unique().tolist()
        selected_cargos = st.sidebar.multiselect(
            "选择Cargo_ID",
            options=cargo_ids,
            default=cargo_ids[:5] if len(cargo_ids) > 5 else cargo_ids
        )
        
        if selected_cargos:
            filtered_df = filtered_df[filtered_df['Cargo_ID'].isin(selected_cargos)]
    
    # 显示筛选后的统计
    st.write(f"### 📈 分析结果 (筛选后记录数: {len(filtered_df)})")
    
    if len(filtered_df) > 0:
        # 创建可视化
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('实货持仓分析', fontsize=16, fontweight='bold')
        
        try:
            # 1. 按Target Month的总持仓量
            ax1 = axes[0, 0]
            if 'Target_Month_Date' in filtered_df.columns and 'Volume' in filtered_df.columns:
                monthly_volume = filtered_df.groupby('Target_Month_Date')['Volume'].sum().sort_index()
                
                if not monthly_volume.empty:
                    ax1.fill_between(monthly_volume.index, 0, monthly_volume.values, 
                                    alpha=0.7, color='steelblue', label='总持仓量')
                    ax1.plot(monthly_volume.index, monthly_volume.values, 
                            color='darkblue', linewidth=2, marker='o')
                    ax1.set_xlabel('目标定价月份')
                    ax1.set_ylabel('持仓量')
                    ax1.set_title('按目标月份的总持仓量')
                    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                    ax1.xaxis.set_major_locator(mdates.MonthLocator())
                    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
                    ax1.grid(True, alpha=0.3)
                    ax1.legend()
                else:
                    ax1.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax1.transAxes)
            else:
                ax1.text(0.5, 0.5, '缺少必要数据列', ha='center', va='center', transform=ax1.transAxes)
            
            # 2. 各Cargo_ID的持仓分布
            ax2 = axes[0, 1]
            if 'Cargo_ID' in filtered_df.columns and 'Target_Month_Date' in filtered_df.columns and 'Volume' in filtered_df.columns:
                pivot_table = filtered_df.pivot_table(
                    values='Volume', 
                    index='Target_Month_Date',
                    columns='Cargo_ID',
                    aggfunc='sum',
                    fill_value=0
                ).sort_index()
                
                if not pivot_table.empty and len(pivot_table.columns) > 0:
                    cargo_ids = pivot_table.columns[:min(8, len(pivot_table.columns))]
                    colors = plt.cm.Set3(np.linspace(0, 1, len(cargo_ids)))
                    
                    bottom = np.zeros(len(pivot_table))
                    for i, cargo_id in enumerate(cargo_ids):
                        ax2.bar(pivot_table.index, pivot_table[cargo_id], 
                               bottom=bottom, label=cargo_id, color=colors[i], alpha=0.8)
                        bottom += pivot_table[cargo_id].values
                    
                    ax2.set_xlabel('目标定价月份')
                    ax2.set_ylabel('持仓量')
                    ax2.set_title('各Cargo_ID持仓分布')
                    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                    ax2.xaxis.set_major_locator(mdates.MonthLocator())
                    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
                    ax2.legend(title='Cargo_ID', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
                    ax2.grid(True, alpha=0.3, axis='y')
                else:
                    ax2.text(0.5, 0.5, '无足够数据', ha='center', va='center', transform=ax2.transAxes)
            else:
                ax2.text(0.5, 0.5, '缺少必要数据列', ha='center', va='center', transform=ax2.transAxes)
            
            # 3. 按Pricing Benchmark分类
            ax3 = axes[1, 0]
            if 'Pricing_Benchmark' in filtered_df.columns and 'Volume' in filtered_df.columns:
                benchmark_volume = filtered_df.groupby('Pricing_Benchmark')['Volume'].sum()
                if not benchmark_volume.empty:
                    colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99']
                    ax3.pie(benchmark_volume.values, labels=benchmark_volume.index, 
                           autopct='%1.1f%%', colors=colors[:len(benchmark_volume)],
                           startangle=90, shadow=True)
                    ax3.set_title('按定价基准分类的持仓比例')
                    ax3.axis('equal')
                else:
                    ax3.text(0.5, 0.5, '无足够数据', ha='center', va='center', transform=ax3.transAxes)
            else:
                ax3.text(0.5, 0.5, '缺少必要数据列', ha='center', va='center', transform=ax3.transAxes)
            
            # 4. 主要Cargo_ID的时间序列
            ax4 = axes[1, 1]
            if 'Cargo_ID' in filtered_df.columns and 'Target_Month_Date' in filtered_df.columns and 'Volume' in filtered_df.columns:
                major_cargos = filtered_df['Cargo_ID'].value_counts().index[:min(5, len(filtered_df['Cargo_ID'].unique()))]
                
                for cargo_id in major_cargos:
                    cargo_data = filtered_df[filtered_df['Cargo_ID'] == cargo_id].sort_values('Target_Month_Date')
                    if not cargo_data.empty and len(cargo_data) > 1:
                        ax4.plot(cargo_data['Target_Month_Date'], cargo_data['Volume'], 
                                marker='o', linewidth=2, label=cargo_id)
                
                if len(major_cargos) > 0:
                    ax4.set_xlabel('目标定价月份')
                    ax4.set_ylabel('持仓量')
                    ax4.set_title('主要Cargo_ID持仓量变化趋势')
                    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                    ax4.xaxis.set_major_locator(mdates.MonthLocator())
                    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
                    ax4.legend(fontsize='small')
                    ax4.grid(True, alpha=0.3)
                else:
                    ax4.text(0.5, 0.5, '无足够数据', ha='center', va='center', transform=ax4.transAxes)
            else:
                ax4.text(0.5, 0.5, '缺少必要数据列', ha='center', va='center', transform=ax4.transAxes)
            
            plt.tight_layout()
            st.pyplot(fig)
            
        except Exception as e:
            st.error(f"生成图表时出错: {str(e)}")
        
        # 显示详细统计
        st.write("### 📊 详细统计")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if 'Volume' in filtered_df.columns:
                total_volume = filtered_df['Volume'].sum()
                avg_volume = filtered_df['Volume'].mean()
                st.metric("总持仓量", f"{total_volume:,.0f}")
                st.metric("平均持仓量", f"{avg_volume:,.0f}")
        
        with col2:
            if 'Pricing_Benchmark' in filtered_df.columns:
                st.write("**定价基准分布:**")
                benchmark_counts = filtered_df['Pricing_Benchmark'].value_counts()
                st.write(benchmark_counts)
        
        # 显示数据表格
        with st.expander("查看详细数据"):
            st.dataframe(filtered_df)
        
        # 下载处理后的数据
        @st.cache_data
        def convert_df(df):
            return df.to_csv(index=False).encode('utf-8')
        
        csv = convert_df(filtered_df)
        
        st.download_button(
            label="📥 下载处理后的数据",
            data=csv,
            file_name="processed_cargo_data.csv",
            mime="text/csv"
        )
        
    else:
        st.warning("筛选后无数据，请调整筛选条件")
        
else:
    st.info("👆 请上传CSV文件开始分析")
    st.markdown("""
    ### 使用说明：
    1. 点击"Browse files"按钮上传你的实货持仓CSV文件
    2. 文件应包含以下列（至少）：
       - Cargo_ID
       - Commodity_Type
       - Volume
       - Target_Pricing_Month
       - Pricing_Benchmark
    3. 上传后系统会自动分析并生成可视化图表
    
    ### 示例文件格式：
    ```
    Cargo_ID,Commodity_Type,Volume,Target_Pricing_Month,Pricing_Benchmark
    PHY-2026-001,Crude Oil,250000,26-Jan,JCC
    PHY-2026-002,Crude Oil,480000,26-Feb,Brent
    ```
    """)
