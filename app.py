import re
from dataclasses import dataclass, field
from itertools import permutations
from typing import List, Dict, Tuple, Optional

import streamlit as st

st.set_page_config(page_title="競馬AI2.0", layout="wide")

# ==============================
# データ定義
# ==============================

@dataclass
class PastRace:
    date: str = ""
    place: str = ""
    surface: str = ""
    distance: int = 0
    condition: str = ""
    finish: int = 99
    popularity: int = 99
    margin: float = 99.0
    passing: str = ""
    jockey: str = ""
    weight: float = 0.0
    bodyweight: int = 0
    body_diff: int = 0
    raw: str = ""


@dataclass
class Horse:
    frame: int = 0
    number: int = 0
    name: str = ""
    popularity: int = 99
    odds: Optional[float] = None
    jockey: str = ""
    weight: float = 0.0
    bodyweight: int = 0
    body_diff: int = 0
    races: List[PastRace] = field(default_factory=list)

    recent_score: int = 0
    aptitude_score: int = 0
    pace_score: int = 0
    bonus_score: int = 0
    total: int = 0
    style: str = "不明"
    mark: str = ""
    reasons: List[str] = field(default_factory=list)
    cautions: List[str] = field(default_factory=list)


# ==============================
# 共通ユーティリティ
# ==============================

PLACES = [
    "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
    "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋",
    "園田", "姫路", "高知", "佐賀", "帯広"
]

IGNORE_WORDS = [
    "馬メモ", "レース別馬メモ", "全角100文字以内", "削除保存", "閉じる", "編集",
    "次走買い", "次走消し", "不利", "馬場向かず", "ペース合わず", "ハイレベル戦",
    "好ラップ", "映像を見る"
]


def clean_lines(text: str) -> List[str]:
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(w in line for w in IGNORE_WORDS):
            continue
        if re.fullmatch(r"\d+/100|\d+/500", line):
            continue
        lines.append(line)
    return lines


def to_int(value, default=99):
    try:
        return int(value)
    except Exception:
        return default


def parse_number_list(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", text or "")]


# ==============================
# 出走表パーサー
# ==============================

def extract_odds_popularity(block: str) -> Tuple[Optional[float], int]:
    odds = None
    popularity = 99

    pop = re.search(r"(\d+)\s*人気", block)
    if pop:
        popularity = int(pop.group(1))

    odd = re.search(r"(\d+\.\d+)", block)
    if odd:
        try:
            odds = float(odd.group(1))
        except Exception:
            odds = None

    return odds, popularity


def parse_weight_body(block: str) -> Tuple[float, int, int]:
    weight = 0.0
    body = 0
    diff = 0

    # 斤量 56.0 / 斤量だけ独立して出るケースにも対応
    w = re.search(r"(?:^|\s)(\d{2}(?:\.\d)?)(?:\s|$)", block)
    if w:
        try:
            val = float(w.group(1))
            if 48 <= val <= 65:
                weight = val
        except Exception:
            pass

    b = re.search(r"(\d{3})kg\s*\(([+-]?\d+)\)", block)
    if b:
        body = int(b.group(1))
        diff = int(b.group(2))
    else:
        b2 = re.search(r"(\d{3})kg", block)
        if b2:
            body = int(b2.group(1))

    return weight, body, diff


def make_horse(frame, number, name, block="") -> Horse:
    odds, pop = extract_odds_popularity(block)
    weight, body, diff = parse_weight_body(block)

    jockey = ""
    # 騎手は厳密に取りすぎると馬名を拾うので、ここでは空でもOKにする
    jockey_candidates = re.findall(r"(?:替)?([一-龥ァ-ヴー]{2,5})\s*(?:\d{2}(?:\.\d)?)", block)
    if jockey_candidates:
        jockey = jockey_candidates[-1]

    return Horse(
        frame=frame,
        number=number,
        name=name.strip(),
        popularity=pop,
        odds=odds,
        jockey=jockey,
        weight=weight,
        bodyweight=body,
        body_diff=diff,
    )


def parse_pc_racecard(lines: List[str]) -> List[Horse]:
    horses = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\d+)\s+(\d+)$", lines[i])
        if not m:
            i += 1
            continue

        frame = int(m.group(1))
        number = int(m.group(2))
        j = i + 1
        while j < len(lines) and lines[j] == "--":
            j += 1
        if j >= len(lines):
            i += 1
            continue
        name = lines[j]
        if re.fullmatch(r"\d+", name) or "人気" in name or re.search(r"\d+\.\d+", name):
            i += 1
            continue

        k = j + 1
        block = []
        while k < len(lines):
            if re.match(r"^\d+\s+\d+$", lines[k]):
                break
            block.append(lines[k])
            k += 1
        horses.append(make_horse(frame, number, name, " ".join(block)))
        i = k
    return horses


