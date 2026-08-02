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
    "JPN1": 100, "JPNI": 100,
    "JPN2": 92, "JPNII": 92,
    "JPN3": 86, "JPNIII": 86,
    "重賞": 82,
    "L": 80, "リステッド": 80,
    "OP": 78, "オープン": 78,
    "A1": 84, "A2": 80,
    "B1": 76, "B2": 72, "B3": 68,
    "C1": 64, "C2": 58, "C3": 52,
    "3勝": 74, "2勝": 66, "1勝": 58,
    "未勝利": 45, "新馬": 40,
}

TURF_SPRINT_SIRES = {
    "ロードカナロア",
    "ダイワメジャー",
    "ビッグアーサー",
    "キンシャサノキセキ",
    "ファインニードル",
    "ミッキーアイル",
    "アドマイヤムーン",
    "サクラバクシンオー",
    "モーリス",
    "カレンブラックヒル",
    "Dark Angel",
    "Invincible Spirit",
    "Kingman",
    "No Nay Never",
    "Siyouni",
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
    race_class: str = ""


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
    transition_bonus: float = 0.0
    age_adjustment: float = 0.0
    survival_score: float = 0.0
    danger_score: float = 0.0
    recent_peak_score: float = 0.0
    weight_bonus: float = 0.0
    high_class_win_bonus: float = 0.0
    young_condition_change_bonus: float = 0.0
    young_lightweight_current_class_bonus: float = 0.0
    young_layoff_growth_bonus: float = 0.0
    selection_score: float = 0.0
    avg5_score: float = 50.0
    avg5_rank: int = 0
    same_condition_score: float = 50.0
    same_condition_count: int = 0
    trend_score: float = 50.0
    stability_score: float = 0.0
    stable_axis_score: float = 0.0
    win_axis_score: float = 0.0
    base_axis_score: float = 0.0
    condition_boost: float = 0.0
    axis_index: float = 0.0
    axis_rank: int = 0
    recent_win_rate: float = 0.0
    recent_top2_rate: float = 0.0
    recent_top3_rate: float = 0.0
    recent_rate_count: int = 0
    same_condition_win_rate: float = 0.0
    same_condition_top3_rate: float = 0.0
    same_condition_rate_count: int = 0
    last2_form_score: float = 50.0
    class_adjusted_win_score: float = 50.0
    high_class_close_score: float = 50.0
    first_place_score: float = 0.0
    first_place_rank: int = 0
    first_place_tiebreak_promoted: bool = False
    upset_boundary_promoted: bool = False
    upset_boundary_demoted: bool = False
    upset_boundary_rule: str = ""
    in_money_score: float = 0.0
    in_money_rank: int = 0
    reserve_retention_score: float = 0.0
    reserve_protected: bool = False
    reserve_protection_reason: str = ""
    axis_banned: bool = False
    axis_ban_reason: str = ""
    axis_type: str = ""
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
    sire: str = ""
    records: List[RaceRecord] = field(default_factory=list)
    time_index: TimeIndex = field(default_factory=TimeIndex)
    running_style: str = ""
    style_hint: str = ""
    layoff_weeks: int = 0
    age: int = 0
    sex: str = ""
    carried_weight: float = 0.0
    weight_allowance: float = 0.0
    weight_change: int = 0
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

def parse_race_class_label(text: str) -> str:
    """
    レース名・条件文からクラス表記を安全に取得する。

    B14組をB1、C10組をC1として途中一致させない。
    単独の(A)(B)(C)、BC、B1B2混などにも対応する。
    """
    normalized = normalize_text(text)

    for pattern in (
        r"(JpnIII|JpnII|JpnI|Jpn3|Jpn2|Jpn1|GIII|GII|GI|G3|G2|G1)",
        r"(重賞)",
        r"(3勝|2勝|1勝|未勝利|新馬|OP|オープン|リステッド)",
    ):
        match = re.search(pattern, normalized, re.I)
        if match:
            label = match.group(1)
            return label.upper() if label != "重賞" else label

    # B1B2混、B2B3、A2B1などの混合条件。
    mixed = re.search(
        r"(?<![A-Z0-9])((?:A|B|C)\d{1,2}(?:A|B|C)\d{1,2})(?:混)?(?!\d)",
        normalized,
        re.I,
    )
    if mixed:
        return mixed.group(1).upper()

    # B14組、C10組など。組番号を丸ごと保持する。
    group = re.search(
        r"(?<![A-Z0-9])([ABC])(\d{1,2})組",
        normalized,
        re.I,
    )
    if group:
        return f"{group.group(1).upper()}{safe_int(group.group(2))}"

    # A1、B2、C3など。後ろに数字が続く場合は一致させない。
    exact = re.search(
        r"(?<![A-Z0-9])([ABC])(\d{1,2})(?!\d)",
        normalized,
        re.I,
    )
    if exact:
        return f"{exact.group(1).upper()}{safe_int(exact.group(2))}"

    # (BC)、BC級。
    if re.search(r"\(BC\)|BC級", normalized, re.I):
        return "BC"

    # (A)(B)(C)、A級・B級・C級。
    generic = re.search(r"\(([ABC])\)|([ABC])級", normalized, re.I)
    if generic:
        return (generic.group(1) or generic.group(2)).upper()

    return ""


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
        race_class=parse_race_class_label(normalized),
    )


def merge_conditions(
    explicit_text: str,
    racecard_text: str,
) -> RaceConditions:
    """
    任意のレース条件入力を優先し、不足している項目だけ出走表から補う。
    例: 「中京 ダ1400 良」
    """
    explicit = parse_conditions(explicit_text)
    fallback = parse_conditions(racecard_text)

    return RaceConditions(
        venue=explicit.venue or fallback.venue,
        surface=explicit.surface or fallback.surface,
        distance=explicit.distance or fallback.distance,
        going=explicit.going or fallback.going,
        race_class=explicit.race_class or fallback.race_class,
    )


def has_known_conditions(conditions: RaceConditions) -> bool:
    return any((
        conditions.venue,
        conditions.surface,
        conditions.distance,
        conditions.going,
        conditions.race_class,
    ))


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

        sex_age_match = re.search(r"(牡|牝|セ|騙)(\d{1,2})", line)
        if sex_age_match:
            current.sex = sex_age_match.group(1)
            current.age = safe_int(sex_age_match.group(2), current.age)
            current.sex_age = sex_age_match.group(0)

        # 出走表の「牝7 52.0」等から今回斤量を取得する。
        weight_match = re.search(
            r"(?:牡|牝|セ|騙)\d{1,2}\s+(\d{2}(?:\.\d)?)",
            line,
        )
        if weight_match:
            current.carried_weight = safe_float(weight_match.group(1), current.carried_weight)

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
    """
    netkeiba馬柱の日付行末にある数字を正式な着順として読む。

    例:
        2026.06.20 阪神5  -> 5着
        2026.05.23 東京1  -> 1着

    「中」「取」「除」「失」など数字ではない結果は着順不明として扱う。
    """
    if lines:
        date_line = normalize_text(lines[0])
        match = re.match(
            r"^20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?"
            r"\s+.+?(\d{1,2})$",
            date_line,
        )
        if match:
            finish = safe_int(match.group(1), 99)
            if 1 <= finish <= 99:
                return finish, True

    # 別形式で「5着」「着順:5」と明記される場合にも対応。
    for line in lines:
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

    race_class = parse_race_class_label(joined)

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

    # 着順不明時は通過順位を着順として代用しない。
    # 着差が負なら自身が勝ったことだけは確定できるため1着とする。
    if not finish_known and margin is not None and margin < 0:
        finish = 1
        finish_known = True

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
    expect_sire = False

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
            expect_sire = False
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
            expect_sire = False
            continue

        # 馬名で紐づけ
        if current is None:
            for horse in horses.values():
                if horse.name and horse.name in line:
                    current = horse
                    break

        if current is None:
            continue

        # netkeiba馬柱では「--」直後の行が父名。
        if not block and line in {"--", "－", "―"}:
            expect_sire = True
            continue

        if expect_sire and not block:
            current.sire = line
            expect_sire = False
            continue

        # 年齢と今回の馬体重増減を取得する。
        age_match = re.search(r"(牡|牝|セ|騙)(\d{1,2})", line)
        if age_match and not block:
            current.sex = age_match.group(1)
            current.age = safe_int(age_match.group(2), 0)
            current.sex_age = age_match.group(0)

        # 馬柱ヘッダーの独立した「52.0」「57.0」行を今回斤量として取得。
        if not block and re.fullmatch(r"\d{2}(?:\.\d)?", line):
            current.carried_weight = safe_float(line, current.carried_weight)

        weight_match = re.search(r"\d{3}kg\(([+-]?\d+)\)", line)
        if weight_match and not block:
            current.weight_change = safe_int(weight_match.group(1), 0)

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

def local_group_class_score(letter: str, group_number: int) -> float:
    """地方の組番号を、上位組ほど高く・下位組ほど低く評価する。"""
    letter = letter.upper()
    group_number = max(1, group_number)

    if letter == "A":
        if group_number == 1:
            return 84.0
        if group_number == 2:
            return 80.0
        return clamp(78.0 - (group_number - 3) * 1.5, 68.0, 78.0)

    if letter == "B":
        if group_number == 1:
            return 76.0
        if group_number == 2:
            return 72.0
        if group_number == 3:
            return 68.0
        return clamp(68.0 - (group_number - 3) * 1.2, 54.0, 68.0)

    if letter == "C":
        if group_number == 1:
            return 64.0
        if group_number == 2:
            return 58.0
        if group_number == 3:
            return 52.0
        return clamp(52.0 - (group_number - 3) * 1.0, 42.0, 52.0)

    return 52.0


def class_score(label: str) -> float:
    if not label:
        return 52.0

    upper = label.upper()
    if upper in CLASS_SCORES:
        return float(CLASS_SCORES[upper])

    generic_scores = {
        "A": 80.0,
        "B": 66.0,
        "C": 52.0,
        "BC": 59.0,
    }
    if upper in generic_scores:
        return generic_scores[upper]

    # B1B2、B2B3、A2B1などは構成クラスの平均。
    mixed_parts = re.findall(r"([ABC])(\d{1,2})", upper)
    if len(mixed_parts) >= 2:
        return average([
            local_group_class_score(letter, safe_int(number, 1))
            for letter, number in mixed_parts
        ], 52.0)

    single = re.fullmatch(r"([ABC])(\d{1,2})", upper)
    if single:
        return local_group_class_score(
            single.group(1),
            safe_int(single.group(2), 1),
        )

    return 52.0


def recent_high_class_win_bonus(horse: Horse) -> float:
    """
    直近の高格レース勝利を、軸指数ではなく印選定・生存判定だけで評価する。

    前走勝利:
      GI/JpnI       +8
      GII/JpnII     +7
      GIII/JpnIII   +6
      地方重賞      +5
      L/OP          +4

    2走前勝利は半分。最大10点に抑える。
    """
    if not horse.records:
        return 0.0

    base_points = {
        "GI": 8.0, "G1": 8.0,
        "JPNI": 8.0, "JPN1": 8.0,
        "GII": 7.0, "G2": 7.0,
        "JPNII": 7.0, "JPN2": 7.0,
        "GIII": 6.0, "G3": 6.0,
        "JPNIII": 6.0, "JPN3": 6.0,
        "重賞": 5.0,
        "L": 4.0, "リステッド": 4.0,
        "OP": 4.0, "オープン": 4.0,
    }

    bonus = 0.0
    for index, multiplier in ((0, 1.0), (1, 0.5)):
        if index >= len(horse.records):
            continue

        record = horse.records[index]
        if not record.finish_known or record.finish != 1:
            continue

        label = (record.race_class or "").upper()
        bonus += base_points.get(label, 0.0) * multiplier

    return round(min(bonus, 10.0), 1)


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
    """直近に強い競馬場で走っていた馬の相手弱化を拾う。平均だけで薄めない。"""
    if not horse.records or not conditions.venue:
        return 0.0

    current_strength = venue_strength(conditions.venue)
    recent_strengths = [
        venue_strength(record.venue)
        for record in horse.records[:5]
        if record.venue
    ]
    if not recent_strengths:
        return 0.0

    stronger = [value for value in recent_strengths if value > current_strength]
    max_difference = max(recent_strengths) - current_strength

    if max_difference >= 2:
        return 15.0
    if max_difference >= 1:
        if len(stronger) >= 3:
            return 12.0
        if len(stronger) >= 1:
            return 8.0
    return 0.0


def age_adjustment(horse: Horse) -> float:
    """同程度なら若い馬を少し上げるが、高齢だけで強く下げない。"""
    if horse.age <= 0:
        return 0.0
    if horse.age <= 4:
        return 2.5
    if horse.age == 5:
        return 1.0
    if horse.age >= 9:
        return -1.0
    if horse.age >= 8:
        return -0.5
    return 0.0


def is_turf_sprint_sire(sire: str) -> bool:
    if not sire:
        return False

    normalized = normalize_text(sire)
    return any(
        normalized.casefold() == candidate.casefold()
        for candidate in TURF_SPRINT_SIRES
    )


def record_forward_position(record: RaceRecord) -> bool:
    if not record.passing:
        return False

    try:
        positions = [
            int(value)
            for value in record.passing.split("-")
        ]
    except (TypeError, ValueError):
        return False

    return bool(positions) and (
        positions[0] <= 4
        or positions[-1] <= 3
    )


