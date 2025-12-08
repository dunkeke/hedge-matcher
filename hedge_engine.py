import pandas as pd
import numpy as np
import os
import time
import warnings
from datetime import datetime
from collections import deque

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------
# 1. 基础工具 (Utils)
# ---------------------------------------------------------

def read_file_fast(file_path):
    """
    读取文件，支持 csv 和 Excel 格式，自动尝试不同编码。
    如果无法找到提供的文件，会尝试寻找相同文件名不同扩展名的文件。
    """
    if not os.path.exists(file_path):
        base, ext = os.path.splitext(file_path)
        alt_ext = '.csv' if ext in ['.xlsx', '.xls'] else '.xlsx'
        alt_path = base + alt_ext
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            raise FileNotFoundError(f"未找到文件: {file_path}")

    print(f"正在读取文件: {os.path.basename(file_path)}...")
    # 先尝试读取 Excel
    if file_path.lower().endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(file_path)
        except Exception:
            pass
    # 尝试不同编码读取 CSV
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin1']
    for enc in encodings:
        try:
            return pd.read_csv(file_path, encoding=enc)
        except Exception:
            continue
    raise ValueError(f"无法识别文件编码: {file_path}")

def clean_str(series):
    """
    清洗字符串：去除前后空格，转大写，替换 'NAN' 为''。
    """
    return series.astype(str).str.strip().str.upper().replace('NAN', '')

def standardize_month_vectorized(series):
    """
    将字符串月份标准化为统一的 `MON YY` 格式（例如 'JAN 24'）。

    解析策略：
    - 对输入字符串进行大写、去空格、将 '-' 和 '/' 替换为空格。
    - 使用 `pd.to_datetime` 尝试解析。如果解析成功，则格式化为 `%b %y` 并转大写。
    - 若解析失败，则尝试识别如 `26 APR` 这种年与月颠倒的写法，交换后再格式化为 `APR 26`。
    - 对无法识别的文本保持原样。
    """
    s = series.astype(str).str.strip().str.upper()
    s = s.str.replace('-', ' ', regex=False).str.replace('/', ' ', regex=False)
    # 首先尝试直接解析
    dates = pd.to_datetime(s, errors='coerce')
    # 提取正常解析的结果
    result = dates.dt.strftime('%b %y').str.upper()
    # 处理无法解析的情况
    mask_invalid = dates.isna()
    if mask_invalid.any():
        invalid = s[mask_invalid]
        # 尝试匹配反转形式，例如 '26 APR' -> 'APR 26'
        import re
        def swap_if_match(val):
            # pattern: two digits followed by space then three letters month
            m = re.match(r'^(\d{2})\s*([A-Z]{3})$', val)
            if m:
                yr, mon = m.groups()
                # 返回标准格式
                return f"{mon} {yr}"
            return val
        swapped = invalid.map(swap_if_match)
        # 尝试再次解析
        swapped_dates = pd.to_datetime(swapped, errors='coerce')
        # 格式化
        swapped_formatted = swapped_dates.dt.strftime('%b %y').str.upper()
        # 对成功解析的部分用新值
        result.loc[mask_invalid & swapped_dates.notna()] = swapped_formatted.loc[
            swapped_dates.notna()
        ]
        # 对仍然无法解析的部分保持原样
        result.loc[mask_invalid & swapped_dates.isna()] = swapped.loc[
            swapped_dates.isna()
        ]
    return result

# ---------------------------------------------------------
# 2. 核心：FIFO 净仓计算引擎 (Corrected Netting Engine)
# ---------------------------------------------------------

