import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# =========================================================
# Streamlit
# =========================================================

st.set_page_config(
    page_title="競馬AI Next",
    page_icon="🐎",
    layout="wide",
)


# =========================================================
# Config
# =========================================================

MARKS = ("◎", "○", "▲", "△", "☆", "注", "穴")

VENUES = (
    "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
    "門別", "盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋",
    "園田", "姫路", "高知", "佐賀", "帯広",
)

CLASS_SCORES = {
    "G1": 100, "GI": 100,
    "G2": 92, "GII": 92,
    "G3": 86, "GIII": 86,
    "L": 80, "リステッド": 80,
    "OP": 78, "オープン": 78,
    "A1": 84, "A2": 80,
    "B1": 76, "B2": 72, "B3": 68,
    "C1": 64, "C2": 58, "C3": 52,
    "3勝": 74, "2勝": 66, "1勝": 58,
    "未勝利": 45, "新馬": 40,
}

WEIGHTS = {
    # 検証1件目を反映した暫定配分。数レース蓄積後に再調整する。
    "recent_form": 0.28,
    "race_level": 0.28,
    "suitability": 0.16,
    "running_style": 0.08,
    "closing_power": 0.08,
    "time_index": 0.12,
}


# =========================================================
# Models
# =========================================================

@dataclass
class RaceConditions:
    venue: str = ""
    surface: str = ""
    distance: int = 0
    going: str = ""


@dataclass
class RaceRecord:
    date: str = ""
    venue: str = ""
    surface: str = ""
    distance: int = 0
    going: str = ""
    race_class: str = ""
    finish: int = 99
    finish_known: bool = False
    margin: Optional[float] = None
    passing: str = ""
    last3f: float = 0.0


@dataclass
class TimeIndex:
    # Noneは「データなし」、0は実際の指数0として区別する。
    highest: Optional[int] = None
    overall: Optional[int] = None
    start: Optional[int] = None
    chase: Optional[int] = None
    closing: Optional[int] = None
    avg5: Optional[int] = None
    distance: Optional[int] = None
    course: Optional[int] = None
    last3: Optional[int] = None
    last2: Optional[int] = None
    last1: Optional[int] = None


@dataclass
class ScoreDetail:
    recent_form: float = 0.0
    race_level: float = 0.0
    suitability: float = 0.0
    running_style: float = 0.0
    closing_power: float = 0.0
    time_index: float = 0.0
    total: float = 0.0
    ability_index: int = 0
    ability_rank: int = 0


@dataclass
class Horse:
    number: int
    name: str = ""
    frame: int = 0
    jockey: str = ""
    odds: float = 0.0
    popularity: int = 99
    sex_age: str = ""
    records: List[RaceRecord] = field(default_factory=list)
    time_index: TimeIndex = field(default_factory=TimeIndex)
    running_style: str = ""
    style_hint: str = ""
    layoff_weeks: int = 0
    front_competitors: int = 0
    score: ScoreDetail = field(default_factory=ScoreDetail)
    mark: str = ""
    comment: str = ""


# =========================================================
# Common helpers
# =========================================================

def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\t", " ")
    return re.sub(r"[ ]{2,}", " ", text).strip()


def normalize_lines(text: str) -> List[str]:
    return [v for line in text.splitlines() if (v := normalize_text(line))]


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def average(values: List[float], default: float = 0.0) -> float:
    return statistics.mean(values) if values else default


# =========================================================
# Race conditions parser
# =========================================================

def parse_conditions(text: str) -> RaceConditions:
    normalized = normalize_text(text).replace("ダート", "ダ")

    venue = next((v for v in VENUES if v in normalized), "")

    surface = ""
    distance = 0

    for pattern in (
        r"(芝|ダ|障)\s*[右左直内外]*\s*(\d{3,4})\s*m?",
        r"(\d{3,4})\s*m?\s*(芝|ダ|障)",
    ):
        match = re.search(pattern, normalized)
        if not match:
            continue

        if pattern.startswith(r"(芝"):
            surface = match.group(1)
            distance = safe_int(match.group(2))
        else:
            distance = safe_int(match.group(1))
            surface = match.group(2)
        break

    going = ""
    match = re.search(
        r"(?:馬場(?:状態)?\s*[:：]?\s*)?(良|稍重|重|不良)",
        normalized,
    )
    if match:
        going = match.group(1)

    return RaceConditions(
        venue=venue,
        surface=surface,
        distance=distance,
        going=going,
    )


