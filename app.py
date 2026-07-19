import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="競馬AI Ver5", page_icon="🐎", layout="wide")

TIME_COLUMNS = ("highest", "avg5", "start", "chase", "closing")
APPEARANCE_SCORE = {1: 20, 2: 34, 3: 46, 4: 54, 5: 60}
MARKS = ("◎", "○", "▲", "★", "△")
CLASS_TABLE = (
    ("G1", 10), ("GI", 10), ("G2", 9), ("GII", 9),
    ("G3", 8), ("GIII", 8), ("リステッド", 7), ("L", 7),
    ("OP", 7), ("オープン", 7), ("3勝", 6), ("1600万", 6),
    ("2勝", 5), ("1000万", 5), ("1勝", 4), ("500万", 4),
    ("未勝利", 2), ("新馬", 1),
)


@dataclass
class RaceRecord:
    finish: int = 99
    margin: float = 99.9
    passing: str = ""
    race_class: int = 0


@dataclass
class TimeIndex:
    highest: int = 0
    avg5: int = 0
    start: int = 0
    chase: int = 0
    closing: int = 0


@dataclass
class Horse:
    number: int
    name: str
    jockey: str = ""
    popularity: int = 99
    frame: int = 0
    records: List[RaceRecord] = field(default_factory=list)
    timeindex: TimeIndex = field(default_factory=TimeIndex)
    top3_count: int = 0
    alive: bool = False
    ability_score: int = 0
    stability_score: int = 0
    pace_score: int = 0
    racecard_score: int = 0
    time_score: int = 0
    total_score: int = 0
    mark: str = ""
    reason: str = ""


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\t", " ")
    return re.sub(r"[ ]{2,}", " ", text).strip()


def normalize_lines(text: str) -> List[str]:
    return [value for line in text.splitlines() if (value := normalize_text(line))]


def safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_horse_header(line: str) -> Optional[Tuple[int, str]]:
    if re.search(r"\d{4}[./年]\d{1,2}", line):
        return None
    for pattern in (r"^\s*(\d{1,2})\s+([^\s]+)", r"^\s*(\d{1,2})番\s*([^\s]+)"):
        match = re.match(pattern, line)
        if not match:
            continue
        number = safe_int(match.group(1))
        name = match.group(2).strip()
        if not 1 <= number <= 18:
            continue
        excluded = ("人気", "オッズ", "タイム", "指数", "着", "枠", "馬体重", "通過", "斤量", "前走", "最高")
        if any(word in name for word in excluded):
            continue
        name = re.sub(r"[牡牝セ騙]\d+$", "", name).strip()
        if name:
            return number, name
    return None


def extract_popularity(line: str) -> int:
    for pattern in (r"(\d+)\s*人気", r"人気\s*[:：]?\s*(\d+)"):
        match = re.search(pattern, line)
        if match:
            return safe_int(match.group(1), 99)
    return 99


def extract_frame(line: str) -> int:
    for pattern in (r"(\d+)\s*枠", r"枠\s*[:：]?\s*(\d+)"):
        match = re.search(pattern, line)
        if match:
            value = safe_int(match.group(1))
            if 1 <= value <= 8:
                return value
    return 0


def extract_jockey(line: str) -> str:
    match = re.search(r"騎手\s*[:：]?\s*([^\d／/|]+)", line)
    if not match:
        return ""
    jockey = normalize_text(match.group(1))
    return re.sub(r"\s+\d+(?:\.\d+)?kg.*$", "", jockey).strip()


def parse_racecard(text: str) -> Dict[int, Horse]:
    horses: Dict[int, Horse] = {}
    current: Optional[Horse] = None
    for line in normalize_lines(text):
        header = parse_horse_header(line)
        if header:
            number, name = header
            current = horses.setdefault(number, Horse(number=number, name=name))
            current.name = name or current.name
        if current is None:
            continue
        popularity = extract_popularity(line)
        if popularity != 99:
            current.popularity = popularity
        frame = extract_frame(line)
        if frame:
            current.frame = frame
        jockey = extract_jockey(line)
        if jockey:
            current.jockey = jockey
    return horses


def parse_finish(line: str) -> int:
    match = re.search(r"(\d{1,2})\s*着", line)
    return safe_int(match.group(1), 99) if match else 99


def parse_margin(line: str) -> float:
    for pattern in (r"着差\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)", r"(?:差|着差)\s*([+-]?\d+(?:\.\d+)?)"):
        match = re.search(pattern, line)
        if match:
            return abs(safe_float(match.group(1), 99.9))
    decimal_values = re.findall(r"(?<!\d)([+-]?\d+\.\d)(?!\d)", line)
    plausible = [abs(safe_float(v, 99.9)) for v in decimal_values if abs(safe_float(v, 99.9)) <= 10]
    if plausible:
        return plausible[-1]
    if any(word in line for word in ("クビ", "ハナ", "アタマ")):
        return 0.1
    if "同着" in line:
        return 0.0
    return 99.9


