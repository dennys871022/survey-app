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
    button { height: auto; padding-top: 10px !important; padding-bottom: 10px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 核心邏輯函數 ---

def init_state():
    """初始化 Session State"""
    if 'survey_df' not in st.session_state:
        # 這是我們唯一的「真」資料庫
        st.session_state.survey_df = pd.DataFrame([
            {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}
        ])
    if 'survey_type' not in st.session_state:
        st.session_state.survey_type = "閉合水準測量"
    if 'start_h' not in st.session_state:
        st.session_state.start_h = 0.0
    if 'end_h' not in st.session_state:
        st.session_state.end_h = 0.0

def get_next_name(df, prefix):
    """智慧命名邏輯"""
    if df.empty: return "A1"
    last = str(df.iloc[-1]['Point'])
    match = re.search(r'^(.*?)(\d+)$', last)
    if match:
        p = match.group(1)
        n = int(match.group(2))
        return f"{p}{n+1}"
    return f"{prefix}{len(df)+1}"

def calculate_logic(df, start_h):
    """純計算函數：輸入 DataFrame -> 輸出計算後的 DataFrame"""
    df = df.copy()
    
    # 防呆與轉型
    required = ['Point', 'BS', 'IFS', 'FS', 'HI', 'Elev', 'Note']
    for col in required:
        if col not in df.columns: df[col] = None
            
    for col in ['BS', 'IFS', 'FS']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    last_hi = None
    
    for i in range(len(df)):
        bs = df.at[i, 'BS']
        fs = df.at[i, 'FS']
        ifs = df.at[i, 'IFS']
        
        if i == 0:
            df.at[i, 'Elev'] = start_h
            if pd.notna(bs):
                last_hi = start_h + bs
                df.at[i, 'HI'] = last_hi
            else:
                df.at[i, 'HI'] = None
        else:
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

# --- 3. 關鍵的回調函數 (Callback) ---
# 這是解決數據清空的關鍵：在按鈕執行動作前，先強制把編輯器的內容存下來

def sync_editor_data():
    """將編輯器當下的內容同步到 session_state"""
    if "my_editor" in st.session_state:
        # 從編輯器抓取最新數據
        current_data = st.session_state["my_editor"]
        # 立即計算
        calculated = calculate_logic(current_data, st.session_state.start_h)
        # 存入真資料庫
        st.session_state.survey_df = calculated

def add_tp_callback():
    """新增轉點：先同步，再新增"""
    sync_editor_data() # <--- 關鍵步驟
    df = st.session_state.survey_df
    new_name = get_next_name(df, "TP")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.survey_df = pd.concat([df, new_row], ignore_index=True)

def add_ifs_callback():
    """新增間視：先同步，再新增"""
    sync_editor_data() # <--- 關鍵步驟
    df = st.session_state.survey_df
    new_name = get_next_name(df, "IFS")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    st.session_state.survey_df = pd.concat([df, new_row], ignore_index=True)

def adjust_callback():
    """平差：先同步，再計算"""
    sync_editor_data()
    df = st.session_state.survey_df
    
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
        
        # 平差後重算
        st.session_state.survey_df = calculate_logic(df, st.session_state.start_h)
        st.success(f"已平差！誤差 {error:.4f}m")
    else:
        st.warning("無誤差")

def reset_callback():
    st.session_state.survey_df = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': st.session_state.start_h, 'Note': '起點'}
    ])

# --- 4. 主程式渲染 ---
init_state()

st.title("📐 專業水準測量系統")

# 參數區
col1, col2, col3 = st.columns(3)
with col1:
    st.session_state.survey_type = st.selectbox("測量類型", ["閉合水準測量", "附合水準測量"], index=0 if st.session_state.survey_type=="閉合水準測量" else 1)
with col2:
    # 數值改變時，也觸發同步
    st.session_state.start_h = st.number_input("起點高程 (H1)", value=float(st.session_state.start_h), step=0.001, format="%.3f", on_change=sync_editor_data)
with col3:
    if st.session_state.survey_type == "附合水準測量":
        st.session_state.end_h = st.number_input("終點高程 (H2)", value=float(st.session_state.end_h), step=0.001, format="%.3f", on_change=sync_editor_data)

# 按鈕區 (全部綁定 Callback)
c1, c2, c3, c4 = st.columns(4)
c1.button("➕ 轉點 (TP)", on_click=add_tp_callback, use_container_width=True)
c2.button("👁️ 間視 (IFS)", on_click=add_ifs_callback, use_container_width=True)
c3.button("⚖️ 平差計算", on_click=adjust_callback, use_container_width=True)
c4.button("🗑️ 重置表格", on_click=reset_callback, type="primary", use_container_width=True)

# 數據編輯器
# on_change=sync_editor_data 確保每次輸入完按 Enter 就會立刻計算並存檔
edited_df = st.data_editor(
    st.session_state.survey_df,
    key="my_editor",
    on_change=sync_editor_data, 
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
    hide_index=True,
    num_rows="dynamic"
)

# 由於 sync_editor_data 可能已經更新了 session_state，這裡再做一次計算確保顯示最新
final_df = calculate_logic(edited_df, st.session_state.start_h)

# 底部統計
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
    label="💾 下載 Excel 報表",
    data=buffer.getvalue(),
    file_name="測量成果.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)