def calculate_net_positions_corrected(df_paper):
    """
    修正后的 FIFO 净仓引擎：内部开仓和平仓抵消。
    对同品种和合约月的交易，使用 FIFO 算法净额化。
    生成 Net_Open_Vol, Closed_Vol, Close_Events 等字段，用于后续实货匹配。
    """
    start_time = time.time()
    print("\n>>> [Step 1] 执行纸货内部对冲 (FIFO Netting)...")
    # 按交易日期排序，确保 FIFO
    df_paper = df_paper.sort_values(by='Trade Date').reset_index(drop=True)
    # 组合键：品种+合约月
    df_paper['Group_Key'] = df_paper['Std_Commodity'] + "_" + df_paper['Month']
    # 转字典记录加速
    records = df_paper.to_dict('records')
    groups = {}
    # 按组合键分组交易
    for i, row in enumerate(records):
        key = row['Group_Key']
        if key not in groups:
            groups[key] = []
        groups[key].append(i)
    print(f"  数据分组完成，共 {len(groups)} 个组。")
    # 遍历每个组，进行FIFO平仓
    for key, indices in groups.items():
        open_queue = deque()
        for idx in indices:
            row = records[idx]
            current_vol = row.get('Volume', 0)
            # 初始化净开仓量和已平仓量
            records[idx]['Net_Open_Vol'] = current_vol
            records[idx]['Closed_Vol'] = 0
            records[idx]['Close_Events'] = []
            if abs(current_vol) < 0.0001:
                continue
            current_sign = 1 if current_vol > 0 else -1
            while open_queue:
                q_idx, q_vol, q_sign = open_queue[0]
                # 方向相反才能抵消
                if q_sign != current_sign:
                    offset = min(abs(current_vol), abs(q_vol))
                    # 更新当前交易和队列交易的剩余量
                    current_vol -= (current_sign * offset)
                    q_vol -= (q_sign * offset)
                    # 记录平仓事件到原交易
                    close_event = {
                        'Ref': str(records[idx].get('Recap No', '')),
                        'Date': records[idx].get('Trade Date'),
                        'Vol': offset,
                        'Price': records[idx].get('Price', 0)
                    }
                    records[q_idx]['Close_Events'].append(close_event)
                    records[q_idx]['Closed_Vol'] += offset
                    records[q_idx]['Net_Open_Vol'] = q_vol
                    records[idx]['Closed_Vol'] += offset
                    records[idx]['Net_Open_Vol'] = current_vol
                    if abs(q_vol) < 0.0001:
                        open_queue.popleft()
                    else:
                        open_queue[0] = (q_idx, q_vol, q_sign)
                    if abs(current_vol) < 0.0001:
                        break
                else:
                    break
            # 如果还有未抵消净额，入队
            if abs(current_vol) > 0.0001:
                open_queue.append((idx, current_vol, current_sign))
    elapsed = time.time() - start_time
    print(f"  计算完成，耗时 {round(elapsed, 2)} 秒。")
    return pd.DataFrame(records)

# ---------------------------------------------------------
# 3. 匹配逻辑 (v19 开放式时间排序)
# ---------------------------------------------------------

def format_close_details(events):
    """
    整理平仓路径：返回字符串描述、加权平仓价格、平仓量。
    """
    if not events:
        return "", 0, 0
    details = []
    total_vol = 0
    total_val = 0
    # 按日期排序平仓事件
    sorted_events = sorted(events, key=lambda x: x['Date'] if pd.notna(x['Date']) else pd.Timestamp.min)
    for e in sorted_events:
        d_str = e['Date'].strftime('%Y-%m-%d') if pd.notna(e['Date']) else 'N/A'
        p_str = f"@{e['Price']}" if pd.notna(e['Price']) else ""
        details.append(f"[{d_str} Tkt#{e['Ref']} Vol:{e['Vol']:.0f} {p_str}]")
        if pd.notna(e['Price']):
            total_vol += e['Vol']
            total_val += (e['Vol'] * e['Price'])
    weighted_close_price = (total_val / total_vol) if total_vol > 0 else 0
    return " -> ".join(details), weighted_close_price, total_vol

