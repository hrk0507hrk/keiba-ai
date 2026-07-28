import streamlit as st
from formatter import diagnostic_dataframe, result_dataframe
from parser import parse_conditions, parse_past_performances, parse_racecard, parse_time_index
from scorer import score_horses
from selector import select_marks

st.set_page_config(page_title="競馬AI Next", page_icon="🐎", layout="wide")
st.title("🐎 競馬AI Next v0.1")
st.caption("出走表＋馬柱＋タイム指数｜人気1～3位から◎｜印は計7頭")

def clear_inputs():
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""

racecard_text = st.text_area("① 出走表", height=260, placeholder="出走表を貼り付け", key="racecard_input")
past_text = st.text_area("② 馬柱", height=420, placeholder="馬柱を貼り付け", key="past_input")
timeindex_text = st.text_area("③ タイム指数", height=320, placeholder="中央・地方どちらも対応", key="timeindex_input")
col1, col2 = st.columns([4,1])
with col1: run_clicked = st.button("予想開始", type="primary", use_container_width=True)
with col2: st.button("クリア", use_container_width=True, on_click=clear_inputs)

if run_clicked:
    conditions = parse_conditions(racecard_text)
    horses = parse_racecard(racecard_text)
    horses = parse_past_performances(past_text, horses)
    horses, mode = parse_time_index(timeindex_text, horses)
    errors = []
    if not horses: errors.append("出走表から馬を読み取れませんでした。")
    if not any(h.records for h in horses.values()): errors.append("馬柱の近走データを読み取れませんでした。")
    if not any(any(v > 0 for v in vars(h.time_index).values()) for h in horses.values()): errors.append("タイム指数を読み取れませんでした。")
    if errors:
        for error in errors: st.error(error)
        st.stop()
    horses = score_horses(horses, conditions, mode)
    selected = select_marks(horses)
    st.divider(); st.subheader("予想結果")
    st.dataframe(result_dataframe(selected), use_container_width=True, hide_index=True)
    with st.expander("読み取り・採点確認"):
        st.write(f"判定形式：{'中央競馬' if mode == 'central' else '地方競馬'}")
        st.write(f"対象条件：{conditions.venue or '不明'} {conditions.surface or '不明'}{conditions.distance or '不明'} {conditions.going or '不明'}")
        st.dataframe(diagnostic_dataframe(horses), use_container_width=True, hide_index=True)