# =========================================================
# Racecard parser
# =========================================================

def parse_horse_header(line: str) -> Optional[Tuple[int, str]]:
    if re.search(r"20\d{2}[./年]\d{1,2}", line):
        return None

    for pattern in (
        r"^\s*(\d{1,2})\s+([^\s]+)",
        r"^\s*(\d{1,2})番\s*([^\s]+)",
    ):
        match = re.match(pattern, line)
        if not match:
            continue

        number = safe_int(match.group(1))
        name = re.sub(r"[牡牝セ騙]\d+$", "", match.group(2)).strip()

        if not 1 <= number <= 18:
            continue

        if any(word in name for word in ("人気", "指数", "着", "枠", "斤量", "タイム")):
            continue

        if name:
            return number, name

    return None


def parse_racecard(text: str) -> Dict[int, Horse]:
    horses: Dict[int, Horse] = {}
    current: Optional[Horse] = None

    for line in normalize_lines(text):
        header = parse_horse_header(line)
        if header:
            number, name = header
            current = horses.setdefault(number, Horse(number=number, name=name))
            current.name = name

        if current is None:
            continue

        pop = re.search(r"(\d+)\s*人気", line)
        if pop:
            current.popularity = safe_int(pop.group(1), 99)

        odds = re.search(
            r"(?:単勝|オッズ)\s*[:：]?\s*(\d+(?:\.\d+)?)",
            line,
        )
        if odds:
            current.odds = safe_float(odds.group(1))

        frame = re.search(r"(?:枠|枠番)\s*[:：]?\s*(\d)", line)
        if frame:
            current.frame = safe_int(frame.group(1))

        jockey = re.search(r"騎手\s*[:：]?\s*([^\d/|]+)", line)
        if jockey:
            current.jockey = normalize_text(jockey.group(1))

    return horses


# =========================================================
# Past performances parser
# =========================================================

def contains_date(line: str) -> bool:
    return bool(
        re.match(
            r"^20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?",
            line,
        )
    )


def parse_finish(lines: List[str]) -> Tuple[int, bool]:
    """明示された着順だけを読む。日付行末の数字（レース番号）は着順にしない。"""
    for line in lines:
        if contains_date(line):
            continue

        match = re.search(r"(?:着順\s*[:：]?\s*)?(\d{1,2})\s*着", line)
        if match:
            return safe_int(match.group(1), 99), True

    return 99, False


def parse_margin(line: str) -> Optional[float]:
    match = re.search(
        r"着差\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)",
        line,
    )
    if match:
        return safe_float(match.group(1), 0.0)

    # 通過順＋上がり＋馬体重の行にある増減値は着差ではない。
    if re.search(r"\d{1,2}(?:-\d{1,2}){1,3}", line):
        return None
    if re.search(r"\d{3}\([+-]?\d+\)\s*$", line):
        return None

    # 最終行の勝ち馬名（着差）を取得。負値は自身が勝ったことを表す。
    match = re.search(r"\(([+-]?\d+(?:\.\d+)?)\)\s*$", line)
    if match:
        return safe_float(match.group(1), 0.0)

    if "ハナ" in line:
        return 0.05
    if any(word in line for word in ("クビ", "アタマ")):
        return 0.1

    return None


def parse_passing(line: str) -> str:
    match = re.search(
        r"^\s*(\d{1,2}(?:-\d{1,2}){1,3})(?:\s|$)",
        line,
    )
    return match.group(1) if match else ""


def parse_last3f(line: str) -> float:
    values = re.findall(r"\((\d{2}\.\d)\)", line)
    if not values:
        return 0.0

    plausible = [
        safe_float(value)
        for value in values
        if 30.0 <= safe_float(value) <= 50.0
    ]
    return plausible[-1] if plausible else 0.0


