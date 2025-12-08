import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(layout="wide")
st.title("实货持仓数据分析")

# 读取CSV文件
file_path = 'physical_cargo_ledger.csv'
df = pd.read_csv(file_path)

# 清理数据：去除完全为空的行
df = df.dropna(how='all')

# 清理列名中的不可见字符
df.columns = df.columns.str.strip()

st.write("### 数据概览")
st.write(f"总记录数: {len(df)}")
st.write(f"数据列: {', '.join(df.columns.tolist())}")

# 数据显示选项
with st.sidebar:
    st.header("筛选选项")
    commodity_type = st.multiselect(
        "选择商品类型",
        options=df['Commodity_Type'].unique().tolist() if 'Commodity_Type' in df.columns else [],
        default=df['Commodity_Type'].unique().tolist() if 'Commodity_Type' in df.columns else []
    )
    
    show_raw_data = st.checkbox("显示原始数据")

# 筛选数据
if 'Commodity_Type' in df.columns and commodity_type:
    filtered_df = df[df['Commodity_Type'].isin(commodity_type)]
else:
    filtered_df = df

# 确保Volume列是数值类型
if 'Volume' in filtered_df.columns:
    filtered_df['Volume'] = pd.to_numeric(filtered_df['Volume'], errors='coerce')

# 解析Target_Pricing_Month
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
            return f"{year_num}-{month_num:02d}"
        return None
    except:
        return None

if 'Target_Pricing_Month' in filtered_df.columns:
    filtered_df['Target_Month_Parsed'] = filtered_df['Target_Pricing_Month'].apply(parse_target_month)

# 显示统计数据
st.write("### 统计摘要")

col1, col2, col3 = st.columns(3)

with col1:
    if 'Commodity_Type' in filtered_df.columns:
        commodity_counts = filtered_df['Commodity_Type'].value_counts()
        st.metric("商品类型数量", len(commodity_counts))
        
with col2:
    if 'Cargo_ID' in filtered_df.columns:
        st.metric("唯一Cargo_ID数量", filtered_df['Cargo_ID'].nunique())
        
with col3:
    if 'Volume' in filtered_df.columns:
        total_volume = filtered_df['Volume'].sum()
        st.metric("总持仓量", f"{total_volume:,.0f}")

# 按商品类型显示数据
if 'Commodity_Type' in filtered_df.columns:
    for commodity in filtered_df['Commodity_Type'].unique():
        st.write(f"#### {commodity}")
        commodity_df = filtered_df[filtered_df['Commodity_Type'] == commodity]
        
        # 创建表格展示
        if 'Target_Month_Parsed' in commodity_df.columns and 'Cargo_ID' in commodity_df.columns:
            pivot_table = commodity_df.pivot_table(
                values='Volume' if 'Volume' in commodity_df.columns else None,
                index='Target_Month_Parsed',
                columns='Cargo_ID',
                aggfunc='sum',
                fill_value=0
            )
            
            if not pivot_table.empty:
                st.dataframe(pivot_table.style.format("{:,.0f}"), use_container_width=True)
                
                # 计算总计
                totals = pivot_table.sum()
                st.write(f"**总计:**")
                for cargo_id, total in totals.items():
                    st.write(f"- {cargo_id}: {total:,.0f}")

# 显示原始数据
if show_raw_data:
    st.write("### 原始数据")
    st.dataframe(filtered_df, use_container_width=True)

# 下载处理后的数据
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

csv_data = convert_df_to_csv(filtered_df)
st.download_button(
    label="下载处理后的数据为CSV",
    data=csv_data,
    file_name="processed_cargo_data.csv",
    mime="text/csv"
)