def parse_smartphone_racecard(lines: List[str]) -> List[Horse]:
    horses = []
    i = 0
    while i < len(lines):
        if not re.fullmatch(r"\d+", lines[i]):
            i += 1
            continue
        number = int(lines[i])
        found = False
        name = ""
        db_idx = -1
        for j in range(i + 1, min(i + 12, len(lines))):
            if "のデータベース" in lines[j]:
                db_idx = j
                name = lines[j - 1].replace("  ", "").strip()
                found = True
                break
        if not found or not name or re.fullmatch(r"\d+", name):
            i += 1
            continue
        frame = (number + 1) // 2
        block = " ".join(lines[i:min(i + 45, len(lines))])
        horses.append(make_horse(frame, number, name, block))
        i = db_idx + 1
    return horses


def parse_racecard(text: str) -> List[Horse]:
    lines = clean_lines(text)
    candidates = []
    if any("のデータベース" in l for l in lines):
        candidates.append(parse_smartphone_racecard(lines))
    candidates.append(parse_pc_racecard(lines))

    best = []
    best_score = -1
    for c in candidates:
        if not c:
            continue
        score = len(c) * 10 + sum(1 for h in c if h.popularity != 99)
        if score > best_score:
            best = c
            best_score = score

    unique = {h.number: h for h in best if h.name}
    return sorted(unique.values(), key=lambda h: h.number)


# ==============================
# 現在条件の取得
# ==============================

def parse_current_condition(text: str) -> Dict[str, object]:
    result = {"place": "", "surface": "", "distance": 0}
    for line in text.splitlines():
        for p in PLACES:
            if p in line:
                result["place"] = p
                break
        m = re.search(r"(芝|ダ|ダート)\s*(\d{3,4})", line)
        if m:
            result["surface"] = "ダ" if m.group(1) in ["ダ", "ダート"] else "芝"
            result["distance"] = int(m.group(2))
    return result


# ==============================
# 馬柱パーサー
# ==============================

def is_horse_start_for_past(lines: List[str], idx: int, horse_names: set) -> Optional[str]:
    line = lines[idx]
    if line in horse_names:
        return line
    if idx + 3 < len(lines) and "のデータベース" in lines[idx + 2]:
        # スマホ：馬番 / 馬名 / -- / 馬名のデータベース
        if lines[idx + 1] in horse_names:
            return lines[idx + 1]
    return None


def parse_race_header(line: str) -> Optional[PastRace]:
    r = PastRace(raw=line)

    # 中央PC例：2026.06.07 東京5 3歳未勝利 ダ1300 1:19.7 良
    m_date = re.match(r"^(\d{4}\.\d{2}\.\d{2})\s+(.+)$", line)
    if m_date:
        r.date = m_date.group(1)
        rest = m_date.group(2)
        for p in PLACES:
            if p in rest:
                r.place = p
                break
        md = re.search(r"(芝|ダ|ダート)(\d{3,4})", rest)
        if md:
            r.surface = "ダ" if md.group(1) in ["ダ", "ダート"] else "芝"
            r.distance = int(md.group(2))
        for c in ["稍重", "不良", "良", "重", "稍"]:
            if c in rest:
                r.condition = "稍重" if c == "稍" else c
                break
        mt = re.search(r"(\d:\d{2}\.\d)", rest)
        if mt:
            # 今はタイムを直接点数化しない。後で拡張用。
            pass
        return r

    # 地方スマホ例：06/02  船橋 1R
    m_local = re.match(r"^(\d{2}/\d{2})\s+(.+)$", line)
    if m_local:
        r.date = m_local.group(1)
        rest = m_local.group(2)
        for p in PLACES:
            if p in rest:
                r.place = p
                break
        return r

    return None