def parse_record_conditions(lines: List[str]):
    joined = " ".join(lines).replace("ダート", "ダ")

    date_match = re.match(
        r"^(20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?)",
        lines[0],
    )
    date = date_match.group(1) if date_match else ""

    venue = next((v for v in VENUES if v in joined), "")

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
            surface = match.group(1)
            distance = safe_int(match.group(2))
        else:
            distance = safe_int(match.group(1))
            surface = match.group(2)
        break

    going = ""
    match = re.search(r"(良|稍重|重|不良)", joined)
    if match:
        going = match.group(1)

    race_class = ""
    for pattern in (
        r"\b(GI|GII|GIII|G1|G2|G3)\b",
        r"(A1|A2|B1|B2|B3|C1|C2|C3)",
        r"(3勝|2勝|1勝|未勝利|新馬|OP|オープン|リステッド)",
    ):
        match = re.search(pattern, joined, re.I)
        if match:
            race_class = match.group(1).upper()
            break

    return date, venue, surface, distance, going, race_class


def record_from_block(lines: List[str]) -> Optional[RaceRecord]:
    if not lines:
        return None

    finish, finish_known = parse_finish(lines)
    margin: Optional[float] = None
    passing = ""
    last3f = 0.0

    # 着差は通常ブロック最終行にあるため後ろから探す。
    for line in reversed(lines[1:]):
        margin = parse_margin(line)
        if margin is not None:
            break

    for line in lines[1:]:
        if not passing:
            passing = parse_passing(line)

        if not last3f:
            last3f = parse_last3f(line)

    # 貼り付け形式に着順がない場合は、勝ち馬なら1着、その他は最終コーナー位置を弱い推定値にする。
    if not finish_known:
        if margin is not None and margin < 0:
            finish = 1
        elif passing:
            finish = safe_int(passing.split("-")[-1], 99)

    date, venue, surface, distance, going, race_class = parse_record_conditions(lines)

    return RaceRecord(
        date=date,
        venue=venue,
        surface=surface,
        distance=distance,
        going=going,
        race_class=race_class,
        finish=finish,
        finish_known=finish_known,
        margin=margin,
        passing=passing,
        last3f=last3f,
    )


def parse_past_performances(
    text: str,
    horses: Dict[int, Horse],
) -> Dict[int, Horse]:
    for horse in horses.values():
        horse.records.clear()

    lines = normalize_lines(text)
    current: Optional[Horse] = None
    block: List[str] = []

    def flush():
        nonlocal block

        if current is not None and block and len(current.records) < 5:
            record = record_from_block(block)
            if record:
                current.records.append(record)

        block = []

    for line in lines:
        # netkeiba形式: 枠番 馬番
        match = re.fullmatch(r"([1-8])\s+([1-9]|1[0-8])", line)
        if match:
            flush()
            number = safe_int(match.group(2))
            current = horses.setdefault(
                number,
                Horse(number=number, name=f"{number}番"),
            )
            continue

        # 別形式: 6番 馬名
        match = re.match(r"^(\d{1,2})番(?:\s+([^\s]+))?", line)
        if match and 1 <= safe_int(match.group(1)) <= 18:
            flush()
            number = safe_int(match.group(1))
            current = horses.setdefault(
                number,
                Horse(
                    number=number,
                    name=match.group(2) or f"{number}番",
                ),
            )
            continue

        # 馬名で紐づけ
        if current is None:
            for horse in horses.values():
                if horse.name and horse.name in line:
                    current = horse
                    break

        if current is None:
            continue

        # 馬柱ヘッダーの「逃中3週」「追中16週」などを取得する。
        style_match = re.search(r"(逃|先|差|追)中(\d+)週", line)
        if style_match and not block:
            current.style_hint = {
                "逃": "逃げ",
                "先": "先行",
                "差": "差し",
                "追": "追込",
            }[style_match.group(1)]
            current.layoff_weeks = safe_int(style_match.group(2), 0)

        if contains_date(line):
            flush()
            block = [line]
        elif block:
            block.append(line)

    flush()
    return horses


# =========================================================
# Time index parser
# =========================================================

def time_cells(text: str) -> List[str]:
    text = (
        text
        .replace("\u3000", " ")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\t", "\n")
    )

    return [
        normalize_text(value)
        for value in text.splitlines()
        if normalize_text(value)
    ]


def index_value(value: str) -> Optional[int]:
    value = normalize_text(value).replace("＊", "*").rstrip("*")

    if value in {"未", "-", "--", "―", "－", "なし"}:
        return None

    return safe_int(value, 0) if re.fullmatch(r"-?\d+", value) else None


