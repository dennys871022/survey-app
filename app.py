import streamlit as st
import pandas as pd
import re
import io

# --- 頁面設定 ---
st.set_page_config(page_title="專業水準測量系統", page_icon="📐", layout="wide")

# --- CSS 優化手機版面 ---
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 5rem; }
    button[kind="secondary"] { border: 1px solid #ced4da; }
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
""", unsafe_allow_html=True)

# --- 初始化 Session State (類似 LocalStorage) ---
if 'data' not in st.session_state:
    # 預設第一行資料
    st.session_state.data = pd.DataFrame([
        {'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}
    ])

# --- 核心邏輯函數 ---

def get_next_smart_name(current_df, type_prefix):
    """智慧命名邏輯：偵測上一點結尾數字並遞增"""
    if current_df.empty:
        return "A1"
    
    last_name = str(current_df.iloc[-1]['Point'])
    match = re.search(r'^(.*?)(\d+)$', last_name)
    
    if match:
        prefix = match.group(1)
        number = int(match.group(2))
        return f"{prefix}{number + 1}"
    else:
        # 沒數字就用預設 TP/IFS
        return f"{type_prefix}{len(current_df) + 1}"

def calculate_survey(df, start_h):
    """計算 HI, Elev 並返回更新後的 DataFrame 與 統計數據"""
    df = df.copy()
    
    # 強制轉型避免計算錯誤
    cols = ['BS', 'IFS', 'FS']
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    last_hi = 0.0
    total_bs = 0.0
    total_fs = 0.0
    
    # 逐行計算
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
                total_bs += bs
            else:
                df.at[i, 'HI'] = None
        else:
            # 轉點 TP
            if pd.notna(fs): 
                # 先算高程
                if pd.notna(last_hi):
                    elev = last_hi - fs
                    df.at[i, 'Elev'] = elev
                    total_fs += fs
                    
                    # 再算新的 HI
                    if pd.notna(bs):
                        last_hi = elev + bs
                        df.at[i, 'HI'] = last_hi
                        total_bs += bs
                    else:
                        df.at[i, 'HI'] = None
                        last_hi = None # 斷鍊
                else:
                    df.at[i, 'Elev'] = None
            
            # 間視 IFS
            elif pd.notna(ifs):
                if pd.notna(last_hi):
                    df.at[i, 'Elev'] = last_hi - ifs
                    df.at[i, 'HI'] = None
                else:
                    df.at[i, 'Elev'] = None

    return df, total_bs, total_fs

def add_row(row_type):
    """新增一列"""
    prefix = "TP" if row_type == "TP" else "IFS"
    new_name = get_next_smart_name(st.session_state.data, prefix)
    
    new_row = {
        'Point': new_name,
        'BS': None, 
        'IFS': None, 
        'FS': None, 
        'HI': None, 
        'Elev': None, 
        'Note': ''
    }
    st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame([new_row])], ignore_index=True)

# --- 介面配置 ---

st.title("📐 專業水準測量系統")

# 1. 頂部設定區 (響應式排列)
col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    survey_type = st.selectbox("測量類型", ["閉合水準測量", "附合水準測量"])
with col2:
    start_height = st.number_input("起點高程 (H1)", value=0.000, step=0.001, format="%.3f")
with col3:
    if survey_type == "附合水準測量":
        end_height = st.number_input("終點高程 (H2)", value=0.000, step=0.001, format="%.3f")
    else:
        end_height = None

# 2. 功能按鈕區
c_add_tp, c_add_ifs, c_adjust, c_reset = st.columns([1, 1, 1, 1])

with c_add_tp:
    if st.button("➕ 轉點 (TP)", use_container_width=True):
        add_row("TP")
with c_add_ifs:
    if st.button("👁️ 間視 (IFS)", use_container_width=True):
        add_row("IFS")
with c_reset:
    if st.button("🗑️ 重置", type="primary", use_container_width=True):
        st.session_state.data = pd.DataFrame([{'Point': 'BM1', 'BS': 0.0, 'IFS': None, 'FS': None, 'HI': None, 'Elev': 0.0, 'Note': '起點'}])
        st.rerun()

# 3. 數據編輯區 (Data Editor)
# 這裡允許使用者直接像 Excel 一樣編輯數據，但鎖定 HI 和 Elev 欄位由系統計算
edited_df = st.data_editor(
    st.session_state.data,
    column_config={
        "BS": st.column_config.NumberColumn("後視 (BS)", format="%.3f"),
        "IFS": st.column_config.NumberColumn("間視 (IFS)", format="%.3f"),
        "FS": st.column_config.NumberColumn("前視 (FS)", format="%.3f"),
        "HI": st.column_config.NumberColumn("儀器高 (HI)", format="%.3f", disabled=True), # 鎖定
        "Elev": st.column_config.NumberColumn("高程 (Elev)", format="%.3f", disabled=True), # 鎖定
        "Point": st.column_config.TextColumn("測點"),
        "Note": st.column_config.TextColumn("備註"),
    },
    num_rows="dynamic", # 允許手動刪減行
    use_container_width=True,
    hide_index=True
)

# 4. 即時計算與更新
# 當使用者編輯表格後，edited_df 會變更，我們進行計算並更新 session_state
calculated_df, sum_bs, sum_fs = calculate_survey(edited_df, start_height)

# 計算閉合差
if survey_type == "閉合水準測量":
    closure_error = sum_bs - sum_fs
else:
    closure_error = (sum_bs - sum_fs) - (end_height - start_height)

# 將計算結果存回 session，以便下次渲染使用
# 注意：這裡不直接寫入 st.session_state.data 以避免迴圈刷新，Streamlit 的 data_editor 機制會自動處理輸入
# 我們只需要顯示計算結果即可，或者在按鈕觸發時寫入

# 5. 平差功能
with c_adjust:
    if st.button("⚖️ 平差計算", use_container_width=True):
        # 找出所有有輸入 BS 的列 (作為分母)
        bs_rows = calculated_df[pd.notna(calculated_df['BS']) & (calculated_df['BS'] != 0)].index
        count = len(bs_rows)
        
        if count > 0 and abs(closure_error) > 0.0001:
            correction = -closure_error / count
            for idx in bs_rows:
                original_bs = calculated_df.at[idx, 'BS']
                calculated_df.at[idx, 'BS'] = original_bs + correction
                # 更新備註
                current_note = str(calculated_df.at[idx, 'Note']) if pd.notna(calculated_df.at[idx, 'Note']) else ""
                calculated_df.at[idx, 'Note'] = f"{current_note} [平差{correction:.4f}]"
            
            # 更新後重新計算全表
            final_df, s_bs, s_fs = calculate_survey(calculated_df, start_height)
            st.session_state.data = final_df # 強制更新
            st.success(f"平差完成！每站改正: {correction:.4f}m")
            st.rerun()
        else:
            st.warning("無誤差或無後視數據，無需平差。")

# 6. 底部統計資訊列 (類似手機 App 底部)
st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Σ BS", f"{sum_bs:.3f}")
m2.metric("Σ FS", f"{sum_fs:.3f}")
m3.metric("實測高差", f"{(sum_bs - sum_fs):.3f}")
m4.metric("閉合差 (Wh)", f"{closure_error:.3f}", delta_color="inverse")

# 7. 匯出 Excel
csv = calculated_df.to_csv(index=False).encode('utf-8-sig')
st.download_button(
    label="💾 下載 CSV 報表",
    data=csv,
    file_name='測量成果.csv',
    mime='text/csv',
    use_container_width=True
)