def parse_past_performances(text: str, horses: List[Horse]) -> List[Horse]:
    lines = clean_lines(text)
    horse_by_name = {h.name: h for h in horses}
    horse_names = set(horse_by_name.keys())
    current: Optional[Horse] = None
    current_race: Optional[PastRace] = None

    for idx, line in enumerate(lines):
        hs = is_horse_start_for_past(lines, idx, horse_names)
        if hs:
            current = horse_by_name[hs]
            current_race = None
            continue

        if current is None:
            continue

        header = parse_race_header(line)
        if header:
            current.races.append(header)
            current_race = header
            continue

        if not current.races:
            continue
        r = current.races[-1]

        # 地方スマホは日付行の後に着順だけの行が出る
        if re.fullmatch(r"\d+", line) and r.finish == 99:
            val = int(line)
            if 1 <= val <= 18:
                r.finish = val
                continue

        # 頭数・人気
        fs = re.search(r"(\d+)頭", line)
        if fs:
            # field_sizeは今回は保持しないが、人気抽出の補助に使える
            pass
        pop = re.search(r"(\d+)人気", line)
        if pop:
            r.popularity = int(pop.group(1))

        # 距離・馬場・タイム
        md = re.search(r"(芝|ダ|ダート)(\d{3,4})", line)
        if md:
            r.surface = "ダ" if md.group(1) in ["ダ", "ダート"] else "芝"
            r.distance = int(md.group(2))
        for c in ["稍重", "不良", "良", "重", "稍"]:
            if c in line:
                r.condition = "稍重" if c == "稍" else c
                break

        # 斤量・馬体重
        jw = re.search(r"([一-龥ァ-ヴー]{2,6})\s+(\d{2}(?:\.\d)?)", line)
        if jw and r.jockey == "":
            r.jockey = jw.group(1)
            try:
                r.weight = float(jw.group(2))
            except Exception:
                pass
        bw = re.search(r"(\d{3})kg", line)
        if bw:
            r.bodyweight = int(bw.group(1))
        bd = re.search(r"\(([+-]\d+)\)", line)
        if bd:
            try:
                r.body_diff = int(bd.group(1))
            except Exception:
                pass

        # 着差：相手名(0.3) など
        mg = re.search(r"\((\d+\.\d)\)\s*$", line)
        if mg:
            try:
                r.margin = float(mg.group(1))
            except Exception:
                pass

        # 通過順位：- 1 1 1 / 4-5 / 3-3-4-3
        ml = re.search(r"-\s*(\d+\s+\d+\s+\d+)", line)
        if ml:
            r.passing = ml.group(1).replace(" ", "-")
        else:
            mp = re.search(r"(\d+(?:-\d+)+)", line)
            if mp and not re.search(r"\d{4}\.\d{2}\.\d{2}", line):
                r.passing = mp.group(1)

    for h in horses:
        h.races = h.races[:9]
    return horses


# ==============================
# 評価エンジン
# ==============================

def get_style(horse: Horse) -> str:
    positions = []
    for r in horse.races[:5]:
        nums = re.findall(r"\d+", r.passing or "")
        if not nums:
            continue
        positions.append(int(nums[0]))
    if not positions:
        return "不明"
    avg = sum(positions) / len(positions)
    if avg <= 2.5:
        return "逃げ"
    if avg <= 5:
        return "先行"
    if avg <= 9:
        return "差し"
    return "追込"