def calculate_young_condition_change_bonus(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """
    3歳馬が未勝利の短距離戦を先行して勝ち、
    1勝クラスでダートから芝短距離へ替わる場合の上昇余地を評価する。

    過去実績の少ない若馬を無条件で上げず、以下がそろう場合だけ加点。
      ・3歳
      ・今回1勝クラス
      ・今回芝1000～1400m
      ・前走が未勝利または新馬の短距離勝ち
      ・前走ダートから今回芝への条件替わり

    父が代表的な芝短距離型で、今回に近い芝短距離実績がまだない場合は
    「未知の適性」を小幅に追加評価する。
    """
    if horse.age != 3 or not horse.records:
        return 0.0

    current_class = (conditions.race_class or "").upper()
    if current_class != "1勝":
        return 0.0

    if (
        conditions.surface != "芝"
        or not 1000 <= conditions.distance <= 1400
    ):
        return 0.0

    latest = horse.records[0]
    latest_class = (latest.race_class or "").upper()

    if (
        latest_class not in {"未勝利", "新馬"}
        or not latest.finish_known
        or latest.finish != 1
        or latest.surface != "ダ"
        or not 1000 <= latest.distance <= 1400
    ):
        return 0.0

    bonus = 2.0
    bonus += 1.5  # ダート短距離→芝短距離

    distance_diff = abs(
        conditions.distance - latest.distance
    )
    if distance_diff <= 100:
        bonus += 1.0
    elif distance_diff <= 200:
        bonus += 0.6

    if record_forward_position(latest):
        bonus += 1.5

    if latest.margin is not None and latest.margin <= 0.3:
        bonus += 0.5

    prior_similar_turf = any(
        record.surface == "芝"
        and 1000 <= record.distance <= 1400
        and abs(record.distance - conditions.distance) <= 200
        for record in horse.records[1:5]
    )

    if (
        not prior_similar_turf
        and is_turf_sprint_sire(horse.sire)
    ):
        bonus += 1.5

    return round(clamp(bonus, 0.0, 8.0), 1)


def is_mixed_age_field(horses: Dict[int, Horse]) -> bool:
    active = [
        horse
        for horse in horses.values()
        if horse.popularity != 99
    ]
    return (
        any(horse.age == 3 for horse in active)
        and any(horse.age >= 4 for horse in active)
    )


def is_current_one_win_context(
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> bool:
    """
    レース条件に1勝と入力されていればそのまま採用する。

    クラス未入力でも、3歳と古馬の混合戦で、複数頭が直近3走以内に
    1勝クラスへ出走している場合は「古馬混合1勝クラス相当」と推定する。
    """
    current_class = (conditions.race_class or "").upper()
    if current_class:
        return current_class == "1勝"

    if not is_mixed_age_field(horses):
        return False

    active = [
        horse
        for horse in horses.values()
        if horse.popularity != 99
    ]
    if not active:
        return False

    recent_one_win_count = sum(
        any(
            (record.race_class or "").upper() == "1勝"
            for record in horse.records[:3]
        )
        for horse in active
    )

    required = max(3, int(len(active) * 0.35 + 0.999))
    return recent_one_win_count >= required


def calculate_young_lightweight_current_class_bonus(
    horse: Horse,
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> float:
    """
    古馬混合1勝クラスで、極端な軽斤量を与えられた3歳馬の選定救済。

    対象条件:
      ・3歳
      ・今回52kg以下
      ・3歳と古馬の混合戦
      ・今回が1勝クラス、または出走構成から1勝クラス相当と推定
      ・直近3走以内に今回と同じ馬場種別
      ・今回から200m以内
      ・1勝クラスで1.0秒差以内

    軸指数や1着期待には加えず、選定・生存・馬券内期待だけに反映する。
    """
    if horse.age != 3:
        return 0.0

    if horse.carried_weight <= 0 or horse.carried_weight > 52.0:
        return 0.0

    if not is_mixed_age_field(horses):
        return 0.0

    if not is_current_one_win_context(horses, conditions):
        return 0.0

    qualifying = []
    for record in horse.records[:3]:
        if (record.race_class or "").upper() != "1勝":
            continue

        if record.margin is None or record.margin > 1.0:
            continue

        if (
            conditions.surface
            and record.surface
            and record.surface != conditions.surface
        ):
            continue

        if (
            conditions.distance
            and record.distance
            and abs(record.distance - conditions.distance) > 200
        ):
            continue

        qualifying.append(record)

    if not qualifying:
        return 0.0

    # 1頭を救済するための固定4点。複数実績があっても過剰加点しない。
    return 4.0


def calculate_young_layoff_growth_bonus(
    horse: Horse,
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> float:
    """
    3歳馬の休養明け成長を、選定と相手評価だけで小幅救済する。

    対象条件:
      ・3歳
      ・古馬との混合戦
      ・今回が1勝クラス、または出走構成から1勝クラス相当と推定
      ・休養13週以上
      ・今回の馬体重が前走比+8kg以上
      ・直近3走以内に、今回と同じ馬場種別かつ距離差200m以内の
        1勝クラスで1.0秒差以内

    軸指数・1着期待・能力総合には加えず、
    成長余地を理由に相手候補から落としすぎないための救済に限定する。
    """
    if horse.age != 3:
        return 0.0

    if not is_mixed_age_field(horses):
        return 0.0

    if not is_current_one_win_context(horses, conditions):
        return 0.0

    if horse.layoff_weeks < 13:
        return 0.0

    if horse.weight_change < 8:
        return 0.0

    qualifying = []
    for record in horse.records[:3]:
        if (record.race_class or "").upper() != "1勝":
            continue

        if record.margin is None or record.margin > 1.0:
            continue

        if (
            conditions.surface
            and record.surface
            and record.surface != conditions.surface
        ):
            continue

        if (
            conditions.distance
            and record.distance
            and abs(record.distance - conditions.distance) > 200
        ):
            continue

        qualifying.append(record)

    if not qualifying:
        return 0.0

    return 4.0


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

    # 開催場が不明な場合は、競馬場格差による相手弱化加点を使わない。
    # 「不明＝最弱の競馬場」と誤認して中央実績を過大評価するのを防ぐ。
    current_strength = (
        venue_strength(conditions.venue)
        if conditions.venue
        else None
    )

    for index, record in enumerate(horse.records[:5]):
        level = class_score(record.race_class)

        if current_strength is not None and record.venue:
            prior_strength = venue_strength(record.venue)

            # 中央・南関から他地区へ移る場合のみ、過去の相手レベルを加点する。
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
    """
    今回条件への純粋な適合度。

    着順・着差は同条件近走で評価するため、ここでは重複させない。
    対象レース数が少ない場合は50点へ縮める。
    """
    if not horse.records:
        return 45.0

    if not has_known_conditions(conditions):
        return 50.0

    scores: List[float] = []

    for record in horse.records[:5]:
        score = 50.0
        compared = 0

        if conditions.surface and record.surface:
            compared += 1
            score += 10 if record.surface == conditions.surface else -12

        if conditions.distance and record.distance:
            compared += 1
            distance_diff = abs(record.distance - conditions.distance)
            if distance_diff == 0:
                score += 14
            elif distance_diff <= 200:
                score += 10
            elif distance_diff <= 400:
                score += 4
            else:
                score -= 5

        if conditions.venue and record.venue:
            compared += 1
            score += 4 if record.venue == conditions.venue else 0

        if conditions.going and record.going:
            compared += 1
            score += 2 if record.going == conditions.going else 0

        if compared:
            scores.append(clamp(score))

    if not scores:
        return 50.0

    raw = average(scores, 50.0)

    # 1走だけなら35％、2走なら55％、3走なら75％、
    # 4走以上で100％まで信頼する。
    reliability = min(1.0, 0.15 + len(scores) * 0.20)
    return clamp(50.0 + (raw - 50.0) * reliability)


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


def distance_band(distance: int) -> str:
    if distance <= 0:
        return "unknown"
    if distance <= 1000:
        return "sprint_1000"
    if distance <= 1300:
        return "sprint_1300"
    if distance <= 1500:
        return "middle_1500"
    if distance <= 1800:
        return "middle_1800"
    return "long"


def passing_gain(record: RaceRecord) -> float:
    if not record.passing:
        return 0.0
    try:
        positions = [int(value) for value in record.passing.split("-")]
    except ValueError:
        return 0.0
    return clamp((positions[0] - positions[-1]) * 2.0, -6.0, 8.0)


def score_closing_power_all(horses: Dict[int, Horse]) -> Dict[int, float]:
    """地方の遅い上がりも、距離帯ごとのレース内相対評価で差を出す。"""
    group_values: Dict[Tuple[str, str], List[float]] = {}
    surface_values: Dict[str, List[float]] = {}
    all_values: List[float] = []

    for horse in horses.values():
        for record in horse.records[:5]:
            if not 30.0 <= record.last3f <= 50.0:
                continue
            key = (record.surface or "unknown", distance_band(record.distance))
            group_values.setdefault(key, []).append(record.last3f)
            surface_values.setdefault(record.surface or "unknown", []).append(record.last3f)
            all_values.append(record.last3f)

    if not all_values:
        return {
            horse.number: (
                time_index_to_score(horse.time_index.closing)
                if horse.time_index.closing is not None
                else 50.0
            )
            for horse in horses.values()
        }

    global_median = statistics.median(all_values)
    global_scale = max(statistics.pstdev(all_values) if len(all_values) >= 2 else 1.0, 0.8)
    recency_weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    results: Dict[int, float] = {}

    for horse in horses.values():
        weighted_scores: List[float] = []
        used_weights: List[float] = []

        for index, record in enumerate(horse.records[:5]):
            if not 30.0 <= record.last3f <= 50.0:
                continue

            key = (record.surface or "unknown", distance_band(record.distance))
            peers = group_values.get(key, [])
            if len(peers) < 4:
                peers = surface_values.get(record.surface or "unknown", [])

            if len(peers) >= 4:
                median_value = statistics.median(peers)
                scale = max(statistics.pstdev(peers) if len(peers) >= 2 else 1.0, 0.7)
            else:
                median_value = global_median
                scale = global_scale

            # 同距離帯の中央値より速いほど加点する。
            score = 60.0 + (median_value - record.last3f) / scale * 10.0
            score += passing_gain(record)

            # 前で運んだ馬は、上がりだけで不当に下げすぎない。
            if horse.running_style in ("逃げ", "先行") and record.passing:
                try:
                    last_position = int(record.passing.split("-")[-1])
                    if last_position <= 2:
                        score += 3.0
                except ValueError:
                    pass

            weight = recency_weights[index]
            weighted_scores.append(clamp(score, 20, 95) * weight)
            used_weights.append(weight)

        if used_weights:
            results[horse.number] = clamp(sum(weighted_scores) / sum(used_weights))
        elif horse.time_index.closing is not None:
            results[horse.number] = time_index_to_score(horse.time_index.closing)
        else:
            results[horse.number] = 50.0

    return results


def time_index_to_score(value: Optional[int]) -> float:
    """実指数を固定基準へ変換する。高指数帯でも点差が残るよう緩やかに圧縮する。"""
    if value is None:
        return 50.0

    points = [
        (-40, 5),
        (-30, 12),
        (-20, 22),
        (-10, 32),
        (0, 42),
        (10, 52),
        (20, 60),
        (30, 67),
        (40, 73),
        (50, 79),
        (60, 84),
        (70, 89),
        (80, 93),
        (100, 98),
    ]

    if value <= points[0][0]:
        return float(points[0][1])
    if value >= points[-1][0]:
        return float(points[-1][1])

    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 <= value <= x2:
            ratio = (value - x1) / (x2 - x1)
            return y1 + (y2 - y1) * ratio

    return 50.0


def weighted_index_score(items: List[Tuple[Optional[int], float]]) -> float:
    available = [(value, weight) for value, weight in items if value is not None]
    if not available:
        return 50.0

    total_weight = sum(weight for _, weight in available)
    return clamp(
        sum(time_index_to_score(value) * weight for value, weight in available)
        / total_weight
    )


def blend_field_scores(
    raw_scores: Dict[int, float],
    relative_low: float = 45.0,
    relative_high: float = 90.0,
    absolute_weight: float = 0.65,
) -> Dict[int, float]:
    """固定基準とレース内相対順位を混ぜ、上限張り付きと同点化を抑える。"""
    if not raw_scores:
        return {}

    items = sorted(raw_scores.items(), key=lambda item: item[1])
    count = len(items)
    relative_scores: Dict[int, float] = {}

    index = 0
    while index < count:
        end = index
        current_value = items[index][1]
        while end + 1 < count and abs(items[end + 1][1] - current_value) < 1e-9:
            end += 1

        if count == 1:
            percentile = 0.5
        else:
            average_position = (index + end) / 2
            percentile = average_position / (count - 1)

        relative_value = relative_low + (relative_high - relative_low) * percentile
        for position in range(index, end + 1):
            relative_scores[items[position][0]] = relative_value
        index = end + 1

    relative_weight = 1.0 - absolute_weight
    return {
        number: round(clamp(
            clamp(raw_score) * absolute_weight
            + relative_scores[number] * relative_weight,
            20,
            95,
        ), 1)
        for number, raw_score in raw_scores.items()
    }


def blend_survival_scores(raw_scores: Dict[int, float]) -> Dict[int, float]:
    """生存指数専用。過剰加点を圧縮しつつ、レース内で45～90程度へ分散させる。"""
    if not raw_scores:
        return {}

    compressed = {
        number: clamp(50.0 + (raw_score - 50.0) * 0.55, 20, 95)
        for number, raw_score in raw_scores.items()
    }
    return blend_field_scores(
        compressed,
        relative_low=42.0,
        relative_high=90.0,
        absolute_weight=0.58,
    )


def score_time_index(horse: Horse, mode: str) -> float:
    ti = horse.time_index

    if mode == "central":
        return weighted_index_score([
            (ti.overall, 0.08),
            (ti.start, 0.05),
            (ti.chase, 0.06),
            (ti.closing, 0.08),
            (ti.avg5, 0.10),
            (ti.distance, 0.08),
            (ti.course, 0.07),
            (ti.last3, 0.14),
            (ti.last2, 0.16),
            (ti.last1, 0.18),
        ])

    # 地方7項目は5走平均を能力の土台として最重視。
    # 前走で現在の状態、距離・2走前・コースで再現性を補う。
    return weighted_index_score([
        (ti.highest, 0.05),
        (ti.avg5, 0.25),
        (ti.distance, 0.15),
        (ti.course, 0.10),
        (ti.last3, 0.05),
        (ti.last2, 0.15),
        (ti.last1, 0.25),
    ])


def recent_time_values(horse: Horse) -> List[int]:
    return [
        value for value in (
            horse.time_index.last3,
            horse.time_index.last2,
            horse.time_index.last1,
        )
        if value is not None
    ]


def recent_peak_score(horse: Horse) -> float:
    """古い最高値ではなく、直近3走内の一発指数だけを補助評価する。"""
    values = recent_time_values(horse)
    if not values:
        return 50.0
    return clamp(time_index_to_score(max(values)))


def record_performance_score(record: RaceRecord) -> float:
    margin_score = margin_performance_score(record.margin)
    position_score = position_content_score(record)

    if record.finish_known and record.finish < 99:
        finish_score = clamp(105 - record.finish * 9, 10, 100)
        return clamp(
            margin_score * 0.50
            + finish_score * 0.35
            + position_score * 0.15
        )

    return clamp(margin_score * 0.75 + position_score * 0.25)


def score_same_condition_recent(
    horse: Horse,
    conditions: RaceConditions,
) -> Tuple[float, int]:
    """
    今回に近い条件での実戦内容を評価する。

    ・上位クラスから今回クラスへ下がる場合は減点しない
    ・相手緩和は最大5点の小幅加点
    ・1～2走だけの高評価は50点へ強く縮める
    """
    if not horse.records or not has_known_conditions(conditions):
        return 50.0, 0

    recency_weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    weighted_scores: List[float] = []
    used_weights: List[float] = []
    used_count = 0

    current_class_score = (
        class_score(conditions.race_class)
        if conditions.race_class
        else None
    )

    for index, record in enumerate(horse.records[:5]):
        similarity = 0.0
        possible = 0.0
        class_relief_bonus = 0.0

        if conditions.surface:
            possible += 0.25
            if record.surface == conditions.surface:
                similarity += 0.25
            elif record.surface:
                similarity -= 0.20

        if conditions.distance:
            possible += 0.35
            if record.distance:
                diff = abs(record.distance - conditions.distance)
                if diff == 0:
                    similarity += 0.35
                elif diff <= 200:
                    similarity += 0.27
                elif diff <= 400:
                    similarity += 0.14

        if conditions.venue:
            possible += 0.20
            if record.venue == conditions.venue:
                similarity += 0.20
            elif record.venue:
                similarity += 0.06

        if conditions.going:
            possible += 0.05
            if record.going == conditions.going:
                similarity += 0.05

        if current_class_score is not None:
            possible += 0.15
            if record.race_class:
                prior_class_score = class_score(record.race_class)
                class_diff = prior_class_score - current_class_score

                # 過去の方が上位クラスなら、クラス違いで減点しない。
                if class_diff >= 0:
                    similarity += 0.15
                    class_relief_bonus = min(5.0, class_diff * 0.20)
                else:
                    tougher_jump = abs(class_diff)
                    if tougher_jump <= 3:
                        similarity += 0.15
                    elif tougher_jump <= 8:
                        similarity += 0.10
                    elif tougher_jump <= 14:
                        similarity += 0.05

        if possible <= 0:
            continue

        normalized_similarity = clamp(similarity / possible, 0.0, 1.0)
        if normalized_similarity < 0.20:
            continue

        performance = record_performance_score(record)

        # 条件が近いほど実績を反映するが、旧版より50点へ寄せる。
        adjusted = (
            50.0
            + (performance - 50.0) * (
                0.40 + normalized_similarity * 0.35
            )
            + class_relief_bonus
        )

        weight = recency_weights[index] * (
            0.35 + normalized_similarity * 0.65
        )
        weighted_scores.append(clamp(adjusted) * weight)
        used_weights.append(weight)
        used_count += 1

    if not used_weights:
        return 50.0, 0

    raw = sum(weighted_scores) / sum(used_weights)

    # 有効1走は35％、2走は60％、3走は80％、4走以上で100％。
    reliability_by_count = {
        1: 0.35,
        2: 0.60,
        3: 0.80,
    }
    reliability = reliability_by_count.get(used_count, 1.0)

    # 類似度が低いレースばかりなら、さらに50点へ寄せる。
    weight_reliability = min(1.0, sum(used_weights) / 2.5)
    reliability *= max(0.55, weight_reliability)

    score = 50.0 + (raw - 50.0) * reliability
    return clamp(score), used_count


def calculate_trend_score(horse: Horse) -> float:
    """直近3走指数の上昇・下降を、安定度とは別に評価する。"""
    values = recent_time_values(horse)
    if not values:
        return 50.0
    if len(values) == 1:
        return time_index_to_score(values[-1]) * 0.50 + 25.0

    start = values[0]
    end = values[-1]
    improvement = end - start

    recent_level = average(
        [time_index_to_score(value) for value in values],
        50.0,
    )
    trend_component = clamp(50.0 + improvement * 1.5, 15.0, 90.0)

    # 前走が2走前より大幅に悪化した場合は下降を少し強めに反映。
    if len(values) >= 2 and values[-1] <= values[-2] - 15:
        trend_component -= 8.0

    return clamp(
        recent_level * 0.45
        + trend_component * 0.55
    )


def calculate_stability_score(horse: Horse) -> float:
    """直近指数・着差・位置取りのブレから、軸向きの安定度を算出する。"""
    recent_values = recent_time_values(horse)

    if recent_values:
        transformed = [time_index_to_score(value) for value in recent_values]
        mean_score = average(transformed, 50.0)
        floor_score = min(transformed)

        if len(recent_values) >= 2:
            raw_std = statistics.pstdev(recent_values)
            consistency_score = clamp(100.0 - raw_std * 2.3, 10, 100)
            trend = recent_values[-1] - recent_values[0]
            trend_score = clamp(50.0 + trend * 1.4, 15, 90)
        else:
            consistency_score = 50.0
            trend_score = 50.0

        index_stability = (
            mean_score * 0.35
            + floor_score * 0.30
            + consistency_score * 0.25
            + trend_score * 0.10
        )
    else:
        index_stability = 50.0

    recent_records = horse.records[:3]
    margins = [
        record.margin
        for record in recent_records
        if record.margin is not None
    ]

    if margins:
        avg_margin = average(margins, 2.0)
        if avg_margin <= 0.3:
            margin_level = 92.0
        elif avg_margin <= 0.7:
            margin_level = 82.0
        elif avg_margin <= 1.2:
            margin_level = 70.0
        elif avg_margin <= 1.8:
            margin_level = 58.0
        elif avg_margin <= 2.5:
            margin_level = 44.0
        else:
            margin_level = 28.0

        margin_std = statistics.pstdev(margins) if len(margins) >= 2 else 0.8
        margin_consistency = clamp(95.0 - margin_std * 24.0, 15, 95)
        margin_stability = margin_level * 0.70 + margin_consistency * 0.30
    else:
        margin_stability = 50.0

    positions = []
    for record in recent_records:
        if not record.passing:
            continue
        try:
            positions.append(int(record.passing.split("-")[-1]))
        except (TypeError, ValueError):
            continue

    if positions:
        position_std = statistics.pstdev(positions) if len(positions) >= 2 else 1.5
        position_consistency = clamp(90.0 - position_std * 10.0, 20, 90)
    else:
        position_consistency = 50.0

    big_defeats = sum(1 for margin in margins if margin >= 3.0)
    big_defeat_penalty = 14.0 if big_defeats >= 2 else 7.0 if big_defeats == 1 else 0.0

    score = (
        index_stability * 0.58
        + margin_stability * 0.30
        + position_consistency * 0.12
        - big_defeat_penalty
    )
    return clamp(score)


def calculate_stable_axis_score(horse: Horse) -> float:
    """複勝圏へ崩れにくい馬を評価する安定軸指数。"""
    score = (
        horse.score.avg5_score * 0.25
        + horse.score.same_condition_score * 0.10
        + horse.score.stability_score * 0.30
        + horse.score.recent_form * 0.15
        + horse.score.suitability * 0.05
        + horse.score.race_level * 0.10
        + horse.score.trend_score * 0.05
        - horse.score.danger_score * 0.25
    )
    return clamp(score)


def calculate_win_axis_score(horse: Horse) -> float:
    """一発の勝ち切り能力を評価する勝負軸指数。"""
    score = (
        horse.score.time_index * 0.20
        + horse.score.avg5_score * 0.18
        + horse.score.recent_form * 0.18
        + horse.score.recent_peak_score * 0.15
        + horse.score.ability_index * 0.14
        + horse.score.running_style * 0.08
        + horse.score.race_level * 0.07
        + horse.score.young_condition_change_bonus * 0.25
        - horse.score.danger_score * 0.20
    )
    return clamp(score)


def calculate_base_axis_score(horse: Horse) -> float:
    """
    条件適性・同条件近走を中立50点にした基礎軸指数。
    条件入力だけで何点上がったかを診断するために使う。
    """
    score = (
        horse.score.avg5_score * 0.22
        + 50.0 * 0.10
        + horse.score.stability_score * 0.20
        + horse.score.trend_score * 0.14
        + horse.score.race_level * 0.12
        + 50.0 * 0.05
        + horse.score.ability_index * 0.12
        + horse.score.recent_form * 0.05
        - horse.score.danger_score * 0.25
    )
    return clamp(score)


def calculate_axis_index(horse: Horse) -> float:
    """
    総合軸指数。

    条件系は合計15％に抑え、5走平均・安定度・上昇度・
    相手レベルなど複数項目がそろった馬を優先する。
    """
    score = (
        horse.score.avg5_score * 0.22
        + horse.score.same_condition_score * 0.10
        + horse.score.stability_score * 0.20
        + horse.score.trend_score * 0.14
        + horse.score.race_level * 0.12
        + horse.score.suitability * 0.05
        + horse.score.ability_index * 0.12
        + horse.score.recent_form * 0.05
        - horse.score.danger_score * 0.25
    )
    return clamp(score)


def smoothed_finish_rate(
    successes: int,
    count: int,
    prior_rate: float,
    prior_weight: float,
) -> float:
    """
    少数戦の100％・0％をそのまま信用しないベイズ型の平滑化率。
    戻り値は0～100％。
    """
    if count <= 0:
        return prior_rate * 100.0

    posterior = (
        successes + prior_rate * prior_weight
    ) / (count + prior_weight)
    return clamp(posterior * 100.0)


def recent_finish_rates(
    horse: Horse,
) -> Tuple[float, float, float, int]:
    known = [
        record
        for record in horse.records[:5]
        if record.finish_known and 1 <= record.finish < 99
    ]
    count = len(known)

    wins = sum(record.finish == 1 for record in known)
    top2 = sum(record.finish <= 2 for record in known)
    top3 = sum(record.finish <= 3 for record in known)

    return (
        smoothed_finish_rate(wins, count, 0.15, 3.0),
        smoothed_finish_rate(top2, count, 0.30, 3.0),
        smoothed_finish_rate(top3, count, 0.45, 3.0),
        count,
    )


def record_matches_current_condition(
    record: RaceRecord,
    conditions: RaceConditions,
) -> bool:
    """
    同条件率の集計対象。

    馬場状態の完全一致までは要求せず、芝ダート・距離・クラスを中心に判定する。
    過去の方が上位クラスの場合は対象から外さない。
    """
    compared = 0
    matched = 0

    if conditions.surface and record.surface:
        compared += 1
        if record.surface != conditions.surface:
            return False
        matched += 1

    if conditions.distance and record.distance:
        compared += 1
        if abs(record.distance - conditions.distance) > 200:
            return False
        matched += 1

    if conditions.race_class and record.race_class:
        compared += 1
        prior_level = class_score(record.race_class)
        current_level = class_score(conditions.race_class)

        # 大幅な昇級だけを別条件扱いにする。
        if current_level - prior_level > 14:
            return False
        matched += 1

    if conditions.venue and record.venue:
        compared += 1
        # 開催場違いは許容するが、同場なら一致材料を増やす。
        if record.venue == conditions.venue:
            matched += 1

    return compared >= 1 and matched >= 1


def same_condition_finish_rates(
    horse: Horse,
    conditions: RaceConditions,
) -> Tuple[float, float, int]:
    known = [
        record
        for record in horse.records[:5]
        if (
            record.finish_known
            and 1 <= record.finish < 99
            and record_matches_current_condition(record, conditions)
        )
    ]
    count = len(known)

    wins = sum(record.finish == 1 for record in known)
    top3 = sum(record.finish <= 3 for record in known)

    # 同条件は母数がさらに少なくなりやすいため、事前分布を強める。
    return (
        smoothed_finish_rate(wins, count, 0.15, 4.0),
        smoothed_finish_rate(top3, count, 0.45, 4.0),
        count,
    )


def rate_to_score(rate: float, baseline: float, sensitivity: float) -> float:
    """平滑化率を、他項目と合成できる50点中心の指数へ変換する。"""
    return clamp(50.0 + (rate - baseline) * sensitivity, 15.0, 95.0)


def calculate_last2_form_score(horse: Horse) -> float:
    records = [
        record
        for record in horse.records[:2]
        if record.finish_known or record.margin is not None
    ]
    if not records:
        return 50.0

    weights = [1.0, 0.75]
    weighted = []
    used_weights = []

    for index, record in enumerate(records):
        weighted.append(record_performance_score(record) * weights[index])
        used_weights.append(weights[index])

    return clamp(sum(weighted) / sum(used_weights))


def win_class_credit(
    record: RaceRecord,
    conditions: RaceConditions,
) -> float:
    """
    1着実績を今回クラスに合わせて補正する。

    重賞が今回条件の場合の目安:
      同格以上 100%
      OP・L     70%
      3勝       40%
      2勝       20%
    """
    prior_level = class_score(record.race_class)

    if conditions.race_class:
        current_level = class_score(conditions.race_class)

        if prior_level >= current_level - 3:
            return 1.00

        # 今回が重賞級のときは、下級条件勝利を明確に割り引く。
        if current_level >= 86:
            if prior_level >= 78:
                return 0.70
            if prior_level >= 74:
                return 0.40
            if prior_level >= 66:
                return 0.20
            if prior_level >= 58:
                return 0.12
            return 0.08

        class_gap = current_level - prior_level
        if class_gap <= 8:
            return 0.75
        if class_gap <= 14:
            return 0.55
        if class_gap <= 22:
            return 0.35
        return 0.18

    # 今回クラスが未入力でも絶対的な格を使って補正する。
    if prior_level >= 86:
        return 1.00
    if prior_level >= 78:
        return 0.70
    if prior_level >= 74:
        return 0.40
    if prior_level >= 66:
        return 0.20
    if prior_level >= 58:
        return 0.12
    return 0.08


def calculate_class_adjusted_win_score(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """
    直近5走の勝利を、勝ったクラスに応じて評価する。

    下級条件の連勝だけで重賞僅差馬を上回りにくくする一方、
    同格以上の勝利は強く残す。
    """
    known = [
        record
        for record in horse.records[:5]
        if record.finish_known and 1 <= record.finish < 99
    ]
    if not known:
        return 50.0

    recency_weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    weighted_credit = 0.0
    exposure = 0.0

    for index, record in enumerate(known):
        weight = recency_weights[index]
        exposure += weight

        if record.finish == 1:
            weighted_credit += weight * win_class_credit(
                record,
                conditions,
            )

    # 少数戦の1勝を過大評価しないよう、12%を事前値として平滑化。
    prior_rate = 0.12
    prior_weight = 2.5
    adjusted_rate = (
        weighted_credit + prior_rate * prior_weight
    ) / (exposure + prior_weight) * 100.0

    return rate_to_score(
        adjusted_rate,
        baseline=12.0,
        sensitivity=1.35,
    )


def high_class_margin_base_score(record: RaceRecord) -> Optional[float]:
    """重賞・OP級での僅差内容を0～100点へ変換する。"""
    level = class_score(record.race_class)
    if level < 78 or record.margin is None:
        return None

    margin = record.margin

    if record.finish_known and record.finish == 1:
        return 100.0
    if margin < 0:
        return 100.0

    if level >= 100:
        if margin <= 0.2:
            return 100.0
        if margin <= 0.5:
            return 95.0
        if margin <= 0.8:
            return 85.0
        if margin <= 1.0:
            return 75.0
        if margin <= 1.5:
            return 62.0
        return 45.0

    if level >= 92:
        if margin <= 0.2:
            return 98.0
        if margin <= 0.3:
            return 94.0
        if margin <= 0.5:
            return 88.0
        if margin <= 0.8:
            return 78.0
        if margin <= 1.0:
            return 70.0
        if margin <= 1.5:
            return 58.0
        return 43.0

    if level >= 86:
        if margin <= 0.2:
            return 94.0
        if margin <= 0.3:
            return 90.0
        if margin <= 0.5:
            return 84.0
        if margin <= 0.8:
            return 74.0
        if margin <= 1.0:
            return 66.0
        if margin <= 1.5:
            return 55.0
        return 40.0

    # L・OP級。
    if margin <= 0.2:
        return 88.0
    if margin <= 0.5:
        return 80.0
    if margin <= 0.8:
        return 70.0
    if margin <= 1.0:
        return 62.0
    if margin <= 1.5:
        return 52.0
    return 38.0


def calculate_high_class_close_score(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """
    GI・GII・GIII・L・OPで、勝ち馬へどれだけ迫ったかを評価する。

    1走だけの僅差は50点へ縮め、複数回続けて僅差だった馬を高くする。
    """
    recency_weights = [1.00, 0.90, 0.80, 0.70, 0.60]
    weighted_scores = []
    used_weights = []
    raw_scores = []

    current_level = (
        class_score(conditions.race_class)
        if conditions.race_class
        else None
    )

    for index, record in enumerate(horse.records[:5]):
        base = high_class_margin_base_score(record)
        if base is None:
            continue

        prior_level = class_score(record.race_class)
        adjusted = base

        # 今回より下のクラスでの僅差は少し割り引く。
        if current_level is not None and prior_level < current_level:
            gap = current_level - prior_level
            if gap <= 8:
                factor = 0.85
            elif gap <= 14:
                factor = 0.65
            else:
                factor = 0.45
            adjusted = 50.0 + (base - 50.0) * factor

        weight = recency_weights[index]
        weighted_scores.append(adjusted * weight)
        used_weights.append(weight)
        raw_scores.append(adjusted)

    if not used_weights:
        return 50.0

    weighted_average = sum(weighted_scores) / sum(used_weights)
    peak = max(raw_scores)

    # 平均を中心にしつつ、GI級の強い一戦も少し残す。
    raw = weighted_average * 0.78 + peak * 0.22

    reliability = {
        1: 0.45,
        2: 0.70,
        3: 0.85,
    }.get(len(raw_scores), 1.00)

    return clamp(50.0 + (raw - 50.0) * reliability)


def calculate_first_place_raw_score(horse: Horse) -> float:
    """
    今回1着になる可能性を評価する指数。

    下級条件の勝利数だけでなく、
    ・勝ったクラス
    ・上位クラスでの僅差好走
    ・5走平均、能力、相手レベル
    を重視する。
    """
    same_win_score = rate_to_score(
        horse.score.same_condition_win_rate,
        baseline=15.0,
        sensitivity=0.90,
    )

    score = (
        horse.score.class_adjusted_win_score * 0.10
        + horse.score.last2_form_score * 0.10
        + horse.score.time_index * 0.15
        + horse.score.avg5_score * 0.14
        + horse.score.ability_index * 0.14
        + same_win_score * 0.06
        + horse.score.recent_form * 0.08
        + horse.score.running_style * 0.04
        + horse.score.trend_score * 0.04
        + horse.score.race_level * 0.10
        + horse.score.high_class_close_score * 0.05
        + horse.score.young_condition_change_bonus * 0.55
        - horse.score.danger_score * 0.22
    )
    return clamp(score)


def calculate_in_money_raw_score(horse: Horse) -> float:
    """
    1～3着へ入る可能性を評価する相手専用指数。

    複勝率・連対率・安定度・着差・5走平均を中心にする。
    """
    recent_top2_score = rate_to_score(
        horse.score.recent_top2_rate,
        baseline=30.0,
        sensitivity=0.90,
    )
    recent_top3_score = rate_to_score(
        horse.score.recent_top3_rate,
        baseline=45.0,
        sensitivity=0.95,
    )
    same_top3_score = rate_to_score(
        horse.score.same_condition_top3_rate,
        baseline=45.0,
        sensitivity=0.75,
    )

    score = (
        recent_top3_score * 0.22
        + recent_top2_score * 0.10
        + same_top3_score * 0.10
        + horse.score.stability_score * 0.18
        + horse.score.avg5_score * 0.12
        + horse.score.recent_form * 0.10
        + horse.score.race_level * 0.08
        + horse.score.suitability * 0.05
        + horse.score.survival_score * 0.05
        + horse.score.young_lightweight_current_class_bonus * 0.50
        + horse.score.young_layoff_growth_bonus * 0.50
        - horse.score.danger_score * 0.18
    )
    return clamp(score)


def assign_expectancy_engine(
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> None:
    """
    7頭選定とは独立して、1着期待指数と馬券内期待指数を全頭へ付与する。
    """
    raw_first: Dict[int, float] = {}
    raw_in_money: Dict[int, float] = {}

    for horse in horses.values():
        (
            horse.score.recent_win_rate,
            horse.score.recent_top2_rate,
            horse.score.recent_top3_rate,
            horse.score.recent_rate_count,
        ) = recent_finish_rates(horse)

        (
            horse.score.same_condition_win_rate,
            horse.score.same_condition_top3_rate,
            horse.score.same_condition_rate_count,
        ) = same_condition_finish_rates(horse, conditions)

        horse.score.last2_form_score = round(
            calculate_last2_form_score(horse),
            1,
        )
        horse.score.class_adjusted_win_score = round(
            calculate_class_adjusted_win_score(
                horse,
                conditions,
            ),
            1,
        )
        horse.score.high_class_close_score = round(
            calculate_high_class_close_score(
                horse,
                conditions,
            ),
            1,
        )

        raw_first[horse.number] = calculate_first_place_raw_score(horse)
        raw_in_money[horse.number] = calculate_in_money_raw_score(horse)

    # 絶対評価を80％残し、レース内比較を20％だけ加える。
    normalized_first = blend_field_scores(
        raw_first,
        relative_low=45.0,
        relative_high=90.0,
        absolute_weight=0.80,
    )
    normalized_in_money = blend_field_scores(
        raw_in_money,
        relative_low=45.0,
        relative_high=90.0,
        absolute_weight=0.80,
    )

    for horse in horses.values():
        horse.score.first_place_score = normalized_first.get(
            horse.number,
            50.0,
        )
        horse.score.in_money_score = normalized_in_money.get(
            horse.number,
            50.0,
        )

    for horse in horses.values():
        horse.score.first_place_tiebreak_promoted = False

    first_ranked, promoted = first_place_tiebreak_decision(
        list(horses.values())
    )
    if promoted is not None:
        promoted.score.first_place_tiebreak_promoted = True

    for rank, horse in enumerate(first_ranked, start=1):
        horse.score.first_place_rank = rank

    in_money_ranked = sorted(
        horses.values(),
        key=lambda horse: (
            horse.score.in_money_score,
            horse.score.recent_top3_rate,
            horse.score.stability_score,
            horse.score.avg5_score,
        ),
        reverse=True,
    )
    for rank, horse in enumerate(in_money_ranked, start=1):
        horse.score.in_money_rank = rank


def axis_ban_judgement(horse: Horse) -> Tuple[bool, str]:
    """平均点で弱点を隠さないため、軸禁止条件を別判定する。"""
    recent_values = recent_time_values(horse)
    recent_avg = average(recent_values, 0.0) if recent_values else None

    hard_reasons: List[str] = []
    soft_reasons: List[str] = []

    if horse.score.danger_score >= 55:
        hard_reasons.append("危険度55以上")
    if horse.score.time_index < 25:
        hard_reasons.append("タイム指数25未満")
    if recent_avg is not None and recent_avg <= -15:
        hard_reasons.append("直近3走平均が大幅マイナス")
    if horse.layoff_weeks >= 13 and abs(horse.weight_change) >= 10:
        hard_reasons.append("長期休養＋大幅馬体変動")

    if horse.score.time_index < 35:
        soft_reasons.append("タイム指数35未満")
    if horse.score.recent_form < 50:
        soft_reasons.append("近走内容50未満")
    if horse.score.suitability < 45:
        soft_reasons.append("条件適性45未満")
    if horse.score.danger_score >= 40:
        soft_reasons.append("危険度40以上")
    if recent_avg is not None and recent_avg < 0:
        soft_reasons.append("直近3走平均マイナス")
    if horse.score.stability_score < 45:
        soft_reasons.append("安定度45未満")

    banned = bool(hard_reasons) or len(soft_reasons) >= 2
    reasons = hard_reasons if hard_reasons else soft_reasons[:3]
    return banned, "・".join(reasons)


def classify_axis_type(horse: Horse) -> str:
    if horse.score.stable_axis_score >= horse.score.win_axis_score + 4:
        base = "安定型"
    elif horse.score.win_axis_score >= horse.score.stable_axis_score + 4:
        base = "勝負型"
    else:
        base = "総合型"

    if 4 <= horse.popularity <= 8:
        return f"穴・{base}"
    return base


def assign_axis_engine(horses: Dict[int, Horse]) -> None:
    """全頭へ安定軸・勝負軸・総合軸・軸禁止を付与する。"""
    for horse in horses.values():
        horse.score.stability_score = round(calculate_stability_score(horse), 1)

    for horse in horses.values():
        horse.score.stable_axis_score = round(
            calculate_stable_axis_score(horse),
            1,
        )
        horse.score.win_axis_score = round(
            calculate_win_axis_score(horse),
            1,
        )
        horse.score.base_axis_score = round(
            calculate_base_axis_score(horse),
            1,
        )
        horse.score.axis_index = round(calculate_axis_index(horse), 1)
        horse.score.condition_boost = round(
            horse.score.axis_index - horse.score.base_axis_score,
            1,
        )
        banned, reason = axis_ban_judgement(horse)
        horse.score.axis_banned = banned
        horse.score.axis_ban_reason = reason
        horse.score.axis_type = classify_axis_type(horse)

    ranked = sorted(
        horses.values(),
        key=lambda horse: (
            not horse.score.axis_banned,
            horse.score.axis_index,
            horse.score.stability_score,
            horse.score.time_index,
        ),
        reverse=True,
    )
    for rank, horse in enumerate(ranked, start=1):
        horse.score.axis_rank = rank


def assign_weight_allowance(horses: Dict[int, Horse]) -> None:
    """同性の標準斤量との差を算出し、性別差を二重加点しない。"""
    by_sex: Dict[str, List[float]] = {}
    all_weights: List[float] = []

    for horse in horses.values():
        if horse.carried_weight <= 0:
            continue
        all_weights.append(horse.carried_weight)
        if horse.sex:
            by_sex.setdefault(horse.sex, []).append(horse.carried_weight)

    def standard_weight(values: List[float]) -> float:
        if not values:
            return 0.0
        # 最頻値を標準斤量とし、同数なら重い方を採用する。
        return max(statistics.multimode(values))

    overall_standard = standard_weight(all_weights)

    for horse in horses.values():
        horse.weight_allowance = 0.0
        if horse.carried_weight <= 0:
            continue

        peers = by_sex.get(horse.sex, []) if horse.sex else []
        standard = standard_weight(peers) if len(peers) >= 2 else overall_standard
        if standard > 0:
            horse.weight_allowance = round(max(0.0, standard - horse.carried_weight), 1)


def calculate_weight_bonus(horse: Horse) -> float:
    """軽斤量は補助材料に限定し、単独で順位を大きく動かさない。"""
    allowance = horse.weight_allowance

    if allowance >= 2.0:
        bonus = 2.0
    elif allowance >= 1.0:
        bonus = 1.0
    elif allowance >= 0.5:
        bonus = 0.5
    else:
        bonus = 0.0

    recent_values = recent_time_values(horse)
    recent_peak = max(recent_values) if recent_values else -99

    # 軽斤量＋前向きな脚質＋直近指数の裏付けがある場合だけ小幅加点。
    if (
        allowance >= 2.0
        and horse.running_style in ("逃げ", "先行")
        and recent_peak >= 10
    ):
        bonus += 1.0
    elif (
        allowance >= 1.0
        and horse.running_style in ("逃げ", "先行")
        and recent_peak >= 0
    ):
        bonus += 0.5

    return clamp(bonus, 0, 3)


def calculate_danger_score(horse: Horse) -> float:
    """能力とは別に、軸として危険な材料を0～100で数値化する。"""
    danger = 0.0
    recent_values = recent_time_values(horse)

    if recent_values:
        recent_avg = average(recent_values)
        if recent_avg <= -20:
            danger += 34
        elif recent_avg <= -15:
            danger += 28
        elif recent_avg <= -10:
            danger += 20
        elif recent_avg < 0:
            danger += 9

        if horse.time_index.last1 is not None and horse.time_index.last1 <= -20:
            danger += 8

    if horse.layoff_weeks >= 20:
        danger += 20
    elif horse.layoff_weeks >= 13:
        danger += 13
    elif horse.layoff_weeks >= 9:
        danger += 8

    if abs(horse.weight_change) >= 15:
        danger += 12
    elif abs(horse.weight_change) >= 10:
        danger += 7

    if horse.running_style == "逃げ" and horse.front_competitors >= 2:
        danger += 12
    elif horse.running_style == "先行" and horse.front_competitors >= 4:
        danger += 5

    if horse.score.recent_form < 50:
        danger += 8
    if horse.score.race_level < 52:
        danger += 5

    return clamp(danger)


def calculate_survival_score(horse: Horse, conditions: RaceConditions) -> float:
    """能力順位が低くても、近走上向き・軽斤量・相手弱化の馬を残す。"""
    score = 48.0
    recent_values = recent_time_values(horse)

    if recent_values:
        transformed = [time_index_to_score(value) for value in recent_values]
        score += (average(transformed) - 50) * 0.50

        # 3走前→2走前→前走で改善している馬を加点する。
        if len(recent_values) == 3 and recent_values[0] < recent_values[1] < recent_values[2]:
            score += 7
        elif horse.time_index.last1 is not None and horse.time_index.last1 >= 0:
            score += 3

        # 平均だけで消さず、直近3走内の高指数も補助的に残す。
        peak = max(recent_values)
        if peak >= 30:
            score += 7
        elif peak >= 20:
            score += 5
        elif peak >= 10:
            score += 3

    score += (horse.score.time_index - 50) * 0.18
    score += (horse.score.recent_peak_score - 50) * 0.12
    score += class_relief_bonus(horse, conditions) * 0.55
    score += horse.score.weight_bonus
    score += horse.score.young_condition_change_bonus * 0.55
    score += horse.score.young_lightweight_current_class_bonus
    score += horse.score.young_layoff_growth_bonus * 0.75

    # 高格レース勝利は平均値に埋もれないよう、生存判定にも小幅反映する。
    # 軸指数には入れず、相手候補を落としすぎないための救済用途に限定。
    score += horse.score.high_class_win_bonus * 0.60

    if horse.age and horse.age <= 5:
        score += 4
    elif horse.age >= 9 and horse.score.time_index < 55 and horse.score.weight_bonus < 2:
        # 高齢減点は、指数や軽斤量の裏付けがない時だけ小さく使う。
        score -= 1

    if 4 <= horse.popularity <= 6:
        score += 6
    elif 7 <= horse.popularity <= 8:
        score += 2

    if horse.records and horse.records[0].margin is not None:
        if horse.records[0].margin <= 0.5:
            score += 5
        elif horse.records[0].margin >= 3.0:
            score -= 4

    # 長期休養や大幅馬体変動は「消し」ではなく、わずかな抑制だけにする。
    if horse.layoff_weeks >= 20:
        score -= 3
    if abs(horse.weight_change) >= 15:
        score -= 2

    return clamp(score, 0, 130)


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
        horse.front_competitors = front_count

    assign_weight_allowance(horses)
    closing_scores = score_closing_power_all(horses)

    raw_time_scores: Dict[int, float] = {}
    raw_peak_scores: Dict[int, float] = {}
    raw_avg5_scores: Dict[int, float] = {}

    # 基礎項目とタイム指数の固定基準値を先に計算する。
    for horse in horses.values():
        horse.score.recent_form = round(score_recent_form(horse), 1)
        horse.score.race_level = round(score_race_level(horse, conditions), 1)
        horse.score.suitability = round(score_suitability(horse, conditions), 1)
        horse.score.running_style = round(score_running_style(horse, front_count), 1)
        horse.score.closing_power = round(closing_scores.get(horse.number, 50.0), 1)
        horse.score.transition_bonus = round(class_relief_bonus(horse, conditions), 1)
        horse.score.age_adjustment = round(age_adjustment(horse), 1)
        horse.score.weight_bonus = round(calculate_weight_bonus(horse), 1)
        horse.score.high_class_win_bonus = recent_high_class_win_bonus(horse)
        horse.score.young_condition_change_bonus = round(
            calculate_young_condition_change_bonus(
                horse,
                conditions,
            ),
            1,
        )
        horse.score.young_lightweight_current_class_bonus = round(
            calculate_young_lightweight_current_class_bonus(
                horse,
                horses,
                conditions,
            ),
            1,
        )
        horse.score.young_layoff_growth_bonus = round(
            calculate_young_layoff_growth_bonus(
                horse,
                horses,
                conditions,
            ),
            1,
        )
        same_condition_score, same_condition_count = (
            score_same_condition_recent(horse, conditions)
        )
        horse.score.same_condition_score = round(
            same_condition_score,
            1,
        )
        horse.score.same_condition_count = same_condition_count
        horse.score.trend_score = round(calculate_trend_score(horse), 1)

        raw_time_scores[horse.number] = score_time_index(horse, mode)
        raw_peak_scores[horse.number] = recent_peak_score(horse)
        raw_avg5_scores[horse.number] = time_index_to_score(
            horse.time_index.avg5
        )

    # 固定基準65％＋レース内相対順位35％で、99～100点への張り付きを解消する。
    normalized_time_scores = blend_field_scores(
        raw_time_scores,
        relative_low=43.0,
        relative_high=91.0,
        absolute_weight=0.65,
    )
    normalized_peak_scores = blend_field_scores(
        raw_peak_scores,
        relative_low=45.0,
        relative_high=90.0,
        absolute_weight=0.62,
    )
    normalized_avg5_scores = blend_field_scores(
        raw_avg5_scores,
        relative_low=45.0,
        relative_high=90.0,
        absolute_weight=0.80,
    )

    for horse in horses.values():
        horse.score.time_index = normalized_time_scores.get(horse.number, 50.0)
        horse.score.recent_peak_score = normalized_peak_scores.get(horse.number, 50.0)
        horse.score.avg5_score = normalized_avg5_scores.get(horse.number, 50.0)

        total = (
            horse.score.recent_form * WEIGHTS["recent_form"]
            + horse.score.race_level * WEIGHTS["race_level"]
            + horse.score.suitability * WEIGHTS["suitability"]
            + horse.score.running_style * WEIGHTS["running_style"]
            + horse.score.closing_power * WEIGHTS["closing_power"]
            + horse.score.time_index * WEIGHTS["time_index"]
        )

        # 転入・相手弱化と年齢は、各項目に埋もれない小幅な直接補正にする。
        total += horse.score.transition_bonus * 0.35
        total += horse.score.age_adjustment
        # 未知の条件替わりは能力そのものではないため、総合点には小幅だけ反映。
        total += horse.score.young_condition_change_bonus * 0.20
        horse.score.total = round(clamp(total), 1)

    avg5_ranked = sorted(
        horses.values(),
        key=lambda horse: (
            horse.score.avg5_score,
            horse.time_index.avg5
            if horse.time_index.avg5 is not None
            else -999,
        ),
        reverse=True,
    )
    for rank, horse in enumerate(avg5_ranked, start=1):
        horse.score.avg5_rank = rank

    assign_fixed_ability_indices(horses)

    raw_survival_scores: Dict[int, float] = {}
    for horse in horses.values():
        horse.score.danger_score = round(calculate_danger_score(horse), 1)

        # 危険度が極端に高い馬は、救済項目だけで残さない。
        if horse.score.danger_score >= 45:
            horse.score.young_lightweight_current_class_bonus = 0.0
            horse.score.young_layoff_growth_bonus = 0.0

        raw_survival_scores[horse.number] = calculate_survival_score(horse, conditions)

    normalized_survival_scores = blend_survival_scores(raw_survival_scores)

    for horse in horses.values():
        horse.score.survival_score = normalized_survival_scores.get(horse.number, 50.0)

        # 印選定は能力だけでなく、生存・直近指数・軽斤量・危険度を合成する。
        horse.score.selection_score = round(clamp(
            horse.score.ability_index * 0.38
            + horse.score.survival_score * 0.27
            + horse.score.time_index * 0.20
            + horse.score.recent_peak_score * 0.10
            + horse.score.weight_bonus
            + horse.score.high_class_win_bonus
            + horse.score.young_condition_change_bonus * 0.70
            + horse.score.young_lightweight_current_class_bonus
            + horse.score.young_layoff_growth_bonus
            - horse.score.danger_score * 0.18,
            0,
            100,
        ), 1)

    # 既存の7頭選定条件を守るため、従来の軸エンジンはそのまま残す。
    assign_axis_engine(horses)

    # 印の役割分け専用。7頭の顔ぶれには影響させない。
    assign_expectancy_engine(horses, conditions)

    return horses


# =========================================================
# Selection
# =========================================================

def ranking_key(horse: Horse):
    return (
        horse.score.ability_index,
        horse.score.total,
        horse.score.recent_form,
        horse.score.race_level,
        horse.score.time_index,
        -horse.popularity,
        -horse.number,
    )


def axis_selection_score(horse: Horse) -> float:
    """互換用。軸選定は独立した軸指数を利用する。"""
    return horse.score.axis_index


def middle_selection_key(horse: Horse):
    return (
        horse.score.selection_score,
        horse.score.survival_score,
        horse.score.time_index,
        horse.score.ability_index,
        -horse.popularity,
    )


def build_comment(horse: Horse) -> str:
    reasons = []

    if horse.score.upset_boundary_promoted:
        if horse.score.upset_boundary_rule == "相手特化昇格":
            reasons.append("荒れ相手特化判定で昇格")
        else:
            reasons.append("荒れ境界再判定で昇格")

    if horse.mark == "◎":
        if horse.score.first_place_tiebreak_promoted:
            reasons.append("僅差最終判定で1着期待1位")
        elif horse.score.first_place_rank == 1:
            reasons.append("全頭1着期待指数1位")
        else:
            reasons.append("相手選定内1着期待最上位")
    elif horse.score.in_money_rank <= 3:
        reasons.append("馬券内期待指数上位")

    if horse.score.axis_banned and horse.popularity <= 3:
        reasons.append(f"軸禁止：{horse.score.axis_ban_reason}")
    elif horse.score.axis_index >= 75:
        reasons.append(f"軸指数上位・{horse.score.axis_type}")

    if horse.score.recent_form >= 75:
        reasons.append("近走内容が優秀")
    elif horse.score.recent_form <= 45:
        reasons.append("近走内容は低評価")

    if horse.score.transition_bonus >= 8:
        reasons.append("相手弱化・転入を評価")
    elif horse.score.race_level >= 70:
        reasons.append("相手レベルを高評価")

    if horse.score.suitability >= 72:
        reasons.append("今回条件への適性あり")

    if horse.score.stability_score >= 75:
        reasons.append("直近3走の安定度が高い")
    elif horse.score.stability_score < 45:
        reasons.append("直近3走のブレに注意")

    if horse.score.closing_power >= 72:
        reasons.append("距離別の上がり評価上位")

    if horse.score.time_index >= 70:
        reasons.append("近走タイム指数も上位")
    elif horse.score.time_index <= 35:
        reasons.append("近走タイム指数は危険")

    if horse.score.survival_score >= 70:
        reasons.append("生存指数が高い")

    if horse.score.weight_bonus >= 6:
        reasons.append("軽斤量と先行力を評価")
    elif horse.score.weight_bonus >= 2:
        reasons.append("軽斤量を評価")

    if horse.score.young_condition_change_bonus >= 6:
        reasons.append("3歳の芝短距離替わりを強く評価")
    elif horse.score.young_condition_change_bonus >= 3:
        reasons.append("3歳の条件替わり上昇を評価")

    if horse.score.young_lightweight_current_class_bonus >= 4:
        reasons.append("3歳軽斤量と現級善戦を評価")

    if horse.score.young_layoff_growth_bonus >= 4:
        reasons.append("3歳休養明けの成長を評価")

    if horse.score.recent_peak_score >= 85:
        reasons.append("直近3走内に高指数")

    if horse.score.high_class_close_score >= 88:
        reasons.append("上位クラスの僅差実績が強い")
    elif horse.score.high_class_close_score >= 78:
        reasons.append("重賞・OP級の僅差実績あり")

    if horse.score.high_class_win_bonus >= 6:
        reasons.append("直近の高格重賞勝利を評価")
    elif horse.score.high_class_win_bonus >= 4:
        reasons.append("直近のOP級勝利を評価")

    if horse.score.danger_score >= 45:
        reasons.append("休養・指数面の危険あり")
    elif horse.running_style == "逃げ" and horse.front_competitors >= 2:
        reasons.append("同型との先行争いに注意")

    if horse.popularity <= 3 and horse.score.ability_index < 75:
        reasons.append("上位人気のため印は残す")

    if not reasons:
        reasons.append("総合バランスで選出")

    return "・".join(reasons[:3])


def mark_order_key(horse: Horse):
    """旧版互換。7頭選定の不足枠を埋める順位には従来基準を使う。"""
    return (
        horse.score.ability_index,
        horse.score.selection_score,
        horse.score.axis_index,
        horse.score.recent_form,
        horse.score.time_index,
        -horse.popularity,
        -horse.number,
    )


UPSET_BOUNDARY_TOTAL_GAP = 1.5
UPSET_BOUNDARY_MAX_REPLACEMENTS = 2
UPSET_PARTNER_IN_MONEY_GAIN = 3
UPSET_PARTNER_FIRST_DEFICIT = 2


def apply_upset_boundary_rerank(
    base_pool: List[Horse],
    horses: Dict[int, Horse],
    protected_numbers: set,
    max_replacements: int = UPSET_BOUNDARY_MAX_REPLACEMENTS,
    total_gap: float = UPSET_BOUNDARY_TOTAL_GAP,
) -> List[Horse]:
    """
    荒れレースモード専用の境界再判定。

    内部総合差が1.5以内の選定外馬を、次のどちらかで救済する。

    通常昇格:
      ・1着期待順位が上
      ・馬券内期待順位も上

    相手特化昇格:
      ・馬券内期待順位が3順位以上上
      ・1着期待順位は選定馬より2順位以内の下まで許容

    上位3人気と既存軸候補は保護し、入れ替えは最大2頭。
    一度昇格した馬は同じ判定内では再び落とさない。
    """
    for horse in horses.values():
        horse.score.upset_boundary_promoted = False
        horse.score.upset_boundary_demoted = False
        horse.score.upset_boundary_rule = ""

    selected = list(base_pool)
    selected_numbers = {horse.number for horse in selected}
    original_outsiders = [
        horse
        for horse in horses.values()
        if horse.number not in selected_numbers
    ]

    promoted_numbers = set()

    for _ in range(max_replacements):
        qualifying_pairs = []

        replaceable = [
            horse
            for horse in selected
            if horse.number not in protected_numbers
            and horse.number not in promoted_numbers
        ]

        for outsider in original_outsiders:
            if outsider.number in selected_numbers:
                continue

            for insider in replaceable:
                internal_gap = (
                    insider.score.total
                    - outsider.score.total
                )

                if internal_gap > total_gap:
                    continue

                first_gain = (
                    insider.score.first_place_rank
                    - outsider.score.first_place_rank
                )
                in_money_gain = (
                    insider.score.in_money_rank
                    - outsider.score.in_money_rank
                )
                first_deficit = (
                    outsider.score.first_place_rank
                    - insider.score.first_place_rank
                )

                standard_rule = (
                    first_gain > 0
                    and in_money_gain > 0
                )
                partner_rule = (
                    in_money_gain >= UPSET_PARTNER_IN_MONEY_GAIN
                    and first_deficit <= UPSET_PARTNER_FIRST_DEFICIT
                )

                if standard_rule:
                    rule_name = "通常昇格"
                    rule_priority = 2
                elif partner_rule:
                    rule_name = "相手特化昇格"
                    rule_priority = 1
                else:
                    continue

                qualifying_pairs.append(
                    (
                        outsider.score.total,
                        outsider.score.selection_score,
                        rule_priority,
                        in_money_gain,
                        first_gain,
                        -abs(internal_gap),
                        -outsider.popularity,
                        -outsider.number,
                        rule_name,
                        outsider,
                        insider,
                    )
                )

        if not qualifying_pairs:
            break

        # 内部総合が高い選定外馬を優先。
        # 同点付近では通常昇格、馬券内順位の改善幅、総合差で決める。
        qualifying_pairs.sort(reverse=True, key=lambda row: row[:8])
        rule_name = qualifying_pairs[0][-3]
        outsider = qualifying_pairs[0][-2]
        insider = qualifying_pairs[0][-1]

        replace_index = next(
            index
            for index, horse in enumerate(selected)
            if horse.number == insider.number
        )
        selected[replace_index] = outsider

        selected_numbers.remove(insider.number)
        selected_numbers.add(outsider.number)
        promoted_numbers.add(outsider.number)

        outsider.score.upset_boundary_promoted = True
        outsider.score.upset_boundary_rule = rule_name
        insider.score.upset_boundary_demoted = True

    return selected


def select_mark_pool(
    horses: Dict[int, Horse],
    upset_mode: bool = False,
) -> List[Horse]:
    """
    v0.6.8と同じ条件で7頭を選ぶ。

    通常モード:
      4～8番人気を相手候補の中心にし、9番人気以下は原則除外。

    荒れレースモード:
      人気薄の消しを解除し、4番人気以下をすべて相手候補にする。

    上位3人気を残す基本方針と、7頭の選定数は変更しない。
    """
    confidence_stars, race_difficulty, _, axis_candidates = axis_confidence(horses)
    _, axis_operation, primary_axis = axis_guidance(
        axis_candidates,
        race_difficulty,
        confidence_stars,
    )

    actual_axes: List[Horse] = []
    if primary_axis is not None:
        actual_axes = (
            axis_candidates[:2]
            if axis_operation == "軸候補2頭"
            else axis_candidates[:1]
        )

    top_popular = sorted(
        [
            horse
            for horse in horses.values()
            if 1 <= horse.popularity <= 3
        ],
        key=lambda horse: horse.popularity,
    )

    if len(top_popular) < 3:
        existing = {horse.number for horse in top_popular}
        fallback = [
            horse
            for horse in sorted(horses.values(), key=ranking_key, reverse=True)
            if horse.number not in existing
        ]
        top_popular.extend(fallback[: 3 - len(top_popular)])

    mandatory: List[Horse] = []
    mandatory_numbers = set()
    for horse in actual_axes + top_popular[:3]:
        if horse.number in mandatory_numbers:
            continue
        mandatory.append(horse)
        mandatory_numbers.add(horse.number)

    remaining_slots = max(0, 7 - len(mandatory))

    middle_candidates = sorted(
        [
            horse
            for horse in horses.values()
            if (
                (
                    upset_mode
                    and horse.popularity >= 4
                )
                or (
                    not upset_mode
                    and 4 <= horse.popularity <= 8
                )
            )
            and horse.number not in mandatory_numbers
        ],
        key=middle_selection_key,
        reverse=True,
    )

    base_pool = mandatory + middle_candidates[:remaining_slots]
    used = {horse.number for horse in base_pool}

    if len(base_pool) < 7:
        fallback = [
            horse
            for horse in sorted(horses.values(), key=mark_order_key, reverse=True)
            if horse.number not in used
        ]
        base_pool.extend(fallback[: 7 - len(base_pool)])

    base_pool = base_pool[:7]

    if upset_mode:
        base_pool = apply_upset_boundary_rerank(
            base_pool,
            horses,
            protected_numbers=mandatory_numbers,
        )

    return base_pool[:7]


FIRST_PLACE_TIEBREAK_GAP = 1.5


def first_place_order_key(horse: Horse):
    return (
        horse.score.first_place_score,
        horse.score.last2_form_score,
        horse.score.time_index,
        horse.score.avg5_score,
        horse.score.ability_index,
        -horse.popularity,
        -horse.number,
    )


def wins_close_first_place_tiebreak(
    challenger: Horse,
    leader: Horse,
) -> bool:
    """
    1着期待指数差が1.5以内のときだけ使う最終判定。

    次の3項目すべてで挑戦馬が上なら、1着期待順位を逆転する。
      ・上級僅差力
      ・レースレベル
      ・5走平均順位
    """
    gap = (
        leader.score.first_place_score
        - challenger.score.first_place_score
    )
    if gap < 0 or gap > FIRST_PLACE_TIEBREAK_GAP:
        return False

    return (
        challenger.score.high_class_close_score
        > leader.score.high_class_close_score
        and challenger.score.race_level
        > leader.score.race_level
        and challenger.score.avg5_rank
        < leader.score.avg5_rank
    )


def first_place_tiebreak_decision(
    candidates: List[Horse],
) -> Tuple[List[Horse], Optional[Horse]]:
    """
    通常は1着期待指数順。

    上位2頭の指数差が1.5以内で、2位馬が指定3項目を
    すべて上回る場合だけ1位と2位を入れ替える。
    """
    ranked = sorted(
        candidates,
        key=first_place_order_key,
        reverse=True,
    )
    promoted: Optional[Horse] = None

    if len(ranked) >= 2:
        leader = ranked[0]
        challenger = ranked[1]

        if wins_close_first_place_tiebreak(
            challenger,
            leader,
        ):
            ranked[0], ranked[1] = challenger, leader
            promoted = challenger

    return ranked, promoted


def rank_first_place_candidates(
    candidates: List[Horse],
) -> List[Horse]:
    ranked, _ = first_place_tiebreak_decision(candidates)
    return ranked


def in_money_order_key(horse: Horse):
    return (
        horse.score.in_money_score,
        horse.score.recent_top3_rate,
        horse.score.recent_top2_rate,
        horse.score.stability_score,
        horse.score.avg5_score,
        horse.score.selection_score,
        -horse.popularity,
        -horse.number,
    )


def first_place_support_count(horse: Horse) -> int:
    signals = (
        horse.score.class_adjusted_win_score >= 56,
        horse.score.high_class_close_score >= 80,
        horse.score.young_condition_change_bonus >= 6,
        horse.score.last2_form_score >= 70,
        horse.score.time_index >= 75,
        horse.score.avg5_score >= 72,
        horse.score.ability_index >= 80,
        horse.score.same_condition_win_rate >= 20
        and horse.score.same_condition_rate_count >= 2,
        horse.score.trend_score >= 65,
        horse.score.race_level >= 70,
    )
    return sum(bool(signal) for signal in signals)


def first_place_axis_analysis(
    candidates: List[Horse],
) -> Tuple[str, str, str, float, List[Horse], Optional[Horse]]:
    """
    出走全頭から、1着期待指数による単独軸を判定する。

    相手7頭の選定条件とは独立させ、選定外に本当の1着期待1位が
    いる場合も軸候補として拾う。
    """
    ranked = rank_first_place_candidates(candidates)
    if not ranked:
        return "★☆☆☆☆", "大混戦", "単独軸非推奨", 0.0, [], None

    first = ranked[0]
    second_score = (
        ranked[1].score.first_place_score
        if len(ranked) >= 2
        else first.score.first_place_score - 10
    )
    # 僅差判定で順位が逆転した場合も、指数差は正の値で表示する。
    gap = abs(first.score.first_place_score - second_score)
    support = first_place_support_count(first)

    eligible = (
        first.score.first_place_score >= 78
        and gap >= 2.5
        and first.score.danger_score < 35
        and support >= 3
        and not first.score.axis_banned
    )

    if eligible:
        if first.score.first_place_score >= 84 and gap >= 5:
            stars = "★★★★★"
            difficulty = "本命寄り"
        elif first.score.first_place_score >= 81 and gap >= 3.5:
            stars = "★★★★☆"
            difficulty = "やや本命"
        else:
            stars = "★★★☆☆"
            difficulty = "混戦"
        operation = "単独軸候補"
        axis = first
    else:
        if first.score.first_place_score >= 75:
            stars = "★★☆☆☆"
            difficulty = "混戦"
        else:
            stars = "★☆☆☆☆"
            difficulty = "大混戦"
        operation = "単独軸非推奨"
        axis = None

    return stars, difficulty, operation, gap, ranked, axis


def select_marks_full(
    horses: Dict[int, Horse],
    upset_mode: bool = False,
) -> List[Horse]:
    """
    v0.6.13までと同じ印付けを行い、内部では7頭選定を維持する。

    通常:
      ◎・○・▲・△・☆・注・穴 = 7頭

    選定外の強い単独軸を追加する例外時:
      ◎・○・▲・△・☆・注・穴・抑 = 8頭
    """
    for horse in horses.values():
        horse.mark = ""
        horse.comment = ""

    base_pool = select_mark_pool(horses, upset_mode=upset_mode)
    if not base_pool or not horses:
        return []

    base_numbers = {horse.number for horse in base_pool}
    all_horses = list(horses.values())

    (
        _,
        _,
        _,
        _,
        full_ranked,
        full_primary_axis,
    ) = first_place_axis_analysis(all_horses)

    full_leader = full_ranked[0] if full_ranked else None
    add_outside_axis = (
        not upset_mode
        and full_leader is not None
        and full_leader.number not in base_numbers
        and full_primary_axis is not None
        and full_primary_axis.number == full_leader.number
    )

    if add_outside_axis:
        # 軸基準を満たした選定外馬だけを◎として追加。
        first_choice = full_leader
        partners = list(base_pool)
        partner_marks = ("○", "▲", "△", "☆", "注", "穴", "抑")
    else:
        # 選定外1位が弱い場合は増やさず、従来7頭内から◎を決める。
        base_ranked = rank_first_place_candidates(base_pool)
        first_choice = base_ranked[0]
        partners = [
            horse
            for horse in base_pool
            if horse.number != first_choice.number
        ]
        partner_marks = ("○", "▲", "△", "☆", "注", "穴")

    partners.sort(key=in_money_order_key, reverse=True)

    selected: List[Horse] = []

    first_choice.mark = "◎"
    first_choice.comment = build_comment(first_choice)
    selected.append(first_choice)

    for mark, horse in zip(partner_marks, partners):
        horse.mark = mark
        horse.comment = build_comment(horse)
        selected.append(horse)

    return selected


RESERVE_RETENTION_IN_MONEY_WEIGHT = 0.60
RESERVE_RETENTION_FIRST_WEIGHT = 0.25
RESERVE_RETENTION_ABILITY_WEIGHT = 0.15
RESERVE_RETENTION_TIE_GAP = 0.5


def calculate_reserve_retention_score(horse: Horse) -> float:
    """
    内部7頭から、実際に馬券対象へ残す6頭を決めるための指数。

    馬券内期待を最重視しつつ、1着期待と能力指数を加える。
    印の並びだけで予備へ落ちる事故を防ぐ。
    """
    score = (
        horse.score.in_money_score
        * RESERVE_RETENTION_IN_MONEY_WEIGHT
        + horse.score.first_place_score
        * RESERVE_RETENTION_FIRST_WEIGHT
        + horse.score.ability_index
        * RESERVE_RETENTION_ABILITY_WEIGHT
    )
    return round(score, 1)


def actual_axis_protected_numbers(
    horses: Dict[int, Horse],
) -> set:
    """絶対基準を満たした軸候補を、予備落ちから保護する。"""
    protected = set()

    (
        confidence_stars,
        race_difficulty,
        _,
        axis_candidates,
    ) = axis_confidence(horses)

    _, axis_operation, primary_axis = axis_guidance(
        axis_candidates,
        race_difficulty,
        confidence_stars,
    )

    if primary_axis is not None:
        axis_count = 2 if axis_operation == "軸候補2頭" else 1
        protected.update(
            horse.number
            for horse in axis_candidates[:axis_count]
        )

    (
        _,
        _,
        _,
        _,
        _,
        first_place_primary_axis,
    ) = first_place_axis_analysis(list(horses.values()))

    if first_place_primary_axis is not None:
        protected.add(first_place_primary_axis.number)

    return protected


def set_reserve_protection_flags(
    full_selected: List[Horse],
    horses: Dict[int, Horse],
) -> set:
    """
    予備へ落とさない馬を決める。

      ・◎
      ・絶対基準を満たした軸候補
      ・1着期待順位と馬券内期待順位が両方5位以内
    """
    for horse in horses.values():
        horse.score.reserve_retention_score = (
            calculate_reserve_retention_score(horse)
        )
        horse.score.reserve_protected = False
        horse.score.reserve_protection_reason = ""

    axis_numbers = actual_axis_protected_numbers(horses)
    protected_numbers = set()

    for horse in full_selected:
        reasons = []

        if horse.mark == "◎":
            reasons.append("◎")

        if horse.number in axis_numbers:
            reasons.append("軸候補")

        if (
            1 <= horse.score.first_place_rank <= 5
            and 1 <= horse.score.in_money_rank <= 5
        ):
            reasons.append("1着・馬券内とも5位以内")

        if reasons:
            horse.score.reserve_protected = True
            horse.score.reserve_protection_reason = "・".join(reasons)
            protected_numbers.add(horse.number)

    return protected_numbers


def choose_reserve_horse(
    full_selected: List[Horse],
    horses: Dict[int, Horse],
) -> Optional[Horse]:
    """
    内部7頭のうち、6頭残留指数が最も低い馬を予備へ回す。

    指数差0.5以内は同点圏として、能力指数が低い馬を先に予備へ回す。
    保護馬しか残らない例外時は、◎以外から最低指数馬を選ぶ。
    """
    if len(full_selected) <= 1:
        return None

    protected_numbers = set_reserve_protection_flags(
        full_selected,
        horses,
    )

    candidates = [
        horse
        for horse in full_selected
        if horse.mark != "◎"
        and horse.number not in protected_numbers
    ]

    # 保護条件が多すぎて候補がなくなった場合も、◎だけは必ず残す。
    if not candidates:
        candidates = [
            horse
            for horse in full_selected
            if horse.mark != "◎"
        ]

    if not candidates:
        return None

    lowest_score = min(
        horse.score.reserve_retention_score
        for horse in candidates
    )

    close_candidates = [
        horse
        for horse in candidates
        if horse.score.reserve_retention_score
        <= lowest_score + RESERVE_RETENTION_TIE_GAP
    ]

    return min(
        close_candidates,
        key=lambda horse: (
            horse.score.ability_index,
            horse.score.reserve_retention_score,
            horse.score.in_money_score,
            horse.score.first_place_score,
            -horse.popularity,
            horse.number,
        ),
    )


def apply_reserve_reselection(
    full_selected: List[Horse],
    horses: Dict[int, Horse],
) -> Tuple[List[Horse], Optional[Horse]]:
    """
    予備を再選定し、残った馬へ表示印を振り直す。

    通常7頭→6頭:
      ◎・○・▲・△・注・穴

    選定外の強い単独軸追加で8頭→7頭:
      ◎・○・▲・△・☆・注・穴
    """
    reserve = choose_reserve_horse(
        full_selected,
        horses,
    )
    if reserve is None:
        return full_selected, None

    first_choice = next(
        (horse for horse in full_selected if horse.mark == "◎"),
        full_selected[0],
    )

    visible_partners = [
        horse
        for horse in full_selected
        if horse.number not in {
            first_choice.number,
            reserve.number,
        }
    ]
    visible_partners.sort(
        key=in_money_order_key,
        reverse=True,
    )

    partner_marks = (
        ("○", "▲", "△", "☆", "注", "穴")
        if len(visible_partners) >= 6
        else ("○", "▲", "△", "注", "穴")
    )

    first_choice.mark = "◎"
    first_choice.comment = build_comment(first_choice)

    for mark, horse in zip(partner_marks, visible_partners):
        horse.mark = mark
        horse.comment = build_comment(horse)

    reserve_score = reserve.score.reserve_retention_score
    reserve.mark = "予備"
    reserve_base_comment = build_comment(reserve)
    reserve.comment = (
        f"6頭残留指数{reserve_score:.1f}で予備"
        + (
            f"・{reserve_base_comment}"
            if reserve_base_comment
            else ""
        )
    )

    visible = [first_choice] + visible_partners
    return visible, reserve


def select_marks_with_reserve(
    horses: Dict[int, Horse],
    upset_mode: bool = False,
) -> Tuple[List[Horse], Optional[Horse]]:
    """
    内部7頭選定は維持し、最後に6頭残留指数で予備を再選定する。

    通常表示:
      ◎・○・▲・△・注・穴 = 6頭
      予備 = 残留指数最下位の非保護馬

    選定外の強い単独軸を追加した例外時:
      ◎＋相手6頭 = 7頭表示
      予備 = 残留指数最下位の非保護馬
    """
    full_selected = select_marks_full(
        horses,
        upset_mode=upset_mode,
    )
    if not full_selected:
        return [], None

    # 荒れモードは境界再判定後の7頭をすべて馬券対象にする。
    if upset_mode:
        set_reserve_protection_flags(
            full_selected,
            horses,
        )
        return full_selected[:7], None

    return apply_reserve_reselection(
        full_selected,
        horses,
    )


def select_marks(
    horses: Dict[int, Horse],
    upset_mode: bool = False,
) -> List[Horse]:
    """互換用。残留指数で選んだ馬券対象6頭（例外時は7頭）を返す。"""
    visible, _ = select_marks_with_reserve(
        horses,
        upset_mode=upset_mode,
    )
    return visible


def axis_candidate_pool(horses: Dict[int, Horse]) -> List[Horse]:
    """人気に制限せず、軸禁止でない全馬を総合軸指数で比較する。"""
    candidates = [
        horse
        for horse in horses.values()
        if not horse.score.axis_banned
    ]

    return sorted(
        candidates,
        key=lambda horse: (
            horse.score.axis_index,
            horse.score.stable_axis_score,
            horse.score.win_axis_score,
            horse.score.avg5_score,
            horse.score.same_condition_score,
        ),
        reverse=True,
    )


def axis_support_count(horse: Horse) -> int:
    """軸を裏付ける独立項目の数を数える。"""
    signals = (
        horse.score.avg5_rank <= 3 or horse.score.avg5_score >= 76,
        horse.score.recent_form >= 70,
        horse.score.same_condition_score >= 68
        and horse.score.same_condition_count >= 2,
        horse.score.stability_score >= 75,
        horse.score.trend_score >= 65,
        horse.score.race_level >= 70,
        horse.score.time_index >= 78,
    )
    return sum(bool(signal) for signal in signals)


def axis_support_ok(horse: Horse) -> bool:
    """
    1項目だけ突出した馬を軸にしない。
    独立した裏付けが3項目以上必要。
    """
    core_support = any((
        horse.score.avg5_rank <= 3,
        horse.score.recent_form >= 70,
        horse.score.same_condition_score >= 68
        and horse.score.same_condition_count >= 2,
        horse.score.stability_score >= 75,
    ))
    return core_support and axis_support_count(horse) >= 3


def single_axis_eligible(candidates: List[Horse]) -> bool:
    if not candidates:
        return False

    first = candidates[0]
    second_score = (
        candidates[1].score.axis_index
        if len(candidates) >= 2
        else first.score.axis_index - 10
    )
    gap = first.score.axis_index - second_score

    return (
        first.score.axis_index >= 82
        and gap >= 4
        and first.score.stability_score >= 75
        and first.score.recent_form >= 70
        and first.score.danger_score < 20
        and first.score.condition_boost < 10
        and axis_support_ok(first)
    )


def pair_axis_eligible(candidates: List[Horse]) -> bool:
    if len(candidates) < 2:
        return False

    first, second = candidates[:2]
    return (
        first.score.axis_index >= 78
        and second.score.axis_index >= 75
        and first.score.danger_score < 35
        and second.score.danger_score < 35
        and first.score.condition_boost < 10
        and second.score.condition_boost < 10
        and axis_support_ok(first)
        and axis_support_ok(second)
    )


def axis_specialists(
    horses: Dict[int, Horse],
) -> Tuple[Optional[Horse], Optional[Horse]]:
    eligible = [
        horse
        for horse in horses.values()
        if not horse.score.axis_banned
    ]
    if not eligible:
        return None, None

    stable_axis = max(
        eligible,
        key=lambda horse: (
            horse.score.stable_axis_score,
            horse.score.axis_index,
        ),
    )
    win_axis = max(
        eligible,
        key=lambda horse: (
            horse.score.win_axis_score,
            horse.score.axis_index,
        ),
    )
    return stable_axis, win_axis


def axis_confidence(horses: Dict[int, Horse]) -> Tuple[str, str, float, List[Horse]]:
    candidates = axis_candidate_pool(horses)
    if not candidates:
        return "★☆☆☆☆", "大混戦", 0.0, []

    first = candidates[0]
    second_score = (
        candidates[1].score.axis_index
        if len(candidates) >= 2
        else max(0.0, first.score.axis_index - 10.0)
    )
    gap = first.score.axis_index - second_score

    if single_axis_eligible(candidates):
        star_count = 5
        difficulty = "本命寄り"
    elif pair_axis_eligible(candidates):
        star_count = 3 if first.score.axis_index >= 80 else 2
        difficulty = "混戦"
    elif first.score.axis_index >= 75:
        star_count = 2
        difficulty = "大混戦"
    else:
        star_count = 1
        difficulty = "大混戦"

    if first.score.danger_score >= 22:
        star_count = min(star_count, 2)

    stars = "★" * star_count + "☆" * (5 - star_count)
    return stars, difficulty, gap, candidates


def axis_guidance(
    candidates: List[Horse],
    difficulty: str,
    stars: str,
) -> Tuple[str, str, Optional[Horse]]:
    """
    絶対基準を満たした場合だけ軸を出す。
    弱い1位を無理に軸候補へしない。
    """
    if not candidates:
        return "軸なし", "単独軸非推奨", None

    if single_axis_eligible(candidates):
        first = candidates[0]
        return f"{first.number}番 {first.name}", "単独軸候補", first

    if pair_axis_eligible(candidates):
        pair = candidates[:2]
        names = "・".join(
            f"{horse.number}番 {horse.name}"
            for horse in pair
        )
        return names, "軸候補2頭", pair[0]

    return "軸なし", "単独軸非推奨", None



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
                "父": horse.sire,
                "人気": "-" if horse.popularity == 99 else horse.popularity,
                "オッズ": "-" if horse.odds <= 0 else horse.odds,
                "推定脚質": horse.running_style,
                "能力順位": horse.score.ability_rank,
                "能力指数": horse.score.ability_index,
                "1着期待順位": horse.score.first_place_rank,
                "1着期待指数": horse.score.first_place_score,
                "僅差判定": (
                    "昇格"
                    if horse.score.first_place_tiebreak_promoted
                    else ""
                ),
                "荒れ境界": (
                    horse.score.upset_boundary_rule
                    if horse.score.upset_boundary_promoted
                    else ""
                ),
                "格補正勝ち切り": horse.score.class_adjusted_win_score,
                "3歳条件替わり": horse.score.young_condition_change_bonus,
                "3歳軽斤量現級": horse.score.young_lightweight_current_class_bonus,
                "3歳休養成長": horse.score.young_layoff_growth_bonus,
                "上級僅差力": horse.score.high_class_close_score,
                "馬券内期待順位": horse.score.in_money_rank,
                "馬券内期待指数": horse.score.in_money_score,
                "6頭残留指数": horse.score.reserve_retention_score,
                "予備保護": horse.score.reserve_protection_reason,
                "直近5走勝率": round(horse.score.recent_win_rate, 1),
                "直近5走連対率": round(horse.score.recent_top2_rate, 1),
                "直近5走複勝率": round(horse.score.recent_top3_rate, 1),
                "近走内容": horse.score.recent_form,
                "レースレベル": horse.score.race_level,
                "条件適性": horse.score.suitability,
                "脚質評価": horse.score.running_style,
                "上がり3F": horse.score.closing_power,
                "タイム指数": horse.score.time_index,
                "5走平均評価": horse.score.avg5_score,
                "5走平均順位": horse.score.avg5_rank,
                "同条件近走": horse.score.same_condition_score,
                "同条件件数": horse.score.same_condition_count,
                "条件上昇幅": horse.score.condition_boost,
                "上昇度": horse.score.trend_score,
                "直近3走ピーク": horse.score.recent_peak_score,
                "安定度": horse.score.stability_score,
                "安定軸指数": horse.score.stable_axis_score,
                "勝負軸指数": horse.score.win_axis_score,
                "軸指数": horse.score.axis_index,
                "軸順位": horse.score.axis_rank,
                "軸タイプ": horse.score.axis_type,
                "軸判定": "軸禁止" if horse.score.axis_banned else "候補可",
                "軽斤量補正": horse.score.weight_bonus,
                "3歳軽斤量現級": horse.score.young_lightweight_current_class_bonus,
                "3歳休養成長": horse.score.young_layoff_growth_bonus,
                "高格勝利補正": horse.score.high_class_win_bonus,
                "印選定指数": horse.score.selection_score,
                "生存指数": horse.score.survival_score,
                "危険度": horse.score.danger_score,
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
                "父": horse.sire,
                "人気": horse.popularity,
                "近走数": len(horse.records),
                "推定脚質": horse.running_style,
                "内部総合": horse.score.total,
                "能力指数": horse.score.ability_index,
                "能力順位": horse.score.ability_rank,
                "1着期待指数": horse.score.first_place_score,
                "1着期待順位": horse.score.first_place_rank,
                "僅差判定": (
                    "昇格"
                    if horse.score.first_place_tiebreak_promoted
                    else ""
                ),
                "荒れ境界": (
                    horse.score.upset_boundary_rule
                    if horse.score.upset_boundary_promoted
                    else (
                        "降格"
                        if horse.score.upset_boundary_demoted
                        else ""
                    )
                ),
                "格補正勝ち切り": horse.score.class_adjusted_win_score,
                "3歳条件替わり": horse.score.young_condition_change_bonus,
                "3歳軽斤量現級": horse.score.young_lightweight_current_class_bonus,
                "3歳休養成長": horse.score.young_layoff_growth_bonus,
                "上級僅差力": horse.score.high_class_close_score,
                "馬券内期待指数": horse.score.in_money_score,
                "馬券内期待順位": horse.score.in_money_rank,
                "6頭残留指数": horse.score.reserve_retention_score,
                "予備保護": horse.score.reserve_protection_reason,
                "直近5走勝率": round(horse.score.recent_win_rate, 1),
                "直近5走連対率": round(horse.score.recent_top2_rate, 1),
                "直近5走複勝率": round(horse.score.recent_top3_rate, 1),
                "率計算対象数": horse.score.recent_rate_count,
                "同条件勝率": round(horse.score.same_condition_win_rate, 1),
                "同条件複勝率": round(horse.score.same_condition_top3_rate, 1),
                "同条件率対象数": horse.score.same_condition_rate_count,
                "直近2走内容": horse.score.last2_form_score,
                "年齢": horse.age,
                "性別": horse.sex,
                "斤量": horse.carried_weight,
                "斤量差": horse.weight_allowance,
                "軽斤量補正": horse.score.weight_bonus,
                "高格勝利補正": horse.score.high_class_win_bonus,
                "馬体増減": horse.weight_change,
                "休養週": horse.layoff_weeks,
                "相手弱化": horse.score.transition_bonus,
                "直近3走ピーク": horse.score.recent_peak_score,
                "5走平均評価": horse.score.avg5_score,
                "5走平均順位": horse.score.avg5_rank,
                "同条件近走": horse.score.same_condition_score,
                "同条件件数": horse.score.same_condition_count,
                "基礎軸指数": horse.score.base_axis_score,
                "条件上昇幅": horse.score.condition_boost,
                "上昇度": horse.score.trend_score,
                "安定度": horse.score.stability_score,
                "安定軸指数": horse.score.stable_axis_score,
                "勝負軸指数": horse.score.win_axis_score,
                "軸指数": horse.score.axis_index,
                "軸順位": horse.score.axis_rank,
                "軸タイプ": horse.score.axis_type,
                "軸禁止": horse.score.axis_banned,
                "軸禁止理由": horse.score.axis_ban_reason,
                "生存指数": horse.score.survival_score,
                "危険度": horse.score.danger_score,
                "選定指数": horse.score.selection_score,
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
    st.session_state["conditions_input"] = ""
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""
    st.session_state["upset_mode"] = False


st.title("🐎 競馬AI Next v0.6.21 予備再選定版")
st.caption(
    "通常6頭＋予備1頭｜馬券内60％・1着25％・能力15％で予備を再選定"
)

conditions_text = st.text_input(
    "レース条件（任意）",
    placeholder="例：名古屋 B級 ダ1500 良　※分かる項目だけでもOK",
    key="conditions_input",
)

upset_mode = st.checkbox(
    "荒れレースモード",
    value=False,
    key="upset_mode",
    help=(
        "ONにすると、通常は原則除外している9番人気以下も"
        "7頭選定の候補に含めます。内部総合差1.5以内では、"
        "期待順位が両方上の馬に加え、馬券内期待が3順位以上上で"
        "1着期待が2順位以内の下までの馬も最大2頭まで救済します。"
    ),
)

if upset_mode:
    st.warning(
        "荒れレースモード適用中：9番人気以下の消しを解除しています。"
        "境界再判定を行い、選定した7頭をすべて馬券対象にします。"
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
    conditions = merge_conditions(conditions_text, racecard_text)
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

    if not has_known_conditions(conditions):
        st.warning(
            "レース条件が読み取れなかったため、競馬場格差補正は使用せず、"
            "条件適性は中立値で判定します。軸精度を上げるには"
            "「中京 ダ1400 良」のようにレース条件を入力してください。"
        )
    elif not conditions.venue:
        st.info(
            "開催場が不明なため、競馬場格差・相手弱化の加点は使用しません。"
        )

    horses = score_horses(
        horses,
        conditions,
        time_mode,
    )

    # 相手7頭は従来条件のまま固定。
    opponent_pool = select_mark_pool(
        horses,
        upset_mode=upset_mode,
    )
    opponent_numbers = {horse.number for horse in opponent_pool}

    # 全頭1着期待1位と軸基準を確認する。
    (
        confidence_stars,
        race_difficulty,
        axis_operation,
        axis_gap,
        first_place_candidates,
        primary_axis,
    ) = first_place_axis_analysis(list(horses.values()))

    first_place_leader = (
        first_place_candidates[0]
        if first_place_candidates
        else None
    )

    # 表示印を作る。内部7頭から6頭残留指数で予備を再選定する。
    selected, reserve_horse = select_marks_with_reserve(
        horses,
        upset_mode=upset_mode,
    )
    displayed_first_choice = next(
        (horse for horse in selected if horse.mark == "◎"),
        None,
    )

    full_leader_is_outside = (
        first_place_leader is not None
        and first_place_leader.number not in opponent_numbers
    )
    leader_added_from_outside = (
        full_leader_is_outside
        and primary_axis is not None
        and any(
            horse.number == first_place_leader.number
            for horse in selected
        )
    )
    outside_leader_not_added = (
        full_leader_is_outside
        and not leader_added_from_outside
    )

    # 相手期待1位は、実際に馬券対象として残った馬から選ぶ。
    partner_candidates = [
        horse
        for horse in selected
        if (
            displayed_first_choice is None
            or horse.number != displayed_first_choice.number
        )
    ]
    partner_candidates.sort(key=in_money_order_key, reverse=True)
    best_partner = partner_candidates[0] if partner_candidates else None

    axis_names = (
        f"{primary_axis.number}番 {primary_axis.name}"
        if primary_axis is not None
        else "軸なし"
    )

    st.divider()

    if upset_mode:
        st.warning(
            "この予想は荒れレースモードです。"
            "9番人気以下も候補に含め、境界再判定後の7頭を"
            "すべて馬券対象として表示しています。"
        )

        promoted_horses = [
            horse
            for horse in horses.values()
            if horse.score.upset_boundary_promoted
        ]
        demoted_horses = [
            horse
            for horse in horses.values()
            if horse.score.upset_boundary_demoted
        ]

        if promoted_horses:
            promoted_text = "、".join(
                f"{horse.number}番 {horse.name}"
                f"（{horse.score.upset_boundary_rule}）"
                for horse in promoted_horses
            )
            demoted_text = "、".join(
                f"{horse.number}番 {horse.name}"
                for horse in demoted_horses
            )
            st.caption(
                f"荒れ境界再判定：昇格 {promoted_text}"
                + (
                    f"／降格 {demoted_text}"
                    if demoted_text
                    else ""
                )
            )

    if selected:
        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        with summary_col1:
            if first_place_leader is None:
                leader_text = "該当なし"
                leader_delta = ""
            else:
                leader_text = (
                    f"{first_place_leader.number}番 "
                    f"{first_place_leader.name}"
                )
                leader_delta = (
                    f"1着期待指数 "
                    f"{first_place_leader.score.first_place_score:.1f}"
                )
            st.metric("全頭1着期待1位", leader_text, leader_delta)

        with summary_col2:
            if best_partner is None:
                partner_text = "該当なし"
                partner_delta = ""
            else:
                partner_text = f"{best_partner.number}番 {best_partner.name}"
                partner_delta = (
                    f"馬券内期待指数 "
                    f"{best_partner.score.in_money_score:.1f}"
                )
            st.metric("相手期待1位", partner_text, partner_delta)

        with summary_col3:
            st.metric(
                "軸信頼度",
                confidence_stars,
                f"1着期待差 {axis_gap:.1f}",
            )

        with summary_col4:
            st.metric("軸運用", axis_operation)

        if primary_axis is not None:
            outside_note = (
                " 従来の相手7頭選定外ですが、軸基準を満たしたため追加しています。"
                if primary_axis.number not in opponent_numbers
                else ""
            )
            st.success(
                f"単独軸候補は{primary_axis.number}番 "
                f"{primary_axis.name}。"
                f"{outside_note}"
                + (
                    " 荒れモードのため、境界再判定後の7頭をすべて表示しています。"
                    if upset_mode
                    else " ○以下は内部7頭から6頭残留指数で選び直した馬券対象です。"
                )
            )
        elif outside_leader_not_added:
            displayed_text = (
                f"{displayed_first_choice.number}番 "
                f"{displayed_first_choice.name}"
                if displayed_first_choice is not None
                else "該当なし"
            )
            st.info(
                "全頭1着期待1位は相手7頭選定外ですが、"
                "単独軸の絶対基準を満たさないため追加していません。"
                f" ◎は相手7頭内の1着期待最上位 "
                f"{displayed_text}です。固定軸推奨ではありません。"
            )
        else:
            st.info(
                "単独軸の絶対基準を満たさないため軸なしです。"
                "◎は相手7頭内にいる全頭1着期待1位ですが、"
                "固定軸推奨ではありません。"
            )




    if upset_mode:
        st.subheader("予想結果（荒れモード7頭）")
        st.caption(
            "人気薄の消しを解除し、内部総合差1.5以内で境界再判定します。"
            "期待順位が両方上の通常昇格に加え、馬券内期待が3順位以上上で"
            "1着期待が2順位以内の下までなら相手特化昇格。最大2頭まで入れ替え、"
            "予備へは落としません。"
        )
    elif leader_added_from_outside:
        st.subheader("予想結果（◎＋相手6頭／予備1頭）")
        st.caption(
            "選定外の強い単独軸を◎として追加した例外表示です。"
            "内部相手7頭を6頭残留指数で再判定し、馬券対象は◎＋相手6頭です。"
        )
    elif outside_leader_not_added:
        st.subheader("予想結果（6頭／予備1頭）")
        st.caption(
            "全頭1着期待1位は軸基準未達のため追加していません。"
            "内部7頭選定は維持し、6頭残留指数が最も低い非保護馬を予備へ回しています。"
            " 指数差1.5以内では3項目の僅差最終判定を適用します。"
        )
    else:
        st.subheader("予想結果（6頭／予備1頭）")
        st.caption(
            "内部7頭選定はこれまでどおり維持し、最後に6頭残留指数で予備を再選定します。"
            "馬券対象は◎・○・▲・△・注・穴の6頭です。"
            " 残留指数は馬券内期待60％・1着期待25％・能力指数15％。"
            "両期待順位が5位以内の馬と軸候補は予備から保護します。"
            " 1着期待指数差1.5以内では、上級僅差力・レースレベル・"
            "5走平均順位の3項目をすべて上回る馬を最終的に優先します。"
        )

    st.dataframe(
        result_dataframe(selected),
        use_container_width=True,
        hide_index=True,
    )

    if reserve_horse is not None:
        with st.expander("予備馬（6頭残留指数で再選定・馬券対象外）", expanded=False):
            st.caption(
                "内部7頭には残していますが、馬券内期待60％・1着期待25％・"
                "能力指数15％の残留指数で予備へ回しています。"
                "◎・軸候補・1着期待と馬券内期待が両方5位以内の馬は保護します。"
            )
            st.dataframe(
                result_dataframe([reserve_horse]),
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
            f"{conditions.going or '不明'} "
            f"{conditions.race_class or 'クラス不明'}"
        )

        st.dataframe(
            diagnostic_dataframe(horses),
            use_container_width=True,
            hide_index=True,
        )
