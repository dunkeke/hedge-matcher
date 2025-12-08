import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.dates as mdates
from datetime import datetime
import matplotlib.ticker as ticker
import matplotlib.font_manager as fm

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 读取CSV文件
file_path = 'physical_cargo_ledger.csv'
df = pd.read_csv(file_path)

# 清理数据：去除完全为空的行
df = df.dropna(how='all')

# 清理列名中的不可见字符
df.columns = df.columns.str.strip()

print("数据列名:", df.columns.tolist())
print(f"数据行数: {len(df)}")
print(f"数据预览:")
print(df.head())
print("\n数据类型:")
print(df.dtypes)

# 检查是否有数据
if df.empty:
    print("数据框为空！")
else:
    # 确保Volume列是数值类型
    df['Volume'] = pd.to_numeric(df['Volume'], errors='coerce')
    
    # 解析日期列
    date_columns = ['Pricing_Start', 'Pricing_End']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce', format='mixed')
    
    # 检查Target_Pricing_Month格式并解析
    print("\nTarget_Pricing_Month唯一值:")
    print(df['Target_Pricing_Month'].unique())
    
    # 将Target_Pricing_Month转换为月份名称和年份
    def parse_target_month(month_str):
        try:
            # 处理各种格式
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
                
                # 尝试从缩写获取月份
                if month_part in month_dict:
                    month_num = month_dict[month_part]
                else:
                    # 尝试从完整月份名称获取
                    month_dict_full = {
                        'January': 1, 'February': 2, 'March': 3, 'April': 4,
                        'May': 5, 'June': 6, 'July': 7, 'August': 8,
                        'September': 9, 'October': 10, 'November': 11, 'December': 12
                    }
                    if month_part in month_dict_full:
                        month_num = month_dict_full[month_part]
                    else:
                        return None
                
                # 处理年份（假设20xx格式）
                year_num = int('20' + year_part) if len(year_part) == 2 else int(year_part)
                
                return datetime(year_num, month_num, 1)
            return None
        except Exception as e:
            print(f"解析'{month_str}'时出错: {e}")
            return None
    
    df['Target_Month_Date'] = df['Target_Pricing_Month'].apply(parse_target_month)
    
    # 过滤掉原油数据
    crude_df = df[df['Commodity_Type'] == 'Crude Oil'].copy()
    
    print(f"\n原油数据行数: {len(crude_df)}")
    
    if not crude_df.empty:
        # 按Cargo_ID分组查看数据
        cargo_groups = crude_df.groupby('Cargo_ID')
        print(f"\nCargo_ID数量: {len(cargo_groups)}")
        
        for cargo_id, group in list(cargo_groups)[:3]:  # 只显示前3个
            print(f"\nCargo_ID: {cargo_id}")
            print(f"记录数: {len(group)}")
            print(group[['Target_Pricing_Month', 'Volume', 'Pricing_Start', 'Pricing_End']].head())
    
    # 创建可视化
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('原油实货持仓分析', fontsize=16, fontweight='bold')
    
    # 1. 按Target Month的总持仓量（堆积面积图）
    ax1 = axes[0, 0]
    if not crude_df.empty and 'Target_Month_Date' in crude_df.columns:
        # 按月份分组并计算总持仓
        monthly_volume = crude_df.groupby('Target_Month_Date')['Volume'].sum().sort_index()
        
        if not monthly_volume.empty:
            ax1.fill_between(monthly_volume.index, 0, monthly_volume.values, 
                            alpha=0.7, color='steelblue', label='总持仓量')
            ax1.plot(monthly_volume.index, monthly_volume.values, 
                    color='darkblue', linewidth=2, marker='o')
            ax1.set_xlabel('目标定价月份')
            ax1.set_ylabel('持仓量 (BBL)')
            ax1.set_title('按目标月份的总持仓量')
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax1.xaxis.set_major_locator(mdates.MonthLocator())
            plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
            ax1.grid(True, alpha=0.3)
            ax1.legend()
        else:
            ax1.text(0.5, 0.5, '无原油数据', ha='center', va='center', transform=ax1.transAxes)
    else:
        ax1.text(0.5, 0.5, '无原油数据', ha='center', va='center', transform=ax1.transAxes)
    
    # 2. 各Cargo_ID的持仓分布（堆积柱状图）
    ax2 = axes[0, 1]
    if not crude_df.empty:
        # 按Cargo_ID和Target Month分组
        pivot_table = crude_df.pivot_table(
            values='Volume', 
            index='Target_Month_Date',
            columns='Cargo_ID',
            aggfunc='sum',
            fill_value=0
        ).sort_index()
        
        if not pivot_table.empty:
            # 只取前5个Cargo_ID显示
            cargo_ids = pivot_table.columns[:5]
            colors = plt.cm.Set3(np.linspace(0, 1, len(cargo_ids)))
            
            bottom = np.zeros(len(pivot_table))
            for i, cargo_id in enumerate(cargo_ids):
                if cargo_id in pivot_table.columns:
                    ax2.bar(pivot_table.index, pivot_table[cargo_id], 
                           bottom=bottom, label=cargo_id, color=colors[i], alpha=0.8)
                    bottom += pivot_table[cargo_id].values
            
            ax2.set_xlabel('目标定价月份')
            ax2.set_ylabel('持仓量 (BBL)')
            ax2.set_title('各Cargo_ID持仓分布（堆积柱状图）')
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator())
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
            ax2.legend(title='Cargo_ID', bbox_to_anchor=(1.05, 1), loc='upper left')
            ax2.grid(True, alpha=0.3, axis='y')
        else:
            ax2.text(0.5, 0.5, '无足够数据', ha='center', va='center', transform=ax2.transAxes)
    else:
        ax2.text(0.5, 0.5, '无原油数据', ha='center', va='center', transform=ax2.transAxes)
    
    # 3. 按Pricing Benchmark分类（饼图）
    ax3 = axes[1, 0]
    if not crude_df.empty:
        benchmark_volume = crude_df.groupby('Pricing_Benchmark')['Volume'].sum()
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
        ax3.text(0.5, 0.5, '无原油数据', ha='center', va='center', transform=ax3.transAxes)
    
    # 4. 持仓量时间序列（折线图）
    ax4 = axes[1, 1]
    if not crude_df.empty and 'Target_Month_Date' in crude_df.columns:
        # 按Cargo_ID分组，展示主要Cargo_ID的时间序列
        major_cargos = crude_df['Cargo_ID'].value_counts().index[:3]
        
        for cargo_id in major_cargos:
            cargo_data = crude_df[crude_df['Cargo_ID'] == cargo_id].sort_values('Target_Month_Date')
            if not cargo_data.empty and len(cargo_data) > 1:
                ax4.plot(cargo_data['Target_Month_Date'], cargo_data['Volume'], 
                        marker='o', linewidth=2, label=cargo_id)
        
        ax4.set_xlabel('目标定价月份')
        ax4.set_ylabel('持仓量 (BBL)')
        ax4.set_title('主要Cargo_ID持仓量变化趋势')
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax4.xaxis.set_major_locator(mdates.MonthLocator())
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
        ax4.legend()
        ax4.grid(True, alpha=0.3)
    else:
        ax4.text(0.5, 0.5, '无足够数据', ha='center', va='center', transform=ax4.transAxes)
    
    plt.tight_layout()
    plt.show()
    
    # 打印统计信息
    print("\n=== 数据统计 ===")
    print(f"总记录数: {len(df)}")
    print(f"原油记录数: {len(crude_df)}")
    print(f"天然气记录数: {len(df[df['Commodity_Type'] == 'Natural Gas'])}")
    
    if not crude_df.empty:
        print(f"\n原油总持仓量: {crude_df['Volume'].sum():,.0f} BBL")
        print(f"原油平均单笔持仓: {crude_df['Volume'].mean():,.0f} BBL")
        print(f"涉及Cargo_ID数量: {crude_df['Cargo_ID'].nunique()}")
        print(f"定价基准分布:")
        print(crude_df['Pricing_Benchmark'].value_counts())
        
        # 按月份统计
        if 'Target_Month_Date' in crude_df.columns:
            print(f"\n按目标月份统计:")
            monthly_stats = crude_df.groupby(crude_df['Target_Month_Date'].dt.strftime('%Y-%m'))['Volume'].agg(['sum', 'count'])
            print(monthly_stats)
