import streamlit as st
import pandas as pd
import re
import io

# --- 1. 頁面設定 ---
st.set_page_config(page_title="專業水準測量系統", page_icon="📐", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 1rem; }
    button { height: auto; padding-top: 10px !important; padding-bottom: 10px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. 核心計算邏輯 ---

def get_next_name(df, prefix):
    if df.empty: return "A1"
    last = str(df.iloc[-1]['Point'])
    match = re.search(r'^(.*?)(\d+)$', last)
    if match:
        p = match.group(1)
        n = int(match.group(2))
        return f"{p}{n+1}"
    return f"{prefix}{len(df)+1}"

def calculate_logic(df, start_h):
    """計算高程的核心邏輯"""
    # 建立副本，避免修改原始資料
    df = df.copy()
    
    # 1. 補齊欄位 (防呆)
    required = ['Point', 'BS', 'IFS', 'FS', 'HI', 'Elev', 'Note']
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

# --- 3. 初始化 (只執行一次) ---
if 'survey_df' not in st.session_state:
    st.session_state.survey_df = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}
    ])
if 'survey_type' not in st.session_state:
    st.session_state.survey_type = "閉合水準測量"
if 'start_h' not in st.session_state:
    st.session_state.start_h = 0.0
if 'end_h' not in st.session_state:
    st.session_state.end_h = 0.0

# --- 4. 介面佈局 ---
st.title("📐 專業水準測量系統")

# 參數區
col1, col2, col3 = st.columns(3)
with col1:
    st.session_state.survey_type = st.selectbox("測量類型", ["閉合水準測量", "附合水準測量"], index=0 if st.session_state.survey_type=="閉合水準測量" else 1)
with col2:
    st.session_state.start_h = st.number_input("起點高程 (H1)", step=0.001, format="%.3f", value=st.session_state.start_h)
with col3:
    if st.session_state.survey_type == "附合水準測量":
        st.session_state.end_h = st.number_input("終點高程 (H2)", step=0.001, format="%.3f", value=st.session_state.end_h)

# --- 5. 數據編輯器 (最關鍵的一步) ---
# 我們獲取使用者「當下」看到的表格，並存入 edited_df
edited_df = st.data_editor(
    st.session_state.survey_df,
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
    hide_index=True
)

# --- 6. 立即計算 ---
# 無論如何，先拿「眼前看到的數據 (edited_df)」算一遍
# 這樣就算您只打字不按按鈕，高程也會跳出來
current_calculated_df = calculate_logic(edited_df, st.session_state.start_h)

# --- 7. 更新 Session State (防止數據丟失的關鍵) ---
# 我們把算好的結果存回資料庫，這樣如果使用者只是改了 H1 或切換類型，數據也會被保留
# 但為了避免 Streamlit 的循環更新警告，我們通常讓它自然流動，
# 只有在「按按鈕」時，我們才強制寫入。

# --- 8. 按鈕區 ---
c1, c2, c3, c4 = st.columns(4)

# 【重點修正】：
# 按下按鈕時，我們是拿 current_calculated_df (包含您剛打的字) 來新增一行
# 然後存回 session_state

if c1.button("➕ 轉點 (TP)", use_container_width=True):
    new_name = get_next_name(current_calculated_df, "TP")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    
    # 這裡用 current_calculated_df，所以您剛打的字會被保留
    st.session_state.survey_df = pd.concat([current_calculated_df, new_row], ignore_index=True)
    st.rerun()

if c2.button("👁️ 間視 (IFS)", use_container_width=True):
    new_name = get_next_name(current_calculated_df, "IFS")
    new_row = pd.DataFrame([{'Point': new_name, 'BS': None, 'IFS': None, 'FS': None, 'HI': None, 'Elev': None, 'Note': ''}])
    
    # 同上
    st.session_state.survey_df = pd.concat([current_calculated_df, new_row], ignore_index=True)
    st.rerun()

if c3.button("⚖️ 平差計算", use_container_width=True):
    # 使用 current_calculated_df 來平差
    df = current_calculated_df
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
        
        # 平差後重算並存回
        st.session_state.survey_df = calculate_logic(df, st.session_state.start_h)
        st.success(f"已平差！誤差 {error:.4f}m")
        st.rerun()
    else:
        st.warning("無顯著誤差")

if c4.button("🗑️ 重置表格", type="primary", use_container_width=True):
    st.session_state.survey_df = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': st.session_state.start_h, 'Note': '起點'}
    ])
    st.rerun()

# 如果沒有按按鈕，但數據有變動（例如使用者只是在表格打字），
# 我們也需要把 current_calculated_df 存起來，以便下次載入
# 但為了避免干擾編輯器，我們只在必要時更新
if not current_calculated_df.equals(st.session_state.survey_df):
    # 這裡不使用 st.rerun() 避免無限迴圈，只是默默更新後台數據
    st.session_state.survey_df = current_calculated_df

# --- 9. 底部統計與導出 ---
total_bs = current_calculated_df['BS'].sum()
total_fs = current_calculated_df['FS'].sum()
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
    current_calculated_df.to_excel(writer, index=False, sheet_name='測量數據')
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
