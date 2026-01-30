import streamlit as st
import pandas as pd
import re
import io

# --- 1. 頁面設定 ---
st.set_page_config(page_title="專業水準測量系統", page_icon="📐", layout="wide")

# --- CSS 優化 ---
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    div[data-testid="stMetricValue"] { font-size: 1.1rem; }
    button { height: auto; padding-top: 10px !important; padding-bottom: 10px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---

def init_state():
    """初始化 Session State"""
    # 定義標準欄位，防止 KeyError
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
    """智慧命名：A1 -> A2"""
    if df.empty: return "A1"
    last = str(df.iloc[-1]['Point'])
    match = re.search(r'^(.*?)(\d+)$', last)
    if match:
        p = match.group(1)
        n = int(match.group(2))
        return f"{p}{n+1}"
    return f"{prefix}{len(df)+1}"

def calculate_logic(df, start_h):
    """
    純計算函數：接收 DataFrame，回傳計算後的 DataFrame
    """
    df = df.copy()
    
    # 1. 確保欄位存在
    required = ['BS', 'IFS', 'FS', 'HI', 'Elev', 'Point', 'Note']
    for col in required:
        if col not in df.columns:
            df[col] = None

    # 2. 轉型為數字
    for col in ['BS', 'IFS', 'FS']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    last_hi = None
    
    # 3. 逐行計算
    for i in range(len(df)):
        bs = df.at[i, 'BS']
        fs = df.at[i, 'FS']
        ifs = df.at[i, 'IFS']
        
        # 第一點
        if i == 0:
            df.at[i, 'Elev'] = start_h
            if pd.notna(bs):
                last_hi = start_h + bs
                df.at[i, 'HI'] = last_hi
            else:
                df.at[i, 'HI'] = None
        else:
            # 優先轉點 TP
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
            
            # 間視 IFS
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

# --- 3. 程式進入點 ---
init_state()

st.title("📐 專業水準測量系統")

# 參數設定
col1, col2, col3 = st.columns(3)
with col1:
    # 直接更新 session_state
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

# --- 4. 按鈕區 (邏輯重寫：先讀取當前狀態 -> 處理 -> 存回 Session -> Rerun) ---
c1, c2, c3, c4 = st.columns(4)
btn_tp = c1.button("➕ 轉點 (TP)", use_container_width=True)
btn_ifs = c2.button("👁️ 間視 (IFS)", use_container_width=True)
btn_adj = c3.button("⚖️ 平差計算", use_container_width=True)
btn_rst = c4.button("🗑️ 重置表格", type="primary", use_container_width=True)

# --- 5. 數據編輯器 (這是關鍵) ---
# 我們不使用 on_change，而是直接讀取回傳值
edited_df = st.data_editor(
    st.session_state.survey_data,
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
    num_rows="dynamic",
    hide_index=True,
    key="main_editor" 
)

# --- 6. 即時計算 ---
# 每次頁面刷新，都基於最新的編輯結果進行計算
# 這保證了你輸入數字後，高程會自動跑出來
final_df = calculate_logic(edited_df, st.session_state.start_h)

# --- 7. 處理按鈕事件 (在此階段，final_df 包含了使用者最新的輸入) ---

if btn_tp:
    new_name = get_next_name(final_df, "TP")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    # 將計算後的結果加上新的一行，存回 Session
    st.session_state.survey_data = pd.concat([final_df, new_row], ignore_index=True)
    st.rerun()

if btn_ifs:
    new_name = get_next_name(final_df, "IFS")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.survey_data = pd.concat([final_df, new_row], ignore_index=True)
    st.rerun()

if btn_rst:
    st.session_state.survey_data = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': st.session_state.start_h, 'Note': '起點'}
    ])
    st.rerun()

if btn_adj:
    # 進行平差邏輯
    sum_bs = final_df['BS'].sum()
    sum_fs = final_df['FS'].sum()
    
    if st.session_state.survey_type == "閉合水準測量":
        error = sum_bs - sum_fs
    else:
        error = (sum_bs - sum_fs) - (st.session_state.end_h - st.session_state.start_h)
    
    bs_indices = final_df[final_df['BS'].notna() & (final_df['BS'] != 0)].index
    count = len(bs_indices)
    
    if count > 0 and abs(error) > 0.0001:
        correction = -error / count
        for idx in bs_indices:
            final_df.at[idx, 'BS'] += correction
            note = str(final_df.at[idx, 'Note']) if pd.notna(final_df.at[idx, 'Note']) else ""
            if "[平差]" not in note:
                final_df.at[idx, 'Note'] = f"{note} [平差{correction:.4f}]"
        
        # 平差後需要再重算一次高程
        final_df = calculate_logic(final_df, st.session_state.start_h)
        st.session_state.survey_data = final_df
        st.success(f"已平差！總誤差 {error:.4f}m，每站修正 {correction:.4f}m")
        st.rerun()
    else:
        st.warning("無顯著誤差，無需平差")

# --- 8. 底部統計與導出 ---
# 使用 final_df (已計算版) 來做統計
total_bs = final_df['BS'].sum()
total_fs = final_df['FS'].sum()
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
    final_df.to_excel(writer, index=False, sheet_name='測量數據')
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
