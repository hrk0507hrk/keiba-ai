import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="競馬AI Ver5", page_icon="🐎", layout="wide")

TIME_COLUMNS = ("overall", "start", "chase", "closing", "avg5")
TIME_LABELS = {
    "overall": "全体",
    "start": "スタート",
    "chase": "追走",
    "closing": "上がり",
    "avg5": "5走平均",
}
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
    overall: int = 0
    start: int = 0
    chase: int = 0
    closing: int = 0
    avg5: int = 0
    distance: int = 0
    course: int = 0
    last3: int = 0
    last2: int = 0
    last1: int = 0


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
    """着順を取得。netkeiba馬柱では日付行末の数字が着順。"""
    match = re.search(r"(\d{1,2})\s*着", line)
    if match:
        return safe_int(match.group(1), 99)

    # 例: 2026.05.17 新潟6 / 2026.02.25 浦和13
    match = re.match(
        r"^20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?\s+.+?(\d{1,2})$",
        normalize_text(line),
    )
    if match:
        value = safe_int(match.group(1), 99)
        if 1 <= value <= 30:
            return value

    return 99


def parse_margin(line: str) -> float:
    """勝ち馬名の直後にある着差を取得。馬体重・上がりは除外する。"""
    for pattern in (
        r"着差\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)",
        r"(?:差|着差)\s*([+-]?\d+(?:\.\d+)?)",
    ):
        match = re.search(pattern, line)
        if match:
            return abs(safe_float(match.group(1), 99.9))

    # 例: マリアイリダータ(0.6) / アロヒアリイ(-0.1)
    # 行末の括弧だけを見ることで、馬体重や上がりと混同しない。
    match = re.search(r"\(([+-]?\d+(?:\.\d+)?)\)\s*$", line)
    if match:
        return abs(safe_float(match.group(1), 99.9))

    if any(word in line for word in ("クビ", "ハナ", "アタマ")):
        return 0.1
    if "同着" in line:
        return 0.0
    return 99.9


def parse_passing(line: str) -> str:
    # 例: 11-9 (33.5) 500(0)
    match = re.search(r"^\s*(\d{1,2}(?:-\d{1,2}){1,3})(?:\s|$)", line)
    return match.group(1) if match else ""


def parse_class(line: str) -> int:
    normalized = line.upper().replace("Ｇ", "G")
    for keyword, score in CLASS_TABLE:
        if keyword.upper() in normalized:
            return score
    return 3


def contains_race_date(line: str) -> bool:
    return bool(
        re.match(
            r"^20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?\s+",
            normalize_text(line),
        )
    )


def past_horse_number(line: str, horses: Dict[int, Horse]) -> Optional[int]:
    """netkeiba馬柱の「枠番 馬番」だけの行から馬番を取得する。"""
    normalized = normalize_text(line)

    # 例: 1 1 / 5 6 / 8 12
    match = re.fullmatch(r"([1-8])\s+([1-9]|1[0-8])", normalized)
    if match:
        number = safe_int(match.group(2))
        if number in horses:
            return number

    # 例: 6番 馬名 / 6 馬名（別形式への保険）
    match = re.match(r"^(\d{1,2})番(?:\s+|$)", normalized)
    if match:
        number = safe_int(match.group(1))
        if number in horses:
            return number

    for number, horse in horses.items():
        if horse.name and horse.name in normalized:
            return number

    return None


def record_from_lines(block_lines: List[str]) -> Optional[RaceRecord]:
    if not block_lines:
        return None

    finish = parse_finish(block_lines[0])
    if finish >= 99:
        return None

    race_class = 3
    passing = ""
    margin = 99.9

    for line in block_lines[1:]:
        # クラスはレース名行から取得
        parsed_class = parse_class(line)
        if parsed_class != 3 or race_class == 3:
            race_class = parsed_class

        if not passing:
            passing = parse_passing(line)

        parsed_margin = parse_margin(line)
        if parsed_margin < 99.9:
            margin = parsed_margin

    return RaceRecord(
        finish=finish,
        margin=margin,
        passing=passing,
        race_class=race_class,
    )