def parse_time_index(
    text: str,
    horses: Dict[int, Horse],
) -> Tuple[Dict[int, Horse], str]:
    mode = (
        "central"
        if all(word in text for word in ("全体", "スタート", "追走", "上がり"))
        else "local"
    )

    cells = time_cells(text)

    starts = []
    for i in range(len(cells) - 2):
        if (
            re.fullmatch(r"[1-8]", cells[i])
            and re.fullmatch(r"(?:[1-9]|1[0-8])", cells[i + 1])
            and cells[i + 2] in {"--", "－", "―"}
        ):
            starts.append(i)

    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(cells)
        row = cells[start:end]

        number = safe_int(row[1], 0)
        if not 1 <= number <= 18:
            continue

        horse = horses.setdefault(
            number,
            Horse(number=number, name=f"{number}番"),
        )

        if len(row) > 3:
            horse.name = row[3]

        if mode == "central" and len(row) >= 19:
            values = [index_value(v) for v in row[7:17]]

            horse.time_index = TimeIndex(
                overall=values[0],
                start=values[1],
                chase=values[2],
                closing=values[3],
                avg5=values[4],
                distance=values[5],
                course=values[6],
                last3=values[7],
                last2=values[8],
                last1=values[9],
            )

            horse.odds = safe_float(row[17], horse.odds)
            horse.popularity = safe_int(row[18], horse.popularity)

        elif mode == "local" and len(row) >= 16:
            values = [index_value(v) for v in row[7:14]]

            horse.time_index = TimeIndex(
                highest=values[0],
                avg5=values[1],
                distance=values[2],
                course=values[3],
                last3=values[4],
                last2=values[5],
                last1=values[6],
            )

            horse.odds = safe_float(row[14], horse.odds)
            horse.popularity = safe_int(row[15], horse.popularity)

    return horses, mode


# =========================================================
# Scoring
# =========================================================

def class_score(label: str) -> float:
    if not label:
        return 52.0

    return float(CLASS_SCORES.get(label.upper(), 52.0))


def venue_strength(venue: str) -> int:
    """競馬場の基礎レベル。過去の強い所属場から地方下級条件へ替わる馬を評価する。"""
    if venue in {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}:
        return 3
    if venue in {"浦和", "船橋", "大井", "川崎"}:
        return 2
    if venue:
        return 1
    return 0


def class_relief_bonus(horse: Horse, conditions: RaceConditions) -> float:
    if not horse.records or not conditions.venue:
        return 0.0

    current_strength = venue_strength(conditions.venue)
    prior_strength = average([venue_strength(r.venue) for r in horse.records if r.venue], current_strength)
    difference = prior_strength - current_strength

    if difference >= 1.5:
        return 14.0
    if difference >= 0.75:
        return 9.0
    return 0.0


def infer_running_style(horse: Horse) -> str:
    positions = []

    for record in horse.records:
        if not record.passing:
            continue

        try:
            parts = [int(value) for value in record.passing.split("-")]
            positions.append((parts[0], parts[-1]))
        except ValueError:
            continue

    if not positions:
        horse.running_style = horse.style_hint or "不明"
        return horse.running_style

    avg_first = average([p[0] for p in positions], 9.0)
    avg_last = average([p[1] for p in positions], 9.0)

    if avg_first <= 2.2:
        style = "逃げ"
    elif avg_first <= 5.0:
        style = "先行"
    elif avg_last <= 7.0:
        style = "差し"
    else:
        style = "追込"

    horse.running_style = style
    return style


def margin_performance_score(margin: Optional[float]) -> float:
    if margin is None:
        return 48.0
    if margin < 0:
        return 100.0
    if margin <= 0.2:
        return 92.0
    if margin <= 0.5:
        return 84.0
    if margin <= 1.0:
        return 72.0
    if margin <= 1.5:
        return 62.0
    if margin <= 2.0:
        return 52.0
    if margin <= 3.0:
        return 40.0
    if margin <= 4.0:
        return 28.0
    return 18.0


def position_content_score(record: RaceRecord) -> float:
    if not record.passing:
        return 50.0

    try:
        positions = [int(v) for v in record.passing.split("-")]
    except ValueError:
        return 50.0

    first = positions[0]
    last = positions[-1]
    score = 70 - max(0, last - 1) * 4
    score += clamp((first - last) * 4, -12, 16)
    return clamp(score, 20, 90)