def parse_passing(line: str) -> str:
    match = re.search(r"(?<!\d)(\d{1,2}(?:-\d{1,2}){1,3})(?!\d)", line)
    return match.group(1) if match else ""


def parse_class(line: str) -> int:
    for keyword, score in CLASS_TABLE:
        if keyword in line:
            return score
    return 3


def looks_like_race_record(line: str) -> bool:
    has_date = bool(re.search(r"(?:20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?|\d{1,2}[./]\d{1,2})", line))
    has_finish = bool(re.search(r"\d{1,2}\s*着", line))
    return has_date and has_finish


def parse_past_performances(text: str, horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.records.clear()
    current: Optional[Horse] = None
    for line in normalize_lines(text):
        header = parse_horse_header(line)
        if header:
            current = horses.get(header[0])
            continue
        if current is None or not looks_like_race_record(line):
            continue
        record = RaceRecord(
            finish=parse_finish(line),
            margin=parse_margin(line),
            passing=parse_passing(line),
            race_class=parse_class(line),
        )
        if record.finish < 99:
            current.records.append(record)
    return horses


def numeric_tokens(line: str) -> List[int]:
    return [safe_int(token) for token in re.findall(r"(?<![\d.])-?\d+(?![\d.])", line)]


def find_horse_number_in_line(line: str, horses: Dict[int, Horse]) -> Optional[int]:
    match = re.match(r"^\s*(\d{1,2})(?:\s|番)", line)
    if match:
        number = safe_int(match.group(1))
        if number in horses:
            return number
    for number, horse in horses.items():
        if horse.name and horse.name in line:
            return number
    return None


def parse_time_index(text: str, horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.timeindex = TimeIndex()
    for line in normalize_lines(text):
        number = find_horse_number_in_line(line, horses)
        if number is None:
            continue
        values = numeric_tokens(line)
        if values and values[0] == number:
            values = values[1:]
        values = [v for v in values if -50 <= v <= 200]
        if len(values) < 5:
            continue
        values = values[-5:]
        horses[number].timeindex = TimeIndex(*values)
    return horses


def time_value(horse: Horse, column: str) -> int:
    return getattr(horse.timeindex, column)


def extract_top3(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.top3_count = 0
    for column in TIME_COLUMNS:
        valid = [h for h in horses.values() if time_value(h, column) > 0]
        if not valid:
            continue
        valid.sort(key=lambda h: time_value(h, column), reverse=True)
        border = time_value(valid[min(2, len(valid) - 1)], column)
        for horse in valid:
            if time_value(horse, column) >= border:
                horse.top3_count += 1
    return horses


def survival_check(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.alive = horse.top3_count > 0
    return horses


def rank_bonus_for_column(horses: Dict[int, Horse], column: str) -> Dict[int, int]:
    valid = [h for h in horses.values() if h.alive and time_value(h, column) > 0]
    if not valid:
        return {}
    distinct = sorted({time_value(h, column) for h in valid}, reverse=True)
    bonus: Dict[int, int] = {}
    for horse in valid:
        value = time_value(horse, column)
        if value == distinct[0]:
            bonus[horse.number] = 2
        elif len(distinct) >= 2 and value == distinct[1]:
            bonus[horse.number] = 1
    return bonus


def calc_time_score(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.time_score = APPEARANCE_SCORE.get(horse.top3_count, 0) if horse.alive else 0
    for column in TIME_COLUMNS:
        for number, bonus in rank_bonus_for_column(horses, column).items():
            horses[number].time_score += bonus
    for horse in horses.values():
        horse.time_score = min(horse.time_score, 60)
    return horses


def recent_five(records: List[RaceRecord]) -> List[RaceRecord]:
    return records[:5]


def calc_ability_score(records: List[RaceRecord]) -> int:
    records = recent_five(records)
    if not records:
        return 0
    finishes = [r.finish for r in records if 1 <= r.finish < 99]
    if finishes:
        avg = sum(finishes) / len(finishes)
        finish_score = 10 if avg <= 1.5 else 9 if avg <= 2.5 else 8 if avg <= 3.5 else 7 if avg <= 4.5 else 6 if avg <= 5.5 else 5 if avg <= 6.5 else 4 if avg <= 7.5 else 3 if avg <= 8.5 else 2 if avg <= 10 else 1
    else:
        finish_score = 0
    classes = [r.race_class for r in records if r.race_class > 0]
    if classes:
        avg_class = sum(classes) / len(classes)
        class_score = 6 if avg_class >= 9 else 5 if avg_class >= 7 else 4 if avg_class >= 6 else 3 if avg_class >= 5 else 2 if avg_class >= 3 else 1
    else:
        class_score = 0
    margins = [r.margin for r in records if 0 <= r.margin < 10]
    if margins:
        avg_margin = sum(margins) / len(margins)
        margin_score = 4 if avg_margin <= 0.2 else 3 if avg_margin <= 0.5 else 2 if avg_margin <= 1.0 else 1 if avg_margin <= 1.5 else 0
    else:
        margin_score = 0
    return min(finish_score + class_score + margin_score, 20)


def calc_stability_score(records: List[RaceRecord]) -> int:
    valid = [r for r in recent_five(records) if 1 <= r.finish < 99]
    if not valid:
        return 0
    rate = sum(1 for r in valid if r.finish <= 3) / len(valid)
    return 10 if rate >= 1.0 else 8 if rate >= 0.8 else 6 if rate >= 0.6 else 4 if rate >= 0.4 else 2 if rate >= 0.2 else 0


def calc_pace_score(records: List[RaceRecord]) -> int:
    positions = []
    for record in recent_five(records):
        match = re.search(r"\d{1,2}", record.passing or "")
        if match:
            positions.append(safe_int(match.group()))
    if not positions:
        return 0
    rate = sum(1 for pos in positions if pos <= 3) / len(positions)
    return 10 if rate >= 1.0 else 8 if rate >= 0.8 else 6 if rate >= 0.6 else 4 if rate >= 0.4 else 2 if rate >= 0.2 else 0


def calc_racecard_score(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        if not horse.alive:
            horse.ability_score = horse.stability_score = horse.pace_score = horse.racecard_score = 0
            continue
        horse.ability_score = calc_ability_score(horse.records)
        horse.stability_score = calc_stability_score(horse.records)
        horse.pace_score = calc_pace_score(horse.records)
        horse.racecard_score = min(horse.ability_score + horse.stability_score + horse.pace_score, 40)
    return horses


def finish_scoring(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.total_score = horse.time_score + horse.racecard_score if horse.alive else 0
        horse.mark = ""
    ranking = sorted([h for h in horses.values() if h.alive], key=lambda h: (h.total_score, h.time_score, h.racecard_score, -h.number), reverse=True)
    for index, horse in enumerate(ranking[:len(MARKS)]):
        horse.mark = MARKS[index]
    for horse in horses.values():
        horse.reason = f"TOP3 {horse.top3_count}/5 / 能力 {horse.ability_score}/20 / 安定 {horse.stability_score}/10 / 展開 {horse.pace_score}/10"
    return horses


def validate_inputs(horses: Dict[int, Horse]) -> List[str]:
    errors: List[str] = []
    if not horses:
        return ["出走表から馬を読み取れませんでした。"]
    if not any(any(getattr(h.timeindex, c) > 0 for c in TIME_COLUMNS) for h in horses.values()):
        errors.append("タイム指数を読み取れませんでした。")
    if sum(len(h.records) for h in horses.values()) == 0:
        errors.append("馬柱の近走データを読み取れませんでした。")
    return errors


def result_dataframe(horses: Dict[int, Horse]) -> pd.DataFrame:
    ranking = sorted([h for h in horses.values() if h.alive], key=lambda h: (h.total_score, h.time_score, h.racecard_score, -h.number), reverse=True)
    return pd.DataFrame([
        {
            "印": h.mark, "馬番": h.number, "馬名": h.name,
            "TOP3回数": h.top3_count, "タイム60": h.time_score,
            "能力20": h.ability_score, "安定10": h.stability_score,
            "展開10": h.pace_score, "馬柱40": h.racecard_score,
            "総合100": h.total_score, "評価": h.reason,
        }
        for h in ranking
    ])


st.title("🐎 競馬AI Ver5")
st.caption("タイム指数60点＋馬柱40点")

racecard_text = st.text_area("① 出走表", height=260, placeholder="出走表を貼り付け")
past_text = st.text_area("② 馬柱", height=420, placeholder="馬柱を貼り付け")
timeindex_text = st.text_area("③ netkeibaタイム指数", height=320, placeholder="タイム指数を貼り付け")

if st.button("予想開始", type="primary", use_container_width=True):
    horses = parse_racecard(racecard_text)
    horses = parse_past_performances(past_text, horses)
    horses = parse_time_index(timeindex_text, horses)

    errors = validate_inputs(horses)
    if errors:
        for error in errors:
            st.error(error)
        st.stop()

    horses = extract_top3(horses)
    horses = survival_check(horses)
    horses = calc_time_score(horses)
    horses = calc_racecard_score(horses)
    horses = finish_scoring(horses)

    st.divider()
    st.subheader("予想結果")
    result = result_dataframe(horses)
    if result.empty:
        st.warning("生存馬がいません。タイム指数の貼り付け内容を確認してください。")
    else:
        st.dataframe(result, use_container_width=True, hide_index=True)

    eliminated = pd.DataFrame([
        {"馬番": h.number, "馬名": h.name, "TOP3回数": h.top3_count}
        for h in sorted(horses.values(), key=lambda x: x.number)
        if not h.alive
    ])
    if not eliminated.empty:
        with st.expander("消し馬"):
            st.dataframe(eliminated, use_container_width=True, hide_index=True)