def parse_past_performances(
    text: str,
    horses: Dict[int, Horse],
) -> Dict[int, Horse]:
    """netkeiba複数行馬柱を枠番・馬番行ごとのブロックで読む。"""
    for horse in horses.values():
        horse.records.clear()

    lines = normalize_lines(text)
    current: Optional[Horse] = None
    race_block: List[str] = []
    waiting_name = False
    header_candidates: List[str] = []

    def flush_race() -> None:
        nonlocal race_block
        if current is not None and race_block and len(current.records) < 5:
            record = record_from_lines(race_block)
            if record is not None:
                current.records.append(record)
        race_block = []

    def usable_name(line: str) -> bool:
        if line == "--" or line.startswith("("):
            return False
        if re.search(r"kg|人気|美浦|栗東|地方|中\d+週|牡\d|牝\d|セ\d|騙\d", line):
            return False
        return bool(re.fullmatch(r"[A-Za-zＡ-Ｚａ-ｚ一-龥ぁ-んァ-ヶー・ヴー]+B?", line))

    for line in lines:
        # netkeiba形式: 「枠番 馬番」
        m = re.fullmatch(r"([1-8])\s+([1-9]|1[0-8])", line)
        if m:
            flush_race()
            number = safe_int(m.group(2))
            current = horses.get(number)
            if current is None:
                current = Horse(number=number, name=f"{number}番")
                horses[number] = current
            waiting_name = True
            header_candidates = []
            continue

        if current is None:
            continue

        if waiting_name:
            if usable_name(line):
                header_candidates.append(line)
                # 血統欄は「父→馬名→母」の順なので2件目が馬名
                if len(header_candidates) >= 2:
                    current.name = header_candidates[1]
                    waiting_name = False
            continue

        if contains_race_date(line):
            flush_race()
            race_block = [line]
            continue

        if race_block:
            race_block.append(line)

    flush_race()
    return horses

def time_index_cells(text: str) -> List[str]:
    """タイム指数表をセル単位に分解する。

    PC版のタブ区切りと、スマホ・ブラウザコピー時の縦並びの両方に対応する。
    """
    text = text.replace("\u3000", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "\n")
    return [re.sub(r"[ ]{2,}", " ", cell).strip() for cell in text.split("\n") if cell.strip()]


def parse_index_value(value: str) -> int:
    """指数セルを整数化。「未」「-」は0、末尾の*は除去する。"""
    value = normalize_text(value).replace("＊", "*")
    value = value.rstrip("*")
    if value in {"未", "-", "--", "―", "－", "なし"}:
        return 0
    match = re.fullmatch(r"-?\d+", value)
    return safe_int(match.group(), 0) if match else 0


def is_frame_cell(value: str) -> bool:
    return bool(re.fullmatch(r"[1-8]", normalize_text(value)))


def is_number_cell(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[1-9]|1[0-8])", normalize_text(value)))


def find_time_row_starts(cells: List[str]) -> List[int]:
    """「枠・馬番・--」の3セルを行頭として検出する。"""
    starts: List[int] = []
    for i in range(len(cells) - 2):
        if (
            is_frame_cell(cells[i])
            and is_number_cell(cells[i + 1])
            and cells[i + 2] in {"--", "－", "―"}
        ):
            starts.append(i)
    return starts


def parse_time_row(row: List[str]) -> Optional[dict]:
    """1頭分のタイム指数行を位置固定で解析する。

    行構成:
    枠, 馬番, 印, 馬名, 性齢, 斤量, 騎手,
    全体, スタート, 追走, 上がり, 5走平均,
    距離, コース, 3走, 2走, 前走, 単勝オッズ, 人気

    ※表の「最高」は全体・スタート・追走・上がりを束ねる見出しで、
    独立した数値列ではない。
    """
    if len(row) < 19:
        return None

    number = safe_int(row[1], 0)
    if not 1 <= number <= 18:
        return None

    # 先頭7セルは固定。指数列は全体から前走まで10セル。
    values = [parse_index_value(value) for value in row[7:17]]
    if len(values) != 10:
        return None

    odds = safe_float(row[17], 0.0)
    popularity = safe_int(row[18], 99)

    return {
        "number": number,
        "frame": safe_int(row[0], 0),
        "name": row[3],
        "jockey": row[6],
        "highest": 0,
        "overall": values[0],
        "start": values[1],
        "chase": values[2],
        "closing": values[3],
        "avg5": values[4],
        "distance": values[5],
        "course": values[6],
        "last3": values[7],
        "last2": values[8],
        "last1": values[9],
        "odds": odds,
        "popularity": popularity,
    }


