import streamlit as st
import pandas as pd
import re
import io

# --- 1. 頁面設定 ---
st.set_page_config(page_title="專業水準測量系統", page_icon="📐", layout="wide")

# --- CSS 優化手機顯示 ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    button { height: auto; padding-top: 12px !important; padding-bottom: 12px !important; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---

def init_state():
    """初始化 Session State，確保欄位結構正確"""
    if 'df' not in st.session_state:
        st.session_state.df = pd.DataFrame([
            {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}
        ])
    if 'survey_type' not in st.session_state:
        st.session_state.survey_type = "閉合水準測量"
    if 'start_h' not in st.session_state:
        st.session_state.start_h = 0.0
    if 'end_h' not in st.session_state:
        st.session_state.end_h = 0.0

def get_next_name(df, prefix):
    """智慧命名：自動偵測上一點編號 (例如 A1 -> A2)"""
    if df.empty: return "A1"
    last = str(df.iloc[-1]['Point'])
    # 抓取字串結尾的數字
    match = re.search(r'^(.*?)(\d+)$', last)
    if match:
        p = match.group(1)
        n = int(match.group(2))
        return f"{p}{n+1}"
    return f"{prefix}{len(df)+1}"

def calculate_logic(df, start_h):
    """
    純計算函數：
    接收使用者編輯後的 DataFrame，回傳計算完 HI 和 Elev 的 DataFrame
    """
    # 建立副本以免影響原始數據
    df = df.copy()
    
    # 1. 確保欄位存在 (防呆)
    required = ['Point', 'BS', 'IFS', 'FS', 'HI', 'Elev', 'Note']
    for col in required:
        if col not in df.columns:
            df[col] = None

    # 2. 轉型為數字 (處理空字串)
    for col in ['BS', 'IFS', 'FS']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    last_hi = None
    
    # 3. 逐行計算 (核心測量邏輯)
    for i in range(len(df)):
        bs = df.at[i, 'BS']
        fs = df.at[i, 'FS']
        ifs = df.at[i, 'IFS']
        
        # 第一點 (已知點)
        if i == 0:
            df.at[i, 'Elev'] = start_h
            if pd.notna(bs):
                last_hi = start_h + bs
                df.at[i, 'HI'] = last_hi
            else:
                df.at[i, 'HI'] = None
        else:
            # 優先處理轉點 (TP)
            if pd.notna(fs): 
                if pd.notna(last_hi):
                    elev = last_hi - fs
                    df.at[i, 'Elev'] = elev
                    
                    if pd.notna(bs):
                        last_hi = elev + bs
                        df.at[i, 'HI'] = last_hi
                    else:
                        df.at[i, 'HI'] = None
                        last_hi = None
                else:
                    df.at[i, 'Elev'] = None
            
            # 處理間視 (IFS)
            elif pd.notna(ifs):
                if pd.notna(last_hi):
                    df.at[i, 'Elev'] = last_hi - ifs
                    df.at[i, 'HI'] = None
                else:
                    df.at[i, 'Elev'] = None
            else:
                df.at[i, 'Elev'] = None
                df.at[i, 'HI'] = None

    return df

# --- 3. 程式主流程 ---
init_state()

st.title("📐 專業水準測量系統")

# 參數設定區
col1, col2, col3 = st.columns(3)
with col1:
    st.session_state.survey_type = st.selectbox(
        "測量類型", 
        ["閉合水準測量", "附合水準測量"], 
        index=0 if st.session_state.survey_type=="閉合水準測量" else 1
    )
with col2:
    st.session_state.start_h = st.number_input(
        "起點高程 (H1)", 
        value=float(st.session_state.start_h), 
        step=0.001, format="%.3f"
    )
with col3:
    if st.session_state.survey_type == "附合水準測量":
        st.session_state.end_h = st.number_input(
            "終點高程 (H2)", 
            value=float(st.session_state.end_h), 
            step=0.001, format="%.3f"
        )