def score_recent_form(horse: Horse) -> float:
    if not horse.records:
        return 35.0

    recency_weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    weighted_scores = []

    for index, record in enumerate(horse.records[:5]):
        margin_component = margin_performance_score(record.margin)
        position_component = position_content_score(record)

        if record.finish < 99:
            finish_component = clamp(105 - record.finish * 9, 10, 100)
            finish_weight = 0.28 if record.finish_known else 0.10
        else:
            finish_component = 48.0
            finish_weight = 0.0

        # 着順が明示されていない形式では、着差とレース内容を中心に評価する。
        margin_weight = 0.62 if not record.finish_known else 0.52
        position_weight = 1.0 - margin_weight - finish_weight
        row_score = (
            margin_component * margin_weight
            + finish_component * finish_weight
            + position_component * position_weight
        )
        weighted_scores.append(row_score * recency_weights[index])

    denominator = sum(recency_weights[:len(weighted_scores)])
    return clamp(sum(weighted_scores) / denominator if denominator else 35.0)


def score_race_level(horse: Horse, conditions: RaceConditions) -> float:
    if not horse.records:
        return 45.0

    weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    weighted_scores = []
    current_strength = venue_strength(conditions.venue)

    for index, record in enumerate(horse.records[:5]):
        level = class_score(record.race_class)
        prior_strength = venue_strength(record.venue)

        # 中央・南関から他地区へ移る場合は、過去に戦った相手レベルを加点する。
        if prior_strength > current_strength:
            level += (prior_strength - current_strength) * 10

        performance = margin_performance_score(record.margin)
        level += (performance - 50) * 0.14
        weighted_scores.append(clamp(level) * weights[index])

    return clamp(
        sum(weighted_scores) / sum(weights[:len(weighted_scores)])
    )