def auto_match_hedges(physical_df, paper_df):
    """
    根据实货的套保指定日期、方向和品种要求，对纸货净仓进行匹配。
    匹配策略：
    1. 根据 Hedge_Proxy 匹配品种，Target_Contract_Month 匹配合约月。
    2. 根据 Direction (买/卖) 决定需要对冲方向 (paper 的净开仓方向相反)。
    3. 如果有 Designation_Date (指定日期)，计算 paper 交易与此日期的时间差，优先分配时间差绝对值最小的交易；
       如果没有指定日期，则回退 FIFO (按交易日期排序)。
    4. 分配顺序：按排序后的 paper 列表依次分配，直到实货量全部匹配或纸货没有可用净仓。
    返回：hedge 关系明细 DataFrame，以及更新后的 physical_df (Unhedged_Volume 字段)。
    """
    hedge_relations = []
    print(">>> [Step 2] 开始实货匹配 (开放式时间排序)...")
    # 不再过滤纸货，只要有交易记录均参与匹配
    active_paper = paper_df.copy()
    active_paper['Allocated_To_Phy'] = 0.0  # 记录已分配给实货的数量（按原始成交量计算）
    # 记录原始索引，方便后续更新到主 DataFrame
    active_paper['_original_index'] = active_paper.index
    match_count = 0
    # 根据定价基准优先级对实货排序：BRENT 优先匹配
    df_phy = physical_df.copy()
    # 记录原始索引，便于回写 Unhedged_Volume
    df_phy['_orig_idx'] = df_phy.index
    if 'Pricing_Benchmark' in df_phy.columns:
        # 创建优先级：包含 BRENT 的排前，其他排后
        def bench_prio(x):
            x_str = str(x).upper()
            return 0 if 'BRENT' in x_str else 1
        df_phy['_priority'] = df_phy['Pricing_Benchmark'].apply(bench_prio)
        # 排序按优先级，然后保持稳定顺序
        df_phy = df_phy.sort_values(by=['_priority', '_orig_idx']).reset_index(drop=True)
        df_phy = df_phy.drop(columns=['_priority'])
    else:
        df_phy = df_phy.reset_index(drop=True)
    # 遍历每一笔实货
    for _, cargo in df_phy.iterrows():
        cargo_id = cargo.get('Cargo_ID')
        phy_vol = cargo.get('Unhedged_Volume', 0)
        if abs(phy_vol) < 0.0001:
            continue
        proxy = str(cargo.get('Hedge_Proxy', ''))
        target_month = cargo.get('Target_Contract_Month', None)
        phy_dir = cargo.get('Direction', 'Buy')
        desig_date = cargo.get('Designation_Date', pd.NaT)
        # 方向：Buy 或 Sell 用于后续计算，但匹配时不再强制根据 paper 净仓方向过滤。
        # required_open_sign = -1 if 'BUY' in str(phy_dir).upper() else 1
        # 基础筛选: 品种、合约月
        candidates_df = active_paper[
            (active_paper['Std_Commodity'].str.contains(proxy, regex=False)) &
            (active_paper['Month'] == target_month)
        ].copy()
        if candidates_df.empty:
            continue
        # 如果有指定日期, 计算时间差绝对值
        if pd.notna(desig_date) and not candidates_df['Trade Date'].isnull().all():
            candidates_df['Time_Lag_Days'] = (candidates_df['Trade Date'] - desig_date).dt.days
            candidates_df['Abs_Lag'] = candidates_df['Time_Lag_Days'].abs()
            # 时间差绝对值小的优先, 如果相同则日期早的优先
            candidates_df = candidates_df.sort_values(by=['Abs_Lag', 'Trade Date'])
        else:
            # 没有指定日期, 退回 FIFO
            candidates_df['Time_Lag_Days'] = np.nan
            candidates_df = candidates_df.sort_values(by='Trade Date')
        # 分配
        for _, ticket in candidates_df.iterrows():
            if abs(phy_vol) < 1:
                break
            original_index = ticket['_original_index']
            # 获取已分配和原始成交量
            curr_allocated = active_paper.at[original_index, 'Allocated_To_Phy']
            curr_total_vol = ticket.get('Volume', 0)
            # 可用量 = 成交量 - 已分配量
            avail = curr_total_vol - curr_allocated
            # 如果剩余可用量几乎为零则跳过
            if abs(avail) < 0.0001:
                continue
            # 分配绝对量：如果可用量足够覆盖需求量，则分配需求量，否则全部可用量
            alloc_amt_abs = abs(phy_vol) if abs(avail) >= abs(phy_vol) else abs(avail)
            # 分配带符号的量根据成交量方向
            alloc_amt = np.sign(avail) * alloc_amt_abs
            # 更新实货未对冲量（减去分配的绝对值）
            phy_vol -= alloc_amt_abs
            # 更新已分配量
            active_paper.at[original_index, 'Allocated_To_Phy'] += alloc_amt
            # 计算 P/L 和 MTM
            open_price = ticket.get('Price', 0)
            mtm_price = ticket.get('Mtm Price', 0)
            total_pl_raw = ticket.get('Total P/L', 0)
            close_events = ticket.get('Close_Events', [])
            close_path_str, avg_close_price, _ = format_close_details(close_events)
            # 未实现MTM: （现价 - 开仓价） * 分配量
            unrealized_mtm = (mtm_price - open_price) * alloc_amt
            ratio = 0
            if abs(ticket.get('Volume', 0)) > 0:
                ratio = abs(alloc_amt) / abs(ticket['Volume'])
            allocated_total_pl = total_pl_raw * ratio
            hedge_relations.append({
                'Cargo_ID': cargo_id,
                'Proxy': proxy,
                'Designation_Date': desig_date.strftime('%Y-%m-%d') if pd.notna(desig_date) else '',
                'Open_Date': ticket.get('Trade Date'),
                'Time_Lag': ticket.get('Time_Lag_Days'),
                'Ticket_ID': ticket.get('Recap No'),
                'Month': ticket.get('Month'),
                'Allocated_Vol': alloc_amt,
                'Trade_Volume': ticket.get('Volume', 0),
                'Trade_Net_Open': ticket.get('Net_Open_Vol', 0),
                'Trade_Closed_Vol': ticket.get('Closed_Vol', 0),
                'Open_Price': open_price,
                'MTM_Price': mtm_price,
                'Alloc_Unrealized_MTM': round(unrealized_mtm, 2),
                'Alloc_Total_PL': round(allocated_total_pl, 2),
                'Close_Path_Details': close_path_str,
            })
            match_count += 1
            # 更新实货未对冲量回到原始 physical_df
            orig_idx = cargo.get('_orig_idx')
            if orig_idx in physical_df.index:
                physical_df.at[orig_idx, 'Unhedged_Volume'] = phy_vol
    print(f"  匹配完成，生成 {match_count} 条详细记录。")
    # 将分配量写回 paper_df (原始索引)
    cols_to_update = active_paper[['_original_index', 'Allocated_To_Phy']].set_index('_original_index')
    paper_df.update(cols_to_update)
    return pd.DataFrame(hedge_relations), physical_df