# --- 4. 數據編輯器 (關鍵修正) ---
# 我們直接顯示 session_state 中的數據
edited_df = st.data_editor(
    st.session_state.df,
    column_config={
        "BS": st.column_config.NumberColumn("後視 (BS)", format="%.3f"),
        "IFS": st.column_config.NumberColumn("間視 (IFS)", format="%.3f"),
        "FS": st.column_config.NumberColumn("前視 (FS)", format="%.3f"),
        "HI": st.column_config.NumberColumn("儀器高 (HI)", format="%.3f", disabled=True),
        "Elev": st.column_config.NumberColumn("高程 (Elev)", format="%.3f", disabled=True),
        "Point": "測點",
        "Note": "備註"
    },
    use_container_width=True,
    num_rows="dynamic", # 允許手動刪減行，增加靈活性
    hide_index=True
)

# --- 5. 即時同步與計算 ---
# 這一步是重點：我們立刻拿使用者剛編輯完的 edited_df 去計算
# 並將計算結果「存回」session_state。
# 這樣一來，無論按下什麼按鈕，session_state 裡永遠是「已輸入 + 已計算」的最新狀態。
calc_df = calculate_logic(edited_df, st.session_state.start_h)
st.session_state.df = calc_df 

# --- 6. 按鈕操作區 ---
c1, c2, c3, c4 = st.columns(4)

# 按鈕邏輯：直接操作已經是最新的 st.session_state.df
if c1.button("➕ 轉點 (TP)", use_container_width=True):
    new_name = get_next_name(st.session_state.df, "TP")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
    st.rerun() # 重新整理頁面以顯示新行

if c2.button("👁️ 間視 (IFS)", use_container_width=True):
    new_name = get_next_name(st.session_state.df, "IFS")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.df = pd.concat([st.session_state.df, new_row], ignore_index=True)
    st.rerun()

if c3.button("⚖️ 平差計算", use_container_width=True):
    # 使用當前數據進行平差
    df = st.session_state.df
    sum_bs = df['BS'].sum()
    sum_fs = df['FS'].sum()
    
    if st.session_state.survey_type == "閉合水準測量":
        error = sum_bs - sum_fs
    else:
        error = (sum_bs - sum_fs) - (st.session_state.end_h - st.session_state.start_h)
    
    bs_indices = df[df['BS'].notna() & (df['BS'] != 0)].index
    count = len(bs_indices)
    
    if count > 0 and abs(error) > 0.0001:
        correction = -error / count
        for idx in bs_indices:
            df.at[idx, 'BS'] += correction
            note = str(df.at[idx, 'Note']) if pd.notna(df.at[idx, 'Note']) else ""
            if "[平差]" not in note:
                df.at[idx, 'Note'] = f"{note} [平差{correction:.4f}]"
        
        # 平差後需要再重算一次高程並存回
        st.session_state.df = calculate_logic(df, st.session_state.start_h)
        st.success(f"已平差！總誤差 {error:.4f}m，每站修正 {correction:.4f}m")
        st.rerun()
    else:
        st.warning("無顯著誤差，無需平差")

if c4.button("🗑️ 重置表格", type="primary", use_container_width=True):
    st.session_state.df = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': st.session_state.start_h, 'Note': '起點'}
    ])
    st.rerun()

# --- 7. 底部統計與導出 ---
# 使用 calc_df 確保顯示的是最新計算結果
total_bs = calc_df['BS'].sum()
total_fs = calc_df['FS'].sum()
diff_h = total_bs - total_fs

if st.session_state.survey_type == "閉合水準測量":
    closure = diff_h
else:
    closure = diff_h - (st.session_state.end_h - st.session_state.start_h)

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Σ BS", f"{total_bs:.3f}")
m2.metric("Σ FS", f"{total_fs:.3f}")
m3.metric("實測高差", f"{diff_h:.3f}")
m4.metric("閉合差 (Wh)", f"{closure:.3f}", delta_color="inverse")

# Excel 導出
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    # 導出的一定是 calc_df (已計算版)
    calc_df.to_excel(writer, index=False, sheet_name='測量數據')
    summary_df = pd.DataFrame([
        {'項目': '測量類型', '數值': st.session_state.survey_type},
        {'項目': '起點高程', '數值': st.session_state.start_h},
        {'項目': '總後視', '數值': total_bs},
        {'項目': '總前視', '數值': total_fs},
        {'項目': '閉合差', '數值': closure}
    ])
    summary_df.to_excel(writer, index=False, sheet_name='統計摘要')

st.download_button(
    label="💾 下載 Excel 報表 (.xlsx)",
    data=buffer.getvalue(),
    file_name="測量成果.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)