def eval_recent(h: Horse) -> int:
    score = 0
    recent = h.races[:5]
    if not recent:
        return 0
    for idx, r in enumerate(recent):
        weight = 1.4 if idx < 3 else 1.0
        base = 0
        if r.finish == 1:
            base = 10
        elif r.finish == 2:
            base = 8
        elif r.finish == 3:
            base = 6
        elif r.finish <= 5:
            base = 4
        elif r.finish <= 8:
            base = 2
        if r.margin <= 0.2:
            base += 4
        elif r.margin <= 0.5:
            base += 2
        elif r.margin <= 1.0:
            base += 1
        score += int(base * weight)
    if score >= 35:
        h.reasons.append("近走内容◎")
    elif score >= 22:
        h.reasons.append("近走安定")
    return score


def eval_aptitude(h: Horse, current: Dict[str, object], track_condition: str, good_track: List[int]) -> int:
    score = 0
    cur_dist = int(current.get("distance") or 0)
    cur_place = str(current.get("place") or "")
    cur_surface = str(current.get("surface") or "")

    same_dist = near_dist = dist_good = 0
    same_place = place_good = 0
    same_cond = cond_good = 0
    same_surface = surface_good = 0

    for r in h.races:
        if cur_dist and r.distance:
            if abs(r.distance - cur_dist) <= 100:
                same_dist += 1
                if r.finish <= 3:
                    dist_good += 1
            elif abs(r.distance - cur_dist) <= 200:
                near_dist += 1
        if cur_place and r.place == cur_place:
            same_place += 1
            if r.finish <= 3:
                place_good += 1
        if track_condition and r.condition == track_condition:
            same_cond += 1
            if r.finish <= 3:
                cond_good += 1
        if cur_surface and r.surface == cur_surface:
            same_surface += 1
            if r.finish <= 3:
                surface_good += 1

    if same_dist >= 2:
        score += 8 + dist_good * 3
        h.reasons.append("距離適性")
    elif near_dist >= 2:
        score += 5
        h.reasons.append("近い距離経験")

    if same_place >= 2:
        score += 6 + place_good * 3
        h.reasons.append("コース適性")
    elif same_place == 1 and place_good:
        score += 4

    if same_cond >= 2:
        score += 5 + cond_good * 3
        h.reasons.append("馬場適性")

    if same_surface >= 3:
        score += min(8, surface_good * 2 + 2)

    if h.number in good_track:
        score += 8
        h.reasons.append("手入力:馬場得意")

    return score


def eval_pace(h: Horse, track_condition: str, good_frames: List[int]) -> int:
    score = 0
    h.style = get_style(h)
    front_count = 0
    for r in h.races[:5]:
        nums = re.findall(r"\d+", r.passing or "")
        if nums and int(nums[0]) <= 3:
            front_count += 1

    if h.style == "逃げ":
        score += 10
        h.reasons.append("逃げ脚質")
    elif h.style == "先行":
        score += 8
        h.reasons.append("先行力")
    elif h.style == "差し":
        score += 4
    elif h.style == "追込":
        score += 1
        h.cautions.append("展開待ち")

    if front_count >= 3:
        score += 6
        h.reasons.append("近走前目")

    if track_condition in ["重", "不良"]:
        if h.style == "逃げ":
            score += 8
            h.reasons.append("重不良前残り")
        elif h.style == "先行":
            score += 5
            h.reasons.append("重不良先行")

    if h.frame in good_frames:
        score += 5
        h.reasons.append("有利枠")

    return score


def eval_bonus(h: Horse) -> int:
    score = 0
    # 人気以上に走った実績
    for r in h.races[:5]:
        if r.popularity >= 7 and r.finish <= 3:
            score += 5
        elif r.popularity >= 10 and r.finish <= 5:
            score += 4
    if score >= 6:
        h.reasons.append("人気以上に好走歴")

    # 騎手継続
    if h.races and h.jockey and h.races[0].jockey and h.jockey == h.races[0].jockey:
        score += 4
        h.reasons.append("継続騎乗")

    # 馬体重変動注意だけ
    if h.races and abs(h.races[0].body_diff) >= 15:
        h.cautions.append("前走馬体重変動大")

    return score