# ---------------------------------------------------------
# 4. 数据加载与导出
# ---------------------------------------------------------

def load_data_v19(paper_file, phys_file):
    """
    加载纸货和实货数据并预处理。
    """
    # 纸货
    df_p = read_file_fast(paper_file)
    # 统一类型
    df_p['Trade Date'] = pd.to_datetime(df_p['Trade Date'])
    df_p['Volume'] = pd.to_numeric(df_p['Volume'], errors='coerce').fillna(0)
    df_p['Std_Commodity'] = clean_str(df_p['Commodity'])
    if 'Month' in df_p.columns:
        df_p['Month'] = standardize_month_vectorized(df_p['Month'])
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
    # 实货
    df_ph = read_file_fast(phys_file)
    # 映射列名：某些文件中可能叫不同名称
    col_map = {'Target_Pricing_Month': 'Target_Contract_Month', 'Month': 'Target_Contract_Month'}
    df_ph.rename(columns=col_map, inplace=True)
    df_ph['Volume'] = pd.to_numeric(df_ph['Volume'], errors='coerce').fillna(0)
    # 初始化未对冲量
    df_ph['Unhedged_Volume'] = df_ph['Volume']
    df_ph['Hedge_Proxy'] = clean_str(df_ph['Hedge_Proxy']) if 'Hedge_Proxy' in df_ph.columns else ''
    # 合约月标准化
    if 'Target_Contract_Month' in df_ph.columns:
        df_ph['Target_Contract_Month'] = standardize_month_vectorized(df_ph['Target_Contract_Month'])
    # 指定日期
    if 'Designation_Date' in df_ph.columns:
        df_ph['Designation_Date'] = pd.to_datetime(df_ph['Designation_Date'], errors='coerce')
    elif 'Pricing_Start' in df_ph.columns:
        df_ph['Designation_Date'] = pd.to_datetime(df_ph['Pricing_Start'], errors='coerce')
    else:
        df_ph['Designation_Date'] = pd.NaT
    return df_p, df_ph

def export_results(df_rels):
    """
    导出配对结果为 CSV 文件。
    """
    if df_rels.empty:
        print("无匹配结果。")
        return
    out_file = "hedge_allocation_v19_optimized.csv"
    cols = [
        'Cargo_ID', 'Proxy', 'Designation_Date', 'Open_Date', 'Time_Lag',
        'Ticket_ID', 'Month', 'Allocated_Vol',
        # 可选：原始成交量、净开仓量、已平仓量
        'Trade_Volume', 'Trade_Net_Open', 'Trade_Closed_Vol',
        'Open_Price', 'MTM_Price',
        'Alloc_Unrealized_MTM', 'Alloc_Total_PL', 'Close_Path_Details'
    ]
    final_cols = [c for c in cols if c in df_rels.columns]
    df_rels[final_cols].to_csv(out_file, index=False)
    print(f"\n[成功] 账本已生成: {out_file}")

def main(paper_file, physical_file):
    print(f"=== 套保匹配引擎 v19.0 (开放式时间匹配) ===")
    try:
        df_paper, df_physical = load_data_v19(paper_file, physical_file)
        if not df_physical.empty:
            # 先内部净额化纸货
            df_paper_net = calculate_net_positions_corrected(df_paper)
            # 实货匹配
            df_rels, _ = auto_match_hedges(df_physical, df_paper_net)
            export_results(df_rels)
        else:
            print("实货文件为空。")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 默认文件名，可以在运行时替换
    paper_file = '20251126162114_ticket_data.xlsx - Data Sheet.csv'
    physical_file = 'physical_cargo_ledger.csv'
    main(paper_file, physical_file)