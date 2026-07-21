import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="競馬AI Ver6", page_icon="🐎", layout="wide")

CENTRAL_TIME_COLUMNS = ("overall", "start", "chase", "closing", "avg5")
LOCAL_TIME_COLUMNS = ("avg5", "distance", "course", "last3", "last2", "last1")
TIME_LABELS = {
    "highest": "最高",
    "overall": "全体",
    "start": "スタート",
    "chase": "追走",
    "closing": "上がり",
    "avg5": "5走平均",
    "distance": "距離",
    "course": "コース",
    "last3": "3走",
    "last2": "2走",
    "last1": "前走",
}
MARKS = ("◎", "○", "▲", "★")
CLASS_TABLE = (
    ("G1", 10), ("GI", 10), ("G2", 9), ("GII", 9),
    ("G3", 8), ("GIII", 8), ("リステッド", 7), ("L", 7),
    ("OP", 7), ("オープン", 7), ("3勝", 6), ("1600万", 6),
    ("2勝", 5), ("1000万", 5), ("1勝", 4), ("500万", 4),
    ("未勝利", 2), ("新馬", 1),
)
VENUES = (
    "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
    "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋",
    "園田", "姫路", "高知", "佐賀", "帯広"
)


@dataclass
class RaceConditions:
    venue: str = ""
    surface: str = ""
    distance: int = 0
    going: str = ""


@dataclass
class BestRecord:
    time_seconds: float = 9999.0
    date: str = ""
    venue: str = ""
    surface: str = ""
    distance: int = 0
    going: str = ""
    match_level: int = 0


@dataclass
class RaceRecord:
    finish: int = 99
    margin: float = 99.9
    passing: str = ""
    race_class: int = 0
    date: str = ""
    venue: str = ""
    surface: str = ""
    distance: int = 0
    going: str = ""
    time_seconds: float = 9999.0


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
    alive: bool = True
    time_score: int = 0
    best_record: BestRecord = field(default_factory=BestRecord)
    record_score: int = 0
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


def parse_race_conditions(text: str) -> RaceConditions:
    normalized = normalize_text(text).replace("ダート", "ダ").replace("芝コース", "芝")

    venue = ""
    for candidate in VENUES:
        if candidate in normalized:
            venue = candidate
            break

    surface = ""
    distance = 0
    surface_distance_patterns = (
        r"(芝|ダ|障)\s*[右左直内外]*\s*(\d{3,4})\s*m?",
        r"(\d{3,4})\s*m?\s*(芝|ダ|障)",
    )
    for pattern in surface_distance_patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        if pattern.startswith(r"(芝"):
            surface, distance_text = match.group(1), match.group(2)
        else:
            distance_text, surface = match.group(1), match.group(2)
        distance = safe_int(distance_text)
        break

    going = ""
    for pattern in (
        r"馬場(?:状態)?\s*[:：]?\s*(良|稍重|重|不良)",
        r"(?:芝|ダート?|障害)\s*[:：]?\s*(良|稍重|重|不良)",
        r"\b(良|稍重|重|不良)\b",
    ):
        match = re.search(pattern, normalized)
        if match:
            going = match.group(1)
            break


    return RaceConditions(venue=venue, surface=surface, distance=distance, going=going)


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


def parse_time_seconds(text: str) -> float:
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})[.．](\d)(?!\d)", text)
    if match:
        return safe_int(match.group(1)) * 60 + safe_int(match.group(2)) + safe_int(match.group(3)) / 10
    return 9999.0