def score_suitability(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    if not horse.records:
        return 45.0

    scores = []

    for record in horse.records:
        score = 45.0

        if conditions.surface and record.surface:
            score += 18 if record.surface == conditions.surface else -15

        if conditions.distance and record.distance:
            distance_diff = abs(record.distance - conditions.distance)

            if distance_diff == 0:
                score += 22
            elif distance_diff <= 200:
                score += 14
            elif distance_diff <= 400:
                score += 6
            else:
                score -= 6

        if conditions.venue and record.venue:
            score += 8 if record.venue == conditions.venue else 0

        if conditions.going and record.going:
            score += 5 if record.going == conditions.going else 0

        # 着順が欠ける形式でも着差から条件実績を評価する。
        score += (margin_performance_score(record.margin) - 50) * 0.18
        scores.append(clamp(score))

    result = average(scores, 45.0)

    # 長期休養は軽く減点。ただし強い競馬場からの条件緩和があれば減点を抑える。
    relief = class_relief_bonus(horse, conditions)
    if horse.layoff_weeks >= 13:
        result -= 2 if relief >= 9 else 6
    elif horse.layoff_weeks >= 9:
        result -= 1 if relief >= 9 else 4
    elif horse.layoff_weeks >= 5:
        result -= 2

    return clamp(result)


def score_running_style(horse: Horse, front_count: int) -> float:
    style = infer_running_style(horse)

    base_score = {
        "逃げ": 76.0,
        "先行": 74.0,
        "差し": 68.0,
        "追込": 58.0,
        "不明": 55.0,
    }[style]

    # 逃げ・先行馬が多い時は同型競合を減点。単騎逃げだけを上げる。
    if style == "逃げ":
        if front_count <= 1:
            base_score += 7
        elif front_count == 2:
            base_score -= 6
        else:
            base_score -= 12
    elif style == "先行" and front_count >= 4:
        base_score -= 4

    if horse.records:
        weak_runs = sum(
            1 for record in horse.records[:5]
            if record.margin is not None and record.margin >= 3.0
        )
        base_score -= weak_runs * 2

    horse.front_competitors = front_count
    return clamp(base_score)


def score_closing_power(horse: Horse) -> float:
    values = [
        record.last3f
        for record in horse.records
        if 30.0 <= record.last3f <= 50.0
    ]

    if not values:
        if horse.time_index.closing is not None:
            return clamp(50 + horse.time_index.closing * 0.9)

        return 45.0

    avg_last3f = average(values)

    if avg_last3f <= 35.0:
        score = 92
    elif avg_last3f <= 36.0:
        score = 82
    elif avg_last3f <= 37.0:
        score = 72
    elif avg_last3f <= 38.5:
        score = 62
    elif avg_last3f <= 40.0:
        score = 52
    else:
        score = 42

    style = infer_running_style(horse)

    if style == "追込" and score >= 72:
        score += 12
    elif style == "差し" and score >= 72:
        score += 7

    return clamp(score)


def weighted_index_score(items: List[Tuple[Optional[int], float]]) -> float:
    available = [(value, weight) for value, weight in items if value is not None]
    if not available:
        return 40.0

    total_weight = sum(weight for _, weight in available)
    raw = sum(value * weight for value, weight in available) / total_weight

    # 実指数0を中立50点とし、マイナス指数もそのまま減点する固定基準。
    return clamp(50 + raw * 0.9)


def score_time_index(horse: Horse, mode: str) -> float:
    ti = horse.time_index

    if mode == "central":
        return weighted_index_score([
            (ti.overall, 0.12),
            (ti.start, 0.07),
            (ti.chase, 0.08),
            (ti.closing, 0.10),
            (ti.avg5, 0.13),
            (ti.distance, 0.10),
            (ti.course, 0.10),
            (ti.last3, 0.08),
            (ti.last2, 0.10),
            (ti.last1, 0.12),
        ])

    return weighted_index_score([
        (ti.highest, 0.08),
        (ti.avg5, 0.16),
        (ti.distance, 0.14),
        (ti.course, 0.14),
        (ti.last3, 0.12),
        (ti.last2, 0.16),
        (ti.last1, 0.20),
    ])


def assign_fixed_ability_indices(horses: Dict[int, Horse]) -> Dict[int, Horse]:
    """レース内順位ではなく、同じ総合点なら常に同じ指数になる固定基準。"""
    for horse in horses.values():
        horse.score.ability_index = round(clamp(35 + horse.score.total * 0.75, 35, 99))

    ranked = sorted(
        horses.values(),
        key=lambda h: (h.score.ability_index, h.score.total),
        reverse=True,
    )
    for rank, horse in enumerate(ranked, start=1):
        horse.score.ability_rank = rank

    return horses


def score_horses(
    horses: Dict[int, Horse],
    conditions: RaceConditions,
    mode: str,
) -> Dict[int, Horse]:
    # 先に全頭の脚質を確定し、逃げ・先行の競合数を出す。
    for horse in horses.values():
        infer_running_style(horse)

    front_count = sum(
        1 for horse in horses.values()
        if horse.running_style in ("逃げ", "先行")
    )

    for horse in horses.values():
        horse.score.recent_form = round(score_recent_form(horse), 1)
        horse.score.race_level = round(score_race_level(horse, conditions), 1)
        horse.score.suitability = round(score_suitability(horse, conditions), 1)
        horse.score.running_style = round(score_running_style(horse, front_count), 1)
        horse.score.closing_power = round(score_closing_power(horse), 1)
        horse.score.time_index = round(score_time_index(horse, mode), 1)

        total = (
            horse.score.recent_form * WEIGHTS["recent_form"]
            + horse.score.race_level * WEIGHTS["race_level"]
            + horse.score.suitability * WEIGHTS["suitability"]
            + horse.score.running_style * WEIGHTS["running_style"]
            + horse.score.closing_power * WEIGHTS["closing_power"]
            + horse.score.time_index * WEIGHTS["time_index"]
        )

        horse.score.total = round(clamp(total), 1)

    return assign_fixed_ability_indices(horses)


# =========================================================
# Selection
# =========================================================

def ranking_key(horse: Horse):
    return (
        horse.score.ability_index,
        horse.score.total,
        horse.score.recent_form,
        horse.score.race_level,
        horse.score.running_style,
        horse.score.closing_power,
        -horse.popularity,
        -horse.number,
    )


def build_comment(horse: Horse) -> str:
    reasons = []

    if horse.score.recent_form >= 75:
        reasons.append("近走内容が優秀")
    elif horse.score.recent_form <= 45:
        reasons.append("近走内容は低評価")

    if horse.score.race_level >= 70:
        reasons.append("相手レベルを高評価")

    if horse.score.suitability >= 72:
        reasons.append("今回条件への適性あり")

    if (
        horse.running_style in ("逃げ", "先行")
        and horse.score.running_style >= 75
    ):
        reasons.append(f"{horse.running_style}脚質を評価")

    if (
        horse.running_style in ("差し", "追込")
        and horse.score.closing_power >= 72
    ):
        reasons.append("上がり3Fの末脚を評価")

    if horse.score.time_index >= 70:
        reasons.append("タイム指数も上位")
    elif horse.score.time_index <= 38:
        reasons.append("近走タイム指数は低調")

    if horse.running_style == "逃げ" and horse.front_competitors >= 2:
        reasons.append("同型との先行争いに注意")

    if horse.popularity <= 3 and horse.score.ability_index < 75:
        reasons.append("上位人気のため印は残す")

    if not reasons:
        reasons.append("総合バランスで選出")

    return "・".join(reasons[:3])


def select_marks(horses: Dict[int, Horse]) -> List[Horse]:
    """人気1～3位は必ず◎○▲。人気4～8位から能力上位4頭へ残りの印。"""
    for horse in horses.values():
        horse.mark = ""
        horse.comment = ""

    selected: List[Horse] = []

    # 人気1～3位は必ず残し、この3頭の能力順で◎○▲を決定する。
    top_popular = [
        horse
        for horse in horses.values()
        if 1 <= horse.popularity <= 3
    ]
    top_popular.sort(key=ranking_key, reverse=True)

    # 人気の読み取り欠損時だけ、総合上位から不足分を補完する。
    if len(top_popular) < 3:
        already = {horse.number for horse in top_popular}
        fallback = [
            horse for horse in sorted(horses.values(), key=ranking_key, reverse=True)
            if horse.number not in already
        ]
        top_popular.extend(fallback[: 3 - len(top_popular)])

    for mark, horse in zip(("◎", "○", "▲"), top_popular[:3]):
        horse.mark = mark
        horse.comment = build_comment(horse)
        selected.append(horse)

    selected_numbers = {horse.number for horse in selected}

    # 人気4～8位の5頭から能力上位4頭を選ぶ。ここで1頭だけ消える。
    middle_popular = [
        horse
        for horse in horses.values()
        if 4 <= horse.popularity <= 8
        and horse.number not in selected_numbers
    ]
    middle_popular.sort(key=ranking_key, reverse=True)

    for mark, horse in zip(("△", "☆", "注", "穴"), middle_popular[:4]):
        horse.mark = mark
        horse.comment = build_comment(horse)
        selected.append(horse)

    # 人気取得が不完全でも印を7頭まで表示できるよう補完する。
    if len(selected) < 7:
        selected_numbers = {horse.number for horse in selected}
        fallback = [
            horse for horse in sorted(horses.values(), key=ranking_key, reverse=True)
            if horse.number not in selected_numbers
        ]
        remaining_marks = list(MARKS[len(selected):])
        for mark, horse in zip(remaining_marks, fallback[: 7 - len(selected)]):
            horse.mark = mark
            horse.comment = build_comment(horse)
            selected.append(horse)

    return selected


def axis_confidence(selected: List[Horse]) -> Tuple[str, str, float]:
    if not selected:
        return "★☆☆☆☆", "判定不能", 0.0

    axis = selected[0]
    second_index = selected[1].score.ability_index if len(selected) >= 2 else axis.score.ability_index
    gap = axis.score.ability_index - second_index

    if axis.score.ability_index >= 90 and gap >= 5:
        star_count = 5
    elif axis.score.ability_index >= 86 and gap >= 3:
        star_count = 4
    elif axis.score.ability_index >= 80 and gap >= 1:
        star_count = 3
    elif axis.score.ability_index >= 73:
        star_count = 2
    else:
        star_count = 1

    # 近走・相手・指数のうち弱点が重なる軸は信頼度を強制的に抑える。
    red_flags = sum([
        axis.score.recent_form < 55,
        axis.score.race_level < 55,
        axis.score.time_index < 45,
    ])
    if red_flags >= 2:
        star_count = min(star_count, 2)
    elif red_flags == 1:
        star_count = min(star_count, 3)

    if axis.running_style == "逃げ" and axis.front_competitors >= 2:
        star_count = min(star_count, 3)

    stars = "★" * star_count + "☆" * (5 - star_count)

    selected_indices = [horse.score.ability_index for horse in selected]
    spread = max(selected_indices) - min(selected_indices) if selected_indices else 0
    top_three = selected_indices[:3]
    top_spread = max(top_three) - min(top_three) if top_three else 0

    if star_count >= 4 and gap >= 4:
        difficulty = "本命寄り"
    elif top_spread <= 4:
        difficulty = "大混戦"
    elif spread <= 10:
        difficulty = "混戦"
    else:
        difficulty = "やや荒れ"

    return stars, difficulty, gap


# =========================================================
# Output
# =========================================================

def result_dataframe(selected: List[Horse]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "印": horse.mark,
                "馬番": horse.number,
                "馬名": horse.name,
                "人気": "-" if horse.popularity == 99 else horse.popularity,
                "オッズ": "-" if horse.odds <= 0 else horse.odds,
                "推定脚質": horse.running_style,
                "能力順位": horse.score.ability_rank,
                "能力指数": horse.score.ability_index,
                "近走内容": horse.score.recent_form,
                "レースレベル": horse.score.race_level,
                "条件適性": horse.score.suitability,
                "脚質評価": horse.score.running_style,
                "上がり3F": horse.score.closing_power,
                "タイム指数": horse.score.time_index,
                "評価": horse.comment,
            }
            for horse in selected
        ]
    )