def evaluate_all(horses: List[Horse], current: Dict[str, object], track_condition: str, good_frames: List[int], good_track: List[int]) -> List[Horse]:
    for h in horses:
        h.reasons = []
        h.cautions = []
        h.recent_score = eval_recent(h)
        h.aptitude_score = eval_aptitude(h, current, track_condition, good_track)
        h.pace_score = eval_pace(h, track_condition, good_frames)
        h.bonus_score = eval_bonus(h)
        # 馬柱重視：近走45%、適性30%、脚質展開20%、補助5%
        h.total = h.recent_score + h.aptitude_score + h.pace_score + h.bonus_score
        if h.popularity >= 10:
            h.cautions.append("10番人気以下は原則消し")
    return horses


# ==============================
# 予想ロジック
# ==============================

def make_marks(horses: List[Horse]) -> Dict[str, Horse]:
    marks = {}
    top3 = sorted([h for h in horses if h.popularity <= 3], key=lambda x: x.total, reverse=True)
    if not top3:
        top3 = sorted(horses, key=lambda x: x.total, reverse=True)[:3]
    if not top3:
        return marks
    axis = top3[0]
    axis.mark = "◎"
    marks["◎"] = axis

    remain = [h for h in horses if h.number != axis.number and h.popularity <= 9]
    remain = sorted(remain, key=lambda x: x.total, reverse=True)
    labels = ["〇", "▲", "△", "☆"]
    for label, h in zip(labels, remain[:4]):
        h.mark = label
        marks[label] = h
    return marks


def ability_rank(horses: List[Horse]) -> List[Horse]:
    return sorted(horses, key=lambda x: x.total, reverse=True)


def cut_horses(horses: List[Horse]) -> List[Horse]:
    return sorted([h for h in horses if h.popularity >= 10], key=lambda x: x.popularity)


def hole_rank(horses: List[Horse]) -> List[Horse]:
    return sorted([h for h in horses if 4 <= h.popularity <= 9], key=lambda x: x.total, reverse=True)


def make_bets(marks: Dict[str, Horse]) -> Dict[str, List[str]]:
    bets = {"馬連": [], "ワイド": [], "3連単": []}
    if "◎" not in marks:
        return bets
    a = marks["◎"].number

    for label in ["〇", "▲", "△"]:
        if label in marks:
            bets["馬連"].append(f"{a}-{marks[label].number}")

    for label in ["▲", "△"]:
        if label in marks:
            bets["ワイド"].append(f"{a}-{marks[label].number}")
    if "▲" in marks and "△" in marks:
        bets["ワイド"].append(f"{marks['▲'].number}-{marks['△'].number}")

    if all(k in marks for k in ["◎", "〇", "▲"]):
        o = marks["〇"].number
        c = marks["▲"].number
        bets["3連単"].extend([f"{a}→{o}→{c}", f"{a}→{c}→{o}"])
    if all(k in marks for k in ["◎", "〇", "△"]):
        o = marks["〇"].number
        d = marks["△"].number
        bets["3連単"].extend([f"{a}→{o}→{d}", f"{a}→{d}→{o}"])
    if all(k in marks for k in ["◎", "〇", "▲"]):
        o = marks["〇"].number
        c = marks["▲"].number
        bets["3連単"].extend([f"{o}→{a}→{c}", f"{c}→{a}→{o}"])
    return bets


def grade(h: Horse) -> str:
    if h.total >= 70:
        return "S"
    if h.total >= 55:
        return "A"
    if h.total >= 40:
        return "B"
    if h.total >= 25:
        return "C"
    return "D"


def comment(h: Horse) -> str:
    if not h.reasons:
        return "強調材料は少なめ。"
    return " / ".join(h.reasons[:5])


# ==============================
# Streamlit UI
# ==============================