def format_time(seconds: float) -> str:
    if seconds >= 9999:
        return "なし"
    minutes = int(seconds // 60)
    remain = seconds - minutes * 60
    return f"{minutes}:{remain:04.1f}"


def extract_record_conditions(block_lines: List[str]) -> Tuple[str, str, int, str, str, float]:
    joined = " ".join(block_lines).replace("ダート", "ダ")
    first = normalize_text(block_lines[0]) if block_lines else ""

    date_match = re.match(r"^(20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?)", first)
    date = date_match.group(1) if date_match else ""

    venue = ""
    for candidate in VENUES:
        if candidate in joined:
            venue = candidate
            break

    surface = ""
    distance = 0
    for pattern in (
        r"(芝|ダ|障)\s*[右左直内外]*\s*(\d{3,4})\s*m?",
        r"(\d{3,4})\s*m?\s*(芝|ダ|障)",
    ):
        match = re.search(pattern, joined)
        if not match:
            continue
        if pattern.startswith(r"(芝"):
            surface, distance_text = match.group(1), match.group(2)
        else:
            distance_text, surface = match.group(1), match.group(2)
        distance = safe_int(distance_text)
        break

    going = ""
    for pattern in (
        r"馬場(?:状態)?\s*[:：]?\s*(良|稍重|重|不良)",
        r"(?:芝|ダ)\s*(良|稍重|重|不良)",
        r"(?<![一-龥])(良|稍重|重|不良)(?![一-龥])",
    ):
        match = re.search(pattern, joined)
        if match:
            going = match.group(1)
            break


    return date, venue, surface, distance, going, parse_time_seconds(joined)


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
        parsed_class = parse_class(line)
        if parsed_class != 3 or race_class == 3:
            race_class = parsed_class
        if not passing:
            passing = parse_passing(line)
        parsed_margin = parse_margin(line)
        if parsed_margin < 99.9:
            margin = parsed_margin

    date, venue, surface, distance, going, time_seconds = extract_record_conditions(block_lines)

    return RaceRecord(
        finish=finish,
        margin=margin,
        passing=passing,
        race_class=race_class,
        date=date,
        venue=venue,
        surface=surface,
        distance=distance,
        going=going,
        time_seconds=time_seconds,
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


def detect_time_index_mode(text: str) -> str:
    """見出しから中央・地方のタイム指数形式を自動判別する。"""
    normalized = normalize_text(text).replace(" ", "")
    if all(label in normalized for label in ("全体", "スタート", "追走", "上がり")):
        return "central"
    return "local"


def parse_central_time_row(row: List[str]) -> Optional[dict]:
    """中央競馬の1頭分を固定位置で解析する。"""
    if len(row) < 19:
        return None
    number = safe_int(row[1], 0)
    if not 1 <= number <= 18:
        return None
    values = [parse_index_value(value) for value in row[7:17]]
    if len(values) != 10:
        return None
    return {
        "number": number, "frame": safe_int(row[0], 0),
        "name": row[3], "jockey": row[6],
        "highest": 0, "overall": values[0], "start": values[1],
        "chase": values[2], "closing": values[3], "avg5": values[4],
        "distance": values[5], "course": values[6],
        "last3": values[7], "last2": values[8], "last1": values[9],
        "odds": safe_float(row[17], 0.0),
        "popularity": safe_int(row[18], 99),
    }


def parse_local_time_row(row: List[str]) -> Optional[dict]:
    """地方競馬の1頭分を固定位置で解析する。

    行構成:
    枠, 馬番, 印, 馬名, 性齢, 斤量, 騎手,
    最高, 5走平均, 距離, コース, 3走, 2走, 前走, 単勝オッズ, 人気
    """
    if len(row) < 16:
        return None
    number = safe_int(row[1], 0)
    if not 1 <= number <= 18:
        return None
    values = [parse_index_value(value) for value in row[7:14]]
    if len(values) != 7:
        return None
    return {
        "number": number, "frame": safe_int(row[0], 0),
        "name": row[3], "jockey": row[6],
        "highest": values[0], "overall": 0, "start": 0,
        "chase": 0, "closing": 0, "avg5": values[1],
        "distance": values[2], "course": values[3],
        "last3": values[4], "last2": values[5], "last1": values[6],
        "odds": safe_float(row[14], 0.0),
        "popularity": safe_int(row[15], 99),
    }


def parse_time_index(text: str, horses: Dict[int, Horse]) -> Tuple[Dict[int, Horse], str]:
    """中央・地方を自動判別してタイム指数を読み取る。"""
    for horse in horses.values():
        horse.timeindex = TimeIndex()

    mode = detect_time_index_mode(text)
    cells = time_index_cells(text)
    starts = find_time_row_starts(cells)

    for pos, start_index in enumerate(starts):
        end_index = starts[pos + 1] if pos + 1 < len(starts) else len(cells)
        row = cells[start_index:end_index]
        parsed = parse_central_time_row(row) if mode == "central" else parse_local_time_row(row)
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
            highest=parsed["highest"], overall=parsed["overall"],
            start=parsed["start"], chase=parsed["chase"],
            closing=parsed["closing"], avg5=parsed["avg5"],
            distance=parsed["distance"], course=parsed["course"],
            last3=parsed["last3"], last2=parsed["last2"], last1=parsed["last1"],
        )

    return horses, mode

def time_value(horse: Horse, column: str) -> int:
    return getattr(horse.timeindex, column)


def extract_top3(horses: Dict[int, Horse], time_columns: Tuple[str, ...]) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.top3_count = 0

    for column in time_columns:
        valid = [horse for horse in horses.values() if time_value(horse, column) > 0]
        if not valid:
            continue
        top3_values = set(sorted({time_value(horse, column) for horse in valid}, reverse=True)[:3])
        for horse in valid:
            if time_value(horse, column) in top3_values:
                horse.top3_count += 1
    return horses


def survival_check(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    # Ver6は全馬を順位付けする。人気上位3頭も必ず候補に残る。
    for horse in horses.values():
        has_time = any(value > 0 for value in vars(horse.timeindex).values())
        horse.alive = has_time or horse.popularity <= 3 or bool(horse.records)
    return horses


def calc_time_score(horses: Dict[int, Horse], time_columns: Tuple[str, ...]) -> Dict[int, Horse]:
    """タイム指数を0～50点へ正規化。各項目の相対値を平均する。"""
    column_max = {
        column: max((time_value(h, column) for h in horses.values()), default=0)
        for column in time_columns
    }

    raw_scores: Dict[int, float] = {}
    for horse in horses.values():
        ratios = [
            time_value(horse, column) / column_max[column]
            for column in time_columns
            if column_max[column] > 0 and time_value(horse, column) > 0
        ]
        coverage = len(ratios) / len(time_columns) if time_columns else 0
        raw_scores[horse.number] = (sum(ratios) / len(ratios) * coverage) if ratios else 0.0

    best_raw = max(raw_scores.values(), default=0.0)
    for horse in horses.values():
        horse.time_score = round(50 * raw_scores[horse.number] / best_raw) if best_raw > 0 else 0
        horse.time_score = max(0, min(50, horse.time_score))
    return horses


def record_match_level(record: RaceRecord, conditions: RaceConditions) -> int:
    if record.time_seconds >= 9999 or record.distance <= 0:
        return 0
    if not conditions.surface or not conditions.distance:
        return 0
    if record.surface != conditions.surface or record.distance != conditions.distance:
        return 0
    same_venue = bool(conditions.venue and record.venue == conditions.venue)
    same_going = bool(conditions.going and record.going == conditions.going)
    if same_venue and same_going:
        return 3
    if same_venue:
        return 2
    return 1


def select_best_records(horses: Dict[int, Horse], conditions: RaceConditions) -> Dict[int, Horse]:
    for horse in horses.values():
        candidates: List[Tuple[int, RaceRecord]] = []
        for record in horse.records:
            level = record_match_level(record, conditions)
            if level > 0:
                candidates.append((level, record))

        if not candidates:
            horse.best_record = BestRecord()
            continue

        highest_level = max(level for level, _ in candidates)
        best = min(
            (record for level, record in candidates if level == highest_level),
            key=lambda record: record.time_seconds,
        )
        horse.best_record = BestRecord(
            time_seconds=best.time_seconds,
            date=best.date,
            venue=best.venue,
            surface=best.surface,
            distance=best.distance,
            going=best.going,
            match_level=highest_level,
        )
    return horses


def calc_record_score(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    """採用持ち時計を0～50点化。一致レベルも反映する。"""
    valid = [h for h in horses.values() if h.best_record.time_seconds < 9999]
    if not valid:
        for horse in horses.values():
            horse.record_score = 0
        return horses

    times = [h.best_record.time_seconds for h in valid]
    fastest, slowest = min(times), max(times)
    level_factor = {3: 1.00, 2: 0.94, 1: 0.88}

    for horse in horses.values():
        if horse.best_record.time_seconds >= 9999:
            horse.record_score = 0
            continue
        if slowest == fastest:
            base = 50.0
        else:
            # 最速50点、最遅25点。極端なタイム差で0点化しない。
            base = 50.0 - 25.0 * (horse.best_record.time_seconds - fastest) / (slowest - fastest)
        score = base * level_factor.get(horse.best_record.match_level, 0.0)
        horse.record_score = max(0, min(50, round(score)))
    return horses


def finish_scoring(horses: Dict[int, Horse], item_count: int) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.total_score = horse.time_score + horse.record_score
        horse.mark = ""

    ranking = sorted(
        horses.values(),
        key=lambda h: (
            h.total_score,
            h.record_score,
            h.time_score,
            h.best_record.match_level,
            -h.popularity,
            -h.number,
        ),
        reverse=True,
    )

    for index, horse in enumerate(ranking):
        horse.mark = MARKS[index] if index < len(MARKS) else "△"
        record_text = (
            f"{horse.best_record.venue}{horse.best_record.surface}{horse.best_record.distance} "
            f"{horse.best_record.going} {format_time(horse.best_record.time_seconds)}"
            if horse.best_record.time_seconds < 9999 else "該当持ち時計なし"
        )
        horse.reason = (
            f"指数TOP3 {horse.top3_count}/{item_count} / "
            f"持ち時計 {record_text} / 一致Lv.{horse.best_record.match_level}"
        )
    return horses


def validate_inputs(
    horses: Dict[int, Horse],
    time_columns: Tuple[str, ...],
    conditions: RaceConditions,
) -> List[str]:
    errors: List[str] = []
    if not horses:
        return ["出走表から馬を読み取れませんでした。"]
    if not any(any(getattr(h.timeindex, c) > 0 for c in time_columns) for h in horses.values()):
        errors.append("タイム指数を読み取れませんでした。")
    if sum(len(h.records) for h in horses.values()) == 0:
        errors.append("馬柱の近走データを読み取れませんでした。")
    if not conditions.surface or not conditions.distance:
        errors.append("出走表から芝・ダートと距離を読み取れませんでした。")
    return errors


def result_dataframe(horses: Dict[int, Horse]) -> pd.DataFrame:
    mark_order = {"◎": 0, "○": 1, "▲": 2, "★": 3, "△": 4}
    ranking = sorted(
        horses.values(),
        key=lambda h: (
            mark_order.get(h.mark, 99),
            -h.total_score,
            -h.record_score,
            -h.time_score,
            h.number,
        ),
    )
    return pd.DataFrame([
        {
            "印": h.mark,
            "馬番": h.number,
            "馬名": h.name,
            "人気": "-" if h.popularity == 99 else h.popularity,
            "タイム指数50": h.time_score,
            "持ち時計50": h.record_score,
            "総合100": h.total_score,
            "採用タイム": format_time(h.best_record.time_seconds),
            "採用条件": (
                f"{h.best_record.venue} {h.best_record.surface}{h.best_record.distance} {h.best_record.going}"
                if h.best_record.time_seconds < 9999 else "なし"
            ),
            "一致レベル": h.best_record.match_level,
            "採用日": h.best_record.date or "-",
            "評価": h.reason,
        }
        for h in ranking
    ])


def clear_inputs() -> None:
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""


st.title("🐎 競馬AI Ver6 中央・地方対応版")
st.caption("中央・地方を自動判別｜タイム指数50点＋同条件ベストタイム50点｜全馬順位")


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
    race_conditions = parse_race_conditions(racecard_text)
    horses = parse_racecard(racecard_text)
    horses = parse_past_performances(past_text, horses)
    horses, time_mode = parse_time_index(timeindex_text, horses)
    time_columns = CENTRAL_TIME_COLUMNS if time_mode == "central" else LOCAL_TIME_COLUMNS

    parsed_horses = len(horses)
    parsed_records = sum(len(h.records) for h in horses.values())
    parsed_record_horses = sum(1 for h in horses.values() if h.records)

    with st.expander("読み取り確認", expanded=False):
        st.write(f"判定形式：{'中央競馬' if time_mode == 'central' else '地方競馬'}")
        st.write(f"対象条件：{race_conditions.venue or '不明'} {race_conditions.surface or '不明'}{race_conditions.distance or '不明'} {race_conditions.going or '不明'}")
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
        diagnostic_rows = []
        for h in sorted(horses.values(), key=lambda x: x.number):
            row = {"馬番": h.number, "馬名": h.name}
            if time_mode == "central":
                row.update({
                    "全体": h.timeindex.overall, "スタート": h.timeindex.start,
                    "追走": h.timeindex.chase, "上がり": h.timeindex.closing,
                    "5走平均": h.timeindex.avg5,
                })
            else:
                row.update({
                    "最高": h.timeindex.highest, "5走平均": h.timeindex.avg5,
                    "距離": h.timeindex.distance, "コース": h.timeindex.course,
                    "3走": h.timeindex.last3, "2走": h.timeindex.last2,
                    "前走": h.timeindex.last1,
                })
            diagnostic_rows.append(row)
        st.dataframe(pd.DataFrame(diagnostic_rows), use_container_width=True, hide_index=True)

    errors = validate_inputs(horses, time_columns, race_conditions)
    if errors:
        for error in errors:
            st.error(error)
        st.stop()

    horses = extract_top3(horses, time_columns)
    horses = survival_check(horses)
    horses = calc_time_score(horses, time_columns)
    horses = select_best_records(horses, race_conditions)
    horses = calc_record_score(horses)
    horses = finish_scoring(horses, len(time_columns))

    st.divider()
    st.subheader("予想結果")
    result = result_dataframe(horses)
    if result.empty:
        st.warning("生存馬がいません。タイム指数の貼り付け内容を確認してください。")
    else:
        st.dataframe(result, use_container_width=True, hide_index=True)

    with st.expander("全馬の採点詳細"):
        detail_rows = []
        for h in sorted(horses.values(), key=lambda x: (-x.total_score, x.number)):
            detail_rows.append({
                "馬番": h.number,
                "馬名": h.name,
                "タイム指数50": h.time_score,
                "持ち時計50": h.record_score,
                "総合100": h.total_score,
                "採用タイム": format_time(h.best_record.time_seconds),
                "競馬場": h.best_record.venue or "-",
                "芝ダ": h.best_record.surface or "-",
                "距離": h.best_record.distance or "-",
                "馬場": h.best_record.going or "-",
                "一致Lv": h.best_record.match_level,
                "採用日": h.best_record.date or "-",
            })
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)