def diagnostic_dataframe(horses: Dict[int, Horse]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "馬番": horse.number,
                "馬名": horse.name,
                "人気": horse.popularity,
                "近走数": len(horse.records),
                "推定脚質": horse.running_style,
                "内部総合": horse.score.total,
                "能力指数": horse.score.ability_index,
                "能力順位": horse.score.ability_rank,
                "休養週": horse.layoff_weeks,
                "先行候補数": horse.front_competitors,
            }
            for horse in sorted(
                horses.values(),
                key=lambda h: h.number,
            )
        ]
    )


# =========================================================
# UI
# =========================================================

def clear_inputs():
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""


st.title("🐎 競馬AI Next v0.3 検証修正版")
st.caption(
    "着順誤読修正・マイナス指数対応・相手レベル補正・同型競合・固定能力指数を実装"
)

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
    "③ タイム指数",
    height=320,
    placeholder="中央・地方どちらも対応",
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
    conditions = parse_conditions(racecard_text)
    horses = parse_racecard(racecard_text)
    horses = parse_past_performances(past_text, horses)
    horses, time_mode = parse_time_index(timeindex_text, horses)

    errors = []

    if not horses:
        errors.append("出走表から馬を読み取れませんでした。")

    if not any(horse.records for horse in horses.values()):
        errors.append("馬柱の近走データを読み取れませんでした。")

    if not any(
        any(value is not None for value in vars(horse.time_index).values())
        for horse in horses.values()
    ):
        errors.append("タイム指数を読み取れませんでした。")

    if errors:
        for error in errors:
            st.error(error)

        st.stop()

    horses = score_horses(
        horses,
        conditions,
        time_mode,
    )

    selected = select_marks(horses)
    confidence_stars, race_difficulty, axis_gap = axis_confidence(selected)

    st.divider()

    if selected:
        axis = selected[0]
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric(
                "◎ 軸馬",
                f"{axis.number}番 {axis.name}",
                f"能力指数 {axis.score.ability_index}",
            )
        with summary_col2:
            st.metric("軸信頼度", confidence_stars, f"2番手との差 {axis_gap:.0f}")
        with summary_col3:
            st.metric("レース難易度", race_difficulty)

    st.subheader("予想結果")

    st.dataframe(
        result_dataframe(selected),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("読み取り・採点確認"):
        st.write(
            f"判定形式："
            f"{'中央競馬' if time_mode == 'central' else '地方競馬'}"
        )

        st.write(
            f"対象条件："
            f"{conditions.venue or '不明'} "
            f"{conditions.surface or '不明'}"
            f"{conditions.distance or '不明'} "
            f"{conditions.going or '不明'}"
        )

        st.dataframe(
            diagnostic_dataframe(horses),
            use_container_width=True,
            hide_index=True,
        )