st.title("競馬AI2.0")
st.caption("出走表・馬柱9走・有利枠・馬場得意馬だけで予想するシンプル版")

if "clear_count" not in st.session_state:
    st.session_state.clear_count = 0
if st.button("🗑️ 入力内容をクリア"):
    st.session_state.clear_count += 1

col1, col2 = st.columns(2)
with col1:
    racecard_text = st.text_area("① 出走表を貼り付け", height=430, key=f"race_{st.session_state.clear_count}")
with col2:
    past_text = st.text_area("② 馬柱9走を貼り付け", height=430, key=f"past_{st.session_state.clear_count}")

col3, col4 = st.columns(2)
with col3:
    good_frame_text = st.text_input("③ 有利枠（例：1,3,8）", key=f"frame_{st.session_state.clear_count}")
with col4:
    good_track_text = st.text_input("④ 今回の馬場状態が得意な馬番（例：2,7,11）", key=f"track_{st.session_state.clear_count}")

track_condition = st.selectbox("馬場状態", ["良", "稍重", "重", "不良"])

if st.button("予想開始"):
    good_frames = parse_number_list(good_frame_text)
    good_track = parse_number_list(good_track_text)
    current = parse_current_condition(racecard_text + "\n" + past_text)

    horses = parse_racecard(racecard_text)
    if not horses:
        st.error("出走表を読み取れませんでした。出走表を少し広めにコピーしてください。")
        st.stop()

    horses = parse_past_performances(past_text, horses)
    horses = evaluate_all(horses, current, track_condition, good_frames, good_track)
    marks = make_marks(horses)
    bets = make_bets(marks)
    ability = ability_rank(horses)
    holes = hole_rank(horses)
    cuts = cut_horses(horses)

    st.success(f"{len(horses)}頭を読み取りました。")
    st.write(f"馬場状態：{track_condition}")
    if current.get("place") or current.get("distance"):
        st.caption(f"推定条件：{current.get('place','')} {current.get('surface','')}{current.get('distance','')}m")

    st.header("AI印")
    for label in ["◎", "〇", "▲", "△", "☆"]:
        if label not in marks:
            continue
        h = marks[label]
        st.markdown(f"### {label} {h.number} {h.name}｜{h.popularity}番人気｜能力{h.total}｜ランク{grade(h)}")
        st.write(comment(h))
        if h.cautions:
            st.caption("注意: " + " / ".join(h.cautions))

    st.divider()
    st.header("買い目")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("馬連")
        st.code(" / ".join(bets["馬連"]) if bets["馬連"] else "なし")
    with c2:
        st.subheader("ワイド")
        st.code(" / ".join(bets["ワイド"]) if bets["ワイド"] else "なし")
    with c3:
        st.subheader("3連単")
        st.code(" / ".join(bets["3連単"]) if bets["3連単"] else "なし")

    st.divider()
    st.header("能力ランキング")
    for i, h in enumerate(ability, 1):
        st.write(
            f"{i}位　{h.number} {h.name}｜{h.popularity}番人気｜能力{h.total}｜"
            f"近走{h.recent_score} / 適性{h.aptitude_score} / 展開{h.pace_score} / 補助{h.bonus_score}｜脚質{h.style}"
        )
        if h.reasons:
            st.caption(" / ".join(h.reasons))
        if h.cautions:
            st.caption("注意: " + " / ".join(h.cautions))

    st.divider()
    st.header("穴候補（4〜9番人気）")
    if holes:
        for h in holes[:5]:
            st.write(f"{h.number} {h.name}｜{h.popularity}番人気｜能力{h.total}｜{comment(h)}")
    else:
        st.write("穴候補なし")

    st.divider()
    st.header("消し馬（10番人気以下）")
    if cuts:
        for h in cuts:
            st.write(f"{h.number} {h.name}｜{h.popularity}番人気｜能力{h.total}")
    else:
        st.write("消し馬なし")

    with st.expander("読み取り確認：馬柱レース数"):
        for h in horses:
            st.write(f"{h.number} {h.name}: {len(h.races)}走")
