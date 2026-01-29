import streamlit as st
import pandas as pd
import re
import io

# --- 頁面設定 ---
st.set_page_config(page_title="專業水準測量系統", page_icon="📐", layout="wide")

# --- CSS 優化 ---
st.markdown("""
    <style>
    .block-container { padding-top: 1.5rem; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem; }
    button { height: auto; padding-top: 10px !important; padding-bottom: 10px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 核心邏輯區 ---

def init_state():
    """初始化 Session State"""
    if 'survey_data' not in st.session_state:
        st.session_state.survey_data = pd.DataFrame([
            {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}
        ])
    if 'survey_type' not in st.session_state:
        st.session_state.survey_type = "閉合水準測量"
    if 'start_h' not in st.session_state:
        st.session_state.start_h = 0.0
    if 'end_h' not in st.session_state:
        st.session_state.end_h = 0.0

def get_next_name(df, prefix):
    """智慧命名：自動偵測上一點編號並遞增"""
    if df.empty: return "A1"
    last = str(df.iloc[-1]['Point'])
    # 尋找結尾數字
    match = re.search(r'^(.*?)(\d+)$', last)
    if match:
        p = match.group(1)
        n = int(match.group(2))
        return f"{p}{n+1}"
    return f"{prefix}{len(df)+1}"

def recalculate():
    """
    核心計算函數 (Callback)
    當表格被編輯、或按下按鈕時，強制執行此函數來更新所有高程。
    """
    # 1. 從編輯器狀態獲取最新數據
    # 注意：st.data_editor 的 key='editor' 會將最新數據存在 st.session_state['editor']
    if 'editor' not in st.session_state:
        return

    df = st.session_state['editor'].copy()
    
    # 2. 確保數值格式正確 (避免文字混入導致報錯)
    cols = ['BS', 'IFS', 'FS']
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    start_h = st.session_state.start_h
    last_hi = None
    
    # 3. 逐行計算 (這是不會跑掉的關鍵)
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
                    
                    # 計算下一站 HI
                    if pd.notna(bs):
                        last_hi = elev + bs
                        df.at[i, 'HI'] = last_hi
                    else:
                        df.at[i, 'HI'] = None
                        last_hi = None # 斷鍊保護
                else:
                    df.at[i, 'Elev'] = None
            
            # 處理間視 (IFS)
            elif pd.notna(ifs):
                if pd.notna(last_hi):
                    df.at[i, 'Elev'] = last_hi - ifs
                    df.at[i, 'HI'] = None
                else:
                    df.at[i, 'Elev'] = None
            
            # 若無輸入則清空
            else:
                df.at[i, 'Elev'] = None
                df.at[i, 'HI'] = None

    # 4. 將計算結果寫回主數據庫
    st.session_state.survey_data = df

def add_tp():
    """新增轉點 Callback"""
    recalculate() # 先保存並計算當前數據
    df = st.session_state.survey_data
    new_name = get_next_name(df, "TP")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.survey_data = pd.concat([df, new_row], ignore_index=True)

def add_ifs():
    """新增間視 Callback"""
    recalculate()
    df = st.session_state.survey_data
    new_name = get_next_name(df, "IFS")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.survey_data = pd.concat([df, new_row], ignore_index=True)

def adjust_errors():
    """平差計算 Callback"""
    recalculate()
    df = st.session_state.survey_data
    
    # 計算閉合差
    sum_bs = df['BS'].sum()
    sum_fs = df['FS'].sum()
    
    if st.session_state.survey_type == "閉合水準測量":
        error = sum_bs - sum_fs
    else:
        error = (sum_bs - sum_fs) - (st.session_state.end_h - st.session_state.start_h)
        
    # 篩選有效後視點
    bs_indices = df[df['BS'].notna() & (df['BS'] != 0)].index
    count = len(bs_indices)
    
    if count > 0 and abs(error) > 0.0001:
        correction = -error / count
        for idx in bs_indices:
            df.at[idx, 'BS'] += correction
            # 更新備註
            note = str(df.at[idx, 'Note']) if pd.notna(df.at[idx, 'Note']) else ""
            if "[平差]" not in note:
                df.at[idx, 'Note'] = f"{note} [平差{correction:.4f}]"
        
        st.session_state.survey_data = df
        recalculate() # 平差後重新計算高程
        st.success(f"已執行平差！總誤差 {error:.4f}m，每站改正 {correction:.4f}m")
    else:
        st.warning("無顯著誤差或數據不足，無需平差。")

def reset_data():
    """重置 Callback"""
    st.session_state.survey_data = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': st.session_state.start_h, 'Note': '起點'}
    ])

# --- 初始化 ---
init_state()

# --- 介面佈局 ---
st.title("📐 專業水準測量系統")

# 1. 頂部參數 (使用 key 自動綁定 session_state)
col1, col2, col3 = st.columns(3)
with col1:
    st.selectbox("測量類型", ["閉合水準測量", "附合水準測量"], key='survey_type')
with col2:
    st.number_input("起點高程 (H1)", step=0.001, format="%.3f", key='start_h', on_change=recalculate)
with col3:
    if st.session_state.survey_type == "附合水準測量":
        st.number_input("終點高程 (H2)", step=0.001, format="%.3f", key='end_h')

# 2. 功能按鈕 (使用 on_click 回調，這是防止數據清空的關鍵！)
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.button("➕ 轉點 (TP)", on_click=add_tp, use_container_width=True)
with c2:
    st.button("👁️ 間視 (IFS)", on_click=add_ifs, use_container_width=True)
with c3:
    st.button("⚖️ 平差計算", on_click=adjust_errors, use_container_width=True)
with c4:
    st.button("🗑️ 重置表格", on_click=reset_data, type="primary", use_container_width=True)

# 3. 數據編輯器
# 關鍵：key='editor' 綁定，on_change=recalculate 自動計算
edited_df = st.data_editor(
    st.session_state.survey_data,
    key='editor', 
    on_change=recalculate, 
    column_config={
        "BS": st.column_config.NumberColumn("後視 (BS)", format="%.3f", required=False),
        "IFS": st.column_config.NumberColumn("間視 (IFS)", format="%.3f", required=False),
        "FS": st.column_config.NumberColumn("前視 (FS)", format="%.3f", required=False),
        "HI": st.column_config.NumberColumn("儀器高 (HI)", format="%.3f", disabled=True),
        "Elev": st.column_config.NumberColumn("高程 (Elev)", format="%.3f", disabled=True),
        "Point": "測點",
        "Note": "備註"
    },
    use_container_width=True,
    num_rows="dynamic",
    hide_index=True
)

# 4. 底部統計 (即時從 session_state 讀取)
curr_df = st.session_state.survey_data
total_bs = curr_df['BS'].sum()
total_fs = curr_df['FS'].sum()
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

# 5. Excel 導出
# 建立 Excel 緩衝區
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    curr_df.to_excel(writer, index=False, sheet_name='測量數據')
    # 可以加入第二個分頁做摘要
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