def parse_time_index(text: str, horses: Dict[int, Horse]) -> Dict[int, Horse]:
    """netkeibaタイム指数を列位置どおりに読み取る。"""
    for horse in horses.values():
        horse.timeindex = TimeIndex()

    cells = time_index_cells(text)
    starts = find_time_row_starts(cells)

    for pos, start_index in enumerate(starts):
        end_index = starts[pos + 1] if pos + 1 < len(starts) else len(cells)
        parsed = parse_time_row(cells[start_index:end_index])
        if parsed is None:
            continue

        number = parsed["number"]
        horse = horses.get(number)
        if horse is None:
            horse = Horse(number=number, name=parsed["name"])
            horses[number] = horse

        horse.name = parsed["name"] or horse.name
        horse.frame = parsed["frame"] or horse.frame
        horse.jockey = parsed["jockey"] or horse.jockey
        horse.popularity = parsed["popularity"]
        horse.timeindex = TimeIndex(
            highest=parsed["highest"],
            overall=parsed["overall"],
            start=parsed["start"],
            chase=parsed["chase"],
            closing=parsed["closing"],
            avg5=parsed["avg5"],
            distance=parsed["distance"],
            course=parsed["course"],
            last3=parsed["last3"],
            last2=parsed["last2"],
            last1=parsed["last1"],
        )

    return horses

def time_value(horse: Horse, column: str) -> int:
    return getattr(horse.timeindex, column)


def extract_top3(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    """各項目の上位3つの指数値を採用し、同値は全頭含める。"""
    for horse in horses.values():
        horse.top3_count = 0

    for column in TIME_COLUMNS:
        valid = [horse for horse in horses.values() if time_value(horse, column) > 0]
        if not valid:
            continue

        top3_values = set(
            sorted(
                {time_value(horse, column) for horse in valid},
                reverse=True,
            )[:3]
        )

        for horse in valid:
            if time_value(horse, column) in top3_values:
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


st.title("🐎 競馬AI Ver5.1 解析安定版")
st.caption("タイム指数60点＋馬柱40点｜タイム指数は列固定・同値含む上位3指数値")

def clear_inputs() -> None:
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""


racecard_text = st.text_area(
    "① 出走表",
    height=260,
    placeholder="出走表を貼り付け",
    key="racecard_input",
)
past_text = st.text_area(
    "② 馬柱",
    height=420,
    placeholder="馬柱を貼り付け",
    key="past_input",
)
timeindex_text = st.text_area(
    "③ netkeibaタイム指数",
    height=320,
    placeholder="タイム指数を貼り付け",
    key="timeindex_input",
)

button_col1, button_col2 = st.columns([4, 1])

with button_col1:
    predict_clicked = st.button(
        "予想開始",
        type="primary",
        use_container_width=True,
    )

with button_col2:
    st.button(
        "クリア",
        use_container_width=True,
        on_click=clear_inputs,
    )

if predict_clicked:
    horses = parse_racecard(racecard_text)
    horses = parse_past_performances(past_text, horses)
    horses = parse_time_index(timeindex_text, horses)

    parsed_horses = len(horses)
    parsed_records = sum(len(h.records) for h in horses.values())
    parsed_record_horses = sum(1 for h in horses.values() if h.records)

    with st.expander("読み取り確認", expanded=False):
        st.write(f"認識馬数：{parsed_horses}頭")
        st.write(f"馬柱認識：{parsed_record_horses}頭・合計{parsed_records}走")
        st.dataframe(
            pd.DataFrame([
                {
                    "馬番": h.number,
                    "馬名": h.name,
                    "近走取得数": len(h.records),
                }
                for h in sorted(horses.values(), key=lambda x: x.number)
            ]),
            use_container_width=True,
            hide_index=True,
        )
        st.write("タイム指数読み取り")
        st.dataframe(
            pd.DataFrame([
                {
                    "馬番": h.number,
                    "馬名": h.name,
                    "全体": h.timeindex.overall,
                    "スタート": h.timeindex.start,
                    "追走": h.timeindex.chase,
                    "上がり": h.timeindex.closing,
                    "5走平均": h.timeindex.avg5,
                }
                for h in sorted(horses.values(), key=lambda x: x.number)
            ]),
            use_container_width=True,
            hide_index=True,
        )

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
