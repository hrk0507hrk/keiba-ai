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
    page_title="競馬AI Ranking",
    page_icon="🐎",
    layout="wide",
)


# =========================================================
# Config
# =========================================================

MARKS = ("◎", "○", "▲", "△", "☆", "注", "穴", "補")

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


CORE_WEIGHTS = {
    # v0.7.0: 同じ情報の二重評価を避け、5つの独立グループへ整理する。
    "base_ability": 0.25,
    "condition_performance": 0.25,
    "current_form": 0.25,
    "time_index": 0.15,
    "pace_style": 0.10,
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
    # 「3歳」「2歳」限定戦。中央の「3歳以上」は対象外。
    age_limited: bool = False
    finish: int = 99
    finish_known: bool = False
    margin: Optional[float] = None
    passing: str = ""
    last3f: float = 0.0
    race_time_sec: float = 0.0


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
    base_ability_score: float = 50.0
    condition_performance_score: float = 50.0
    same_condition_peak_score: float = 50.0
    current_form_score: float = 50.0
    pace_style_score: float = 50.0
    core_selection_score: float = 50.0
    # Ranking AI v1.0: five independent viewpoints.
    basic_rank_score: float = 50.0
    form_rank_score: float = 50.0
    condition_rank_score: float = 50.0
    speed_rank_score: float = 50.0
    pace_rank_score: float = 50.0
    clock_score: float = 50.0
    clock_data_count: int = 0
    basic_rank: int = 0
    form_rank: int = 0
    condition_rank: int = 0
    speed_rank: int = 0
    pace_rank: int = 0
    ranking_base_points: int = 0
    ranking_gap_bonus: int = 0
    ranking_gap_bonuses: Dict[str, int] = field(default_factory=dict)
    ranking_points: int = 0
    top3_count: int = 0
    top5_count: int = 0
    ai_overall_rank: int = 0
    specialist_label: str = ""
    specialist_type: str = ""
    complement_score: int = 0
    average_rank: float = 0.0
    selection_route: str = ""
    selection_reason: str = ""
    value_gap: int = 0
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
    young_same_course_step_up_bonus: float = 0.0
    special_course_experience_bonus: float = 0.0
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
    first_place_adjustment: float = 0.0
    first_place_rank: int = 0
    first_place_tiebreak_promoted: bool = False
    # v1.0.5 地方クラス補正の診断値。
    local_class_basic_adjustment: float = 0.0
    local_class_condition_adjustment: float = 0.0
    local_mixed_unproven: bool = False
    local_class_note: str = ""
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
        raw_name = match.group(2).strip()

        # netkeiba出走表の「枠番 馬番」行を馬名行として誤認しない。
        if re.fullmatch(r"\d{1,2}", raw_name) or raw_name in {"--", "－", "―"}:
            continue

        name = re.sub(r"[牡牝セ騙]\d+$", "", raw_name).strip()

        if not 1 <= number <= 18:
            continue

        if any(word in name for word in ("人気", "指数", "着", "枠", "斤量", "タイム")):
            continue

        if name:
            return number, name

    return None


def racecard_name_candidate(line: str) -> str:
    """枠番・馬番行の直後から馬名だけを安全に取得する。"""
    if line in {"--", "－", "―", "編集"}:
        return ""
    if re.search(r"20\d{2}[./年]\d{1,2}", line):
        return ""
    if any(word in line for word in ("馬メモ", "レース別馬メモ", "全角", "削除保存", "閉じる")):
        return ""

    # 「ベルガラス」または「ベルガラス 牡5 ...」の先頭語を馬名として扱う。
    match = re.match(r"^([^\s]+)(?:\s+(?:牡|牝|セ|騙)\d{1,2}|$)", line)
    if not match:
        return ""

    name = match.group(1).strip()
    if re.fullmatch(r"[\d.()+-]+", name):
        return ""
    if any(word in name for word in ("人気", "指数", "着", "枠", "斤量", "タイム")):
        return ""
    return name


def parse_racecard(text: str) -> Dict[int, Horse]:
    horses: Dict[int, Horse] = {}
    current: Optional[Horse] = None
    pending_number: Optional[int] = None

    for line in normalize_lines(text):
        # netkeiba形式の独立した「枠番 馬番」行。
        frame_number = re.fullmatch(r"([1-8])\s+([1-9]|1[0-8])", line)
        if frame_number:
            frame = safe_int(frame_number.group(1))
            number = safe_int(frame_number.group(2))
            current = horses.setdefault(number, Horse(number=number, name=f"{number}番"))
            current.frame = frame
            pending_number = number
            continue

        # 枠番・馬番行の後にある「--」を飛ばし、その次の馬名を紐づける。
        if pending_number is not None:
            name = racecard_name_candidate(line)
            if name:
                current = horses[pending_number]
                current.name = name
                pending_number = None
            elif line in {"--", "－", "―", "編集"}:
                continue

        # 「6番 馬名」「6 馬名」など別形式にも対応。
        header = parse_horse_header(line)
        if header:
            number, name = header
            current = horses.setdefault(number, Horse(number=number, name=name))
            current.name = name
            pending_number = None

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


def parse_race_time(line: str) -> float:
    """馬柱中の走破時計を秒へ変換する。明示的な時計形式だけを対象にする。"""
    # 1:34.5 / 0:55.2 など。
    match = re.search(r"(?<!\d)(\d{1,2}):(\d{2}\.\d)(?!\d)", line)
    if match:
        minutes = safe_int(match.group(1), 0)
        seconds = safe_float(match.group(2), 0.0)
        total = minutes * 60 + seconds
        return total if 45.0 <= total <= 300.0 else 0.0

    # 「タイム 55.2」のように明示される短距離形式。
    match = re.search(r"(?:タイム|時計)\s*[:：]?\s*(\d{2,3}\.\d)", line)
    if match:
        total = safe_float(match.group(1), 0.0)
        return total if 45.0 <= total <= 300.0 else 0.0

    return 0.0


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
    # 「3歳以上」は古馬混合なので除外し、年齢限定戦だけを記録する。
    age_limited = bool(re.search(r"(?:2歳|3歳)(?!以上)", joined))

    return date, venue, surface, distance, going, race_class, age_limited


def is_non_start_record(lines: List[str]) -> bool:
    """取消・除外・取止・中止・失格など、正式に完走していないレースを判定する。"""
    if not lines:
        return False

    status_tokens = {
        "取消", "除", "除外", "競走除外", "取", "取止",
        "中", "中止", "競走中止", "失", "失格",
    }
    date_line = normalize_text(lines[0])

    # netkeiba馬柱では「2026.05.05 船橋除」のように日付行末へ付く。
    if re.search(
        r"(?:取消|競走除外|除外|除|取止|取|競走中止|中止|中|失格|失)\s*$",
        date_line,
    ):
        return True

    # 別形式で結果が独立行になる場合にも対応。
    return any(normalize_text(line) in status_tokens for line in lines[1:4])


def record_from_block(lines: List[str]) -> Optional[RaceRecord]:
    if not lines or is_non_start_record(lines):
        return None

    finish, finish_known = parse_finish(lines)
    margin: Optional[float] = None
    passing = ""
    last3f = 0.0
    race_time_sec = 0.0

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

        if not race_time_sec:
            race_time_sec = parse_race_time(line)

    # 着順不明時は通過順位を着順として代用しない。
    # 着差が負なら自身が勝ったことだけは確定できるため1着とする。
    if not finish_known and margin is not None and margin < 0:
        finish = 1
        finish_known = True

    (
        date, venue, surface, distance, going, race_class, age_limited
    ) = parse_record_conditions(lines)

    return RaceRecord(
        date=date,
        venue=venue,
        surface=surface,
        distance=distance,
        going=going,
        race_class=race_class,
        age_limited=age_limited,
        finish=finish,
        finish_known=finish_known,
        margin=margin,
        passing=passing,
        last3f=last3f,
        race_time_sec=race_time_sec,
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



def is_local_class_label(label: str) -> bool:
    """地方のA/B/Cクラス表記かを判定する。"""
    if not label:
        return False
    upper = normalize_text(label).upper()
    return bool(
        re.fullmatch(r"(?:[ABC]\d{1,2}|[ABC]|BC|[ABC]\d{1,2}[ABC]\d{1,2})", upper)
    )


def local_direct_class_evidence(
    horse: Horse,
    conditions: RaceConditions,
) -> Tuple[int, int, int]:
    """
    地方競馬で今回クラスへ直接通用した実績を数える。

    戻り値:
      same_class_close  同クラスで0.5秒差以内
      exact_close       同クラス・同場・同距離・同馬場区分で0.5秒差以内
      upper_close       上位クラスで0.8秒差以内
    """
    if not is_local_class_label(conditions.race_class):
        return 0, 0, 0

    current_level = class_score(conditions.race_class)
    same_class_close = 0
    exact_close = 0
    upper_close = 0

    for record in horse.records[:5]:
        if not record.race_class or record.margin is None:
            continue
        if not is_local_class_label(record.race_class):
            continue

        prior_level = class_score(record.race_class)
        # 「同場・同距離」ボーナスは条件が実際に取得できた場合だけ付与する。
        same_surface = bool(
            conditions.surface
            and record.surface
            and record.surface == conditions.surface
        )
        same_distance = bool(
            conditions.distance
            and record.distance
            and record.distance == conditions.distance
        )
        same_venue = bool(
            conditions.venue
            and record.venue
            and record.venue == conditions.venue
        )

        if abs(prior_level - current_level) < 0.25 and record.margin <= 0.5:
            same_class_close += 1
            if same_surface and same_distance and same_venue:
                exact_close += 1
        elif prior_level > current_level + 0.25 and record.margin <= 0.8:
            upper_close += 1

    return same_class_close, exact_close, upper_close


def has_local_current_class_experience(
    horse: Horse,
    conditions: RaceConditions,
) -> bool:
    """今回と同格以上の地方クラスへ出走した経験があるか。"""
    if not is_local_class_label(conditions.race_class):
        return False
    current_level = class_score(conditions.race_class)
    return any(
        record.race_class
        and is_local_class_label(record.race_class)
        and class_score(record.race_class) >= current_level - 0.25
        for record in horse.records[:5]
    )


def local_class_context_adjustment(
    horse: Horse,
    conditions: RaceConditions,
    mode: str,
    older_mixed: bool,
) -> Tuple[float, float, Optional[float], bool, str]:
    """
    地方競馬のクラス比較を5項目へ補う。

    ・今回と同クラス・同場・同距離での僅差実績を優先
    ・3歳限定戦から古馬B/C級へ初挑戦する馬を過大評価しない
    ・古馬同クラスで既に通用している3歳馬は減点しない
    """
    if mode != "local" or not is_local_class_label(conditions.race_class):
        return 0.0, 0.0, None, False, ""

    same_close, exact_close, upper_close = local_direct_class_evidence(
        horse, conditions
    )

    basic_adjustment = 0.0
    condition_adjustment = 0.0
    notes: List[str] = []

    # 同クラスへ直接通用した実績を、C1勝ち・年齢限定戦より優先する。
    if exact_close >= 1:
        basic_adjustment += 4.0
        condition_adjustment += 6.0
        notes.append("同級同場同距離0.5秒内")
        if exact_close >= 2:
            basic_adjustment += 2.0
            condition_adjustment += 2.0
            notes.append("同条件複数")
    elif same_close >= 1:
        basic_adjustment += 2.5
        condition_adjustment += 3.0
        notes.append("同級0.5秒内")
        if same_close >= 2:
            basic_adjustment += 1.0
            condition_adjustment += 1.5

    if upper_close >= 1:
        basic_adjustment += 3.0
        notes.append("上位級0.8秒内")

    has_age_limited_recent = any(
        record.age_limited for record in horse.records[:3]
    )
    has_current_class = has_local_current_class_experience(horse, conditions)
    unproven_mixed = bool(
        older_mixed
        and horse.age == 3
        and has_age_limited_recent
        and not has_current_class
    )

    condition_cap: Optional[float] = None
    if unproven_mixed:
        # 年齢限定戦の勝利を古馬B/C級へそのまま移さない。
        basic_adjustment -= 6.0
        condition_adjustment -= 6.0
        condition_cap = 72.0
        notes.append("3歳限定→古馬初挑戦")

    return (
        basic_adjustment,
        condition_adjustment,
        condition_cap,
        unproven_mixed,
        "/".join(notes),
    )


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


SPECIAL_COURSE_SURVIVAL_BONUS = 3.0
SPECIAL_COURSE_IN_MONEY_BONUS = 3.0


def calculate_special_course_experience_bonus(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """
    新潟芝1000mの特殊適性を、実戦結果から直接評価する。

    対象:
      ・今回が新潟芝1000m
      ・直近3走以内に同じ新潟芝1000m
      ・3勝クラス以上
      ・着差0.2秒以内

    加点:
      0.0秒差以内 +6
      0.1秒差以内 +5
      0.2秒差以内 +4

    能力指数・総合点・軸指数・1着期待には加えない。
    印選定、生存、馬券内期待、荒れモードの優先昇格だけに使う。
    """
    if not (
        conditions.venue == "新潟"
        and conditions.surface == "芝"
        and conditions.distance == 1000
    ):
        return 0.0

    qualifying_margins: List[float] = []

    for record in horse.records[:3]:
        if not (
            record.venue == "新潟"
            and record.surface == "芝"
            and record.distance == 1000
        ):
            continue

        if class_score(record.race_class) < class_score("3勝"):
            continue

        if record.margin is None or record.margin > 0.2:
            continue

        qualifying_margins.append(record.margin)

    if not qualifying_margins:
        return 0.0

    best_margin = min(qualifying_margins)

    if best_margin <= 0.0:
        return 6.0
    if best_margin <= 0.1:
        return 5.0
    return 4.0


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


YOUNG_SAME_COURSE_STEP_UP_BONUS = 5.0
YOUNG_SAME_COURSE_STEP_UP_FIRST_WEIGHT = 0.60
YOUNG_SAME_COURSE_STEP_UP_SURVIVAL_WEIGHT = 0.40
YOUNG_SAME_COURSE_STEP_UP_IN_MONEY_WEIGHT = 0.40


def calculate_young_same_course_step_up_bonus(
    horse: Horse,
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> float:
    """
    3歳馬が、今回と同一コース・同距離の未勝利戦を快勝し、
    成長を挟んで古馬混合1勝クラスへ昇級する型を救済する。

    対象条件:
      ・3歳
      ・古馬との混合戦
      ・今回が1勝クラス、または出走構成から1勝クラス相当と推定
      ・今回53kg以下
      ・前走が未勝利戦1着
      ・前走と今回の競馬場・芝ダート・距離が完全一致
      ・前走を0.2秒差以上で勝利
      ・休養8～12週
      ・今回の馬体重が前走比+6kg以上

    反映:
      ・印選定 +5
      ・1着期待 +3
      ・生存指数 +2
      ・馬券内期待 +2

    能力指数・内部総合・軸指数には加えない。
    """
    if horse.age != 3:
        return 0.0

    if horse.carried_weight <= 0 or horse.carried_weight > 53.0:
        return 0.0

    if not is_mixed_age_field(horses):
        return 0.0

    if not is_current_one_win_context(horses, conditions):
        return 0.0

    if not (8 <= horse.layoff_weeks <= 12):
        return 0.0

    if horse.weight_change < 6:
        return 0.0

    if not horse.records:
        return 0.0

    latest = horse.records[0]

    if (latest.race_class or "").upper() != "未勝利":
        return 0.0

    if latest.finish != 1:
        return 0.0

    if latest.margin is None or latest.margin > -0.2:
        return 0.0

    # 条件が未入力の時に誤作動させない。
    if not (
        conditions.venue
        and conditions.surface
        and conditions.distance
    ):
        return 0.0

    if latest.venue != conditions.venue:
        return 0.0

    if latest.surface != conditions.surface:
        return 0.0

    if latest.distance != conditions.distance:
        return 0.0

    return YOUNG_SAME_COURSE_STEP_UP_BONUS


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
    """
    v0.7.0のタイム指数。

    5走平均へ寄りすぎず、前走と直近2走を中心にする。
      前走 40％ / 2走前 25％ / 3走前 10％
      5走平均 15％ / 距離 6％ / コース 4％

    中央・地方で同じ考え方を使い、欠損項目は利用可能項目へ再配分する。
    """
    ti = horse.time_index
    return weighted_index_score([
        (ti.last1, 0.40),
        (ti.last2, 0.25),
        (ti.last3, 0.10),
        (ti.avg5, 0.15),
        (ti.distance, 0.06),
        (ti.course, 0.04),
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
    """馬券内期待・安定度・今回条件だけで作る安定軸指数。"""
    return clamp(
        horse.score.in_money_score * 0.45
        + horse.score.stability_score * 0.35
        + horse.score.condition_performance_score * 0.20
        - horse.score.danger_score * 0.10
    )

def calculate_win_axis_score(horse: Horse) -> float:
    """1着期待・基礎能力・直近状態・展開で作る勝負軸指数。"""
    return clamp(
        horse.score.first_place_score * 0.50
        + horse.score.base_ability_score * 0.20
        + horse.score.current_form_score * 0.20
        + horse.score.pace_style_score * 0.10
        - horse.score.danger_score * 0.10
    )

def calculate_base_axis_score(horse: Horse) -> float:
    """今回条件を中立50点に置いた比較用軸指数。"""
    stable_base = (
        horse.score.in_money_score * 0.45
        + horse.score.stability_score * 0.35
        + 50.0 * 0.20
        - horse.score.danger_score * 0.10
    )
    win_score = calculate_win_axis_score(horse)
    return clamp(stable_base * 0.60 + win_score * 0.40)

def calculate_axis_index(horse: Horse) -> float:
    """安定軸60％＋勝負軸40％の総合軸指数。"""
    return clamp(
        horse.score.stable_axis_score * 0.60
        + horse.score.win_axis_score * 0.40
    )

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


def calculate_same_condition_peak_score(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """今回に近い条件での「最も強い1走」を評価する。"""
    if not horse.records or not has_known_conditions(conditions):
        return 50.0

    current_level = (
        class_score(conditions.race_class)
        if conditions.race_class
        else None
    )
    candidates: List[float] = []

    for record in horse.records[:5]:
        if conditions.surface and record.surface and record.surface != conditions.surface:
            continue

        if conditions.distance and record.distance:
            distance_diff = abs(record.distance - conditions.distance)
            if distance_diff > 400:
                continue
        else:
            distance_diff = 9999

        reliability = 0.62
        if conditions.surface and record.surface == conditions.surface:
            reliability += 0.10
        if distance_diff == 0:
            reliability += 0.18
        elif distance_diff <= 200:
            reliability += 0.12
        elif distance_diff <= 400:
            reliability += 0.05
        if conditions.venue and record.venue == conditions.venue:
            reliability += 0.10

        performance = record_performance_score(record)

        if current_level is not None and record.race_class:
            prior_level = class_score(record.race_class)
            if prior_level < current_level:
                gap = current_level - prior_level
                factor = 0.85 if gap <= 8 else 0.65 if gap <= 14 else 0.45
                performance = 50.0 + (performance - 50.0) * factor
            elif prior_level > current_level:
                performance += min(5.0, (prior_level - current_level) * 0.20)

        adjusted = 50.0 + (performance - 50.0) * min(1.0, reliability)
        candidates.append(clamp(adjusted))

    return max(candidates) if candidates else 50.0


def calculate_base_ability_group(horse: Horse) -> float:
    """格・上級僅差・格補正勝利だけで基礎能力を作る。"""
    return clamp(
        horse.score.race_level * 0.45
        + horse.score.high_class_close_score * 0.35
        + horse.score.class_adjusted_win_score * 0.20
    )


def calculate_condition_performance_group(horse: Horse) -> float:
    """今回条件での平均内容・最高内容・純適性をまとめる。"""
    return clamp(
        horse.score.same_condition_score * 0.45
        + horse.score.same_condition_peak_score * 0.35
        + horse.score.suitability * 0.20
    )


def calculate_current_form_group(horse: Horse) -> float:
    """前走・2走前を中心に、上昇度と直近ピークを補助する。"""
    return clamp(
        horse.score.last2_form_score * 0.45
        + horse.score.trend_score * 0.25
        + horse.score.recent_peak_score * 0.15
        + horse.score.recent_form * 0.15
    )


def calculate_pace_style_group(horse: Horse) -> float:
    """脚質と末脚を一つの展開グループへまとめる。"""
    return clamp(
        horse.score.running_style * 0.55
        + horse.score.closing_power * 0.45
    )


def calculate_core_selection_score(horse: Horse) -> float:
    """重複を避けたv0.7.0の選定基本点。"""
    return clamp(
        horse.score.base_ability_score * CORE_WEIGHTS["base_ability"]
        + horse.score.condition_performance_score * CORE_WEIGHTS["condition_performance"]
        + horse.score.current_form_score * CORE_WEIGHTS["current_form"]
        + horse.score.time_index * CORE_WEIGHTS["time_index"]
        + horse.score.pace_style_score * CORE_WEIGHTS["pace_style"]
    )


def calculate_first_place_raw_score(horse: Horse) -> float:
    """v0.7.0の1着期待。選定基本点を中心に、勝ち切り要素だけを足す。"""
    score = (
        horse.score.core_selection_score * 0.35
        + horse.score.class_adjusted_win_score * 0.20
        + horse.score.current_form_score * 0.20
        + horse.score.same_condition_peak_score * 0.15
        + horse.score.pace_style_score * 0.10
        + horse.score.weight_bonus * 0.50
        + horse.score.special_course_experience_bonus * 0.40
        - horse.score.danger_score * 0.15
    )
    return clamp(score)

def calculate_in_money_raw_score(horse: Horse) -> float:
    """v0.7.0の馬券内期待。安定・同条件・直近複勝率へ役割を限定する。"""
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

    # 正の配点は90％。全項目50点なら50点になるよう中立5点を加える。
    score = (
        horse.score.core_selection_score * 0.30
        + horse.score.stability_score * 0.25
        + same_top3_score * 0.20
        + recent_top3_score * 0.15
        + 5.0
        + horse.score.weight_bonus * 0.50
        + (
            2.0
            if horse.score.special_course_experience_bonus > 0
            else 0.0
        )
        - horse.score.danger_score * 0.10
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
    """v0.7.0の生存指数。専用補正の積み上げではなく5グループで判定する。"""
    score = (
        horse.score.current_form_score * 0.35
        + horse.score.condition_performance_score * 0.25
        + horse.score.time_index * 0.20
        + horse.score.base_ability_score * 0.10
        + horse.score.pace_style_score * 0.10
        + horse.score.weight_bonus
        + horse.score.transition_bonus * 0.20
        + (
            SPECIAL_COURSE_SURVIVAL_BONUS
            if horse.score.special_course_experience_bonus > 0
            else 0.0
        )
        - horse.score.danger_score * 0.25
    )
    return clamp(score, 0, 100)

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
    """v0.7.0: 5グループへ整理した採点エンジン。"""
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

    for horse in horses.values():
        horse.score.recent_form = round(score_recent_form(horse), 1)
        horse.score.race_level = round(score_race_level(horse, conditions), 1)
        horse.score.suitability = round(score_suitability(horse, conditions), 1)
        horse.score.running_style = round(score_running_style(horse, front_count), 1)
        horse.score.closing_power = round(closing_scores.get(horse.number, 50.0), 1)
        horse.score.transition_bonus = round(class_relief_bonus(horse, conditions), 1)
        horse.score.age_adjustment = round(age_adjustment(horse), 1)
        horse.score.weight_bonus = round(calculate_weight_bonus(horse), 1)

        # v0.7.0では個別レース型の後付け補正を停止する。
        # 同条件・成長・斤量は5グループの基本採点へ吸収する。
        horse.score.high_class_win_bonus = 0.0
        horse.score.young_condition_change_bonus = 0.0
        horse.score.young_lightweight_current_class_bonus = 0.0
        horse.score.young_layoff_growth_bonus = 0.0
        horse.score.young_same_course_step_up_bonus = 0.0
        horse.score.special_course_experience_bonus = round(
            calculate_special_course_experience_bonus(horse, conditions), 1
        )

        same_score, same_count = score_same_condition_recent(horse, conditions)
        horse.score.same_condition_score = round(same_score, 1)
        horse.score.same_condition_count = same_count
        horse.score.same_condition_peak_score = round(
            calculate_same_condition_peak_score(horse, conditions), 1
        )
        horse.score.trend_score = round(calculate_trend_score(horse), 1)
        horse.score.last2_form_score = round(calculate_last2_form_score(horse), 1)
        horse.score.class_adjusted_win_score = round(
            calculate_class_adjusted_win_score(horse, conditions), 1
        )
        horse.score.high_class_close_score = round(
            calculate_high_class_close_score(horse, conditions), 1
        )

        raw_time_scores[horse.number] = score_time_index(horse, mode)
        raw_peak_scores[horse.number] = recent_peak_score(horse)
        raw_avg5_scores[horse.number] = time_index_to_score(horse.time_index.avg5)

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

        horse.score.base_ability_score = round(calculate_base_ability_group(horse), 1)
        horse.score.condition_performance_score = round(
            calculate_condition_performance_group(horse), 1
        )
        horse.score.current_form_score = round(calculate_current_form_group(horse), 1)
        horse.score.pace_style_score = round(calculate_pace_style_group(horse), 1)
        horse.score.core_selection_score = round(calculate_core_selection_score(horse), 1)
        horse.score.total = horse.score.core_selection_score

    avg5_ranked = sorted(
        horses.values(),
        key=lambda horse: (
            horse.score.avg5_score,
            horse.time_index.avg5 if horse.time_index.avg5 is not None else -999,
        ),
        reverse=True,
    )
    for rank, horse in enumerate(avg5_ranked, start=1):
        horse.score.avg5_rank = rank

    assign_fixed_ability_indices(horses)

    for horse in horses.values():
        horse.score.danger_score = round(calculate_danger_score(horse), 1)
        horse.score.stability_score = round(calculate_stability_score(horse), 1)

    raw_survival_scores = {
        horse.number: calculate_survival_score(horse, conditions)
        for horse in horses.values()
    }
    normalized_survival_scores = blend_survival_scores(raw_survival_scores)

    for horse in horses.values():
        horse.score.survival_score = normalized_survival_scores.get(horse.number, 50.0)
        horse.score.selection_score = round(clamp(
            horse.score.core_selection_score
            + horse.score.weight_bonus
            + horse.score.transition_bonus * 0.20
            + horse.score.special_course_experience_bonus
            - horse.score.danger_score * 0.12,
            0,
            100,
        ), 1)

    # 期待指数を先に作り、その役割に沿って軸指数を算出する。
    assign_expectancy_engine(horses, conditions)
    assign_axis_engine(horses)

    return horses

# =========================================================
# Selection
# =========================================================

def ranking_key(horse: Horse):
    return (
        horse.score.core_selection_score,
        horse.score.base_ability_score,
        horse.score.condition_performance_score,
        horse.score.current_form_score,
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
        horse.score.current_form_score,
        horse.score.condition_performance_score,
        horse.score.survival_score,
        horse.score.base_ability_score,
        -horse.popularity,
    )

def build_comment(horse: Horse) -> str:
    reasons = []

    if horse.score.upset_boundary_promoted:
        if horse.score.upset_boundary_rule == "特殊コース実績昇格":
            reasons.append("特殊コース実績で優先昇格")
        elif horse.score.upset_boundary_rule == "相手特化昇格":
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

    if horse.score.condition_performance_score >= 75:
        reasons.append("今回条件実績を高評価")
    if horse.score.current_form_score >= 75:
        reasons.append("直近状態が上向き")
    if horse.score.base_ability_score >= 75:
        reasons.append("基礎能力が上位")

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

    if horse.score.special_course_experience_bonus >= 6:
        reasons.append("新潟芝1000mで0.0秒差以内")
    elif horse.score.special_course_experience_bonus >= 5:
        reasons.append("新潟芝1000mで0.1秒差以内")
    elif horse.score.special_course_experience_bonus >= 4:
        reasons.append("新潟芝1000mで0.2秒差以内")

    if horse.score.recent_peak_score >= 85:
        reasons.append("直近3走内に高指数")

    if horse.score.high_class_close_score >= 88:
        reasons.append("上位クラスの僅差実績が強い")
    elif horse.score.high_class_close_score >= 78:
        reasons.append("重賞・OP級の僅差実績あり")

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
    return (
        horse.score.core_selection_score,
        horse.score.selection_score,
        horse.score.axis_index,
        horse.score.condition_performance_score,
        horse.score.current_form_score,
        -horse.popularity,
        -horse.number,
    )

UPSET_BOUNDARY_TOTAL_GAP = 1.5
UPSET_BOUNDARY_MAX_REPLACEMENTS = 2
UPSET_PARTNER_IN_MONEY_GAIN = 3
UPSET_PARTNER_FIRST_DEFICIT = 2


def special_course_promotion_key(horse: Horse):
    return (
        horse.score.special_course_experience_bonus,
        horse.score.selection_score,
        horse.score.in_money_score,
        horse.score.core_selection_score,
        -horse.popularity,
        -horse.number,
    )


def special_course_replacement_key(horse: Horse):
    return (
        horse.score.special_course_experience_bonus > 0,
        horse.score.in_money_score,
        horse.score.selection_score,
        horse.score.core_selection_score,
        horse.score.ability_index,
        -horse.popularity,
        -horse.number,
    )


def count_upset_promotions(horses: Dict[int, Horse]) -> int:
    return sum(
        1 for horse in horses.values()
        if horse.score.upset_boundary_promoted
    )


def apply_upset_boundary_rerank(
    base_pool: List[Horse],
    horses: Dict[int, Horse],
    protected_numbers: set,
    max_replacements: int = UPSET_BOUNDARY_MAX_REPLACEMENTS,
    total_gap: float = UPSET_BOUNDARY_TOTAL_GAP,
) -> List[Horse]:
    """
    荒れモードの境界再判定。

    新潟芝1000mの特殊コース実績だけを例外的に優先し、
    それ以外は新しい基本採点・1着期待・馬券内期待の境界比較で判断する。
    """
    for horse in horses.values():
        horse.score.upset_boundary_promoted = False
        horse.score.upset_boundary_demoted = False
        horse.score.upset_boundary_rule = ""

    selected = list(base_pool)
    selected_numbers = {horse.number for horse in selected}
    original_outsiders = [
        horse for horse in horses.values()
        if horse.number not in selected_numbers
    ]
    promoted_numbers = set()

    special_outsiders = sorted(
        [
            horse for horse in original_outsiders
            if horse.score.special_course_experience_bonus > 0
        ],
        key=special_course_promotion_key,
        reverse=True,
    )
    promoted_numbers.update(
        horse.number for horse in selected
        if horse.score.special_course_experience_bonus > 0
    )

    for outsider in special_outsiders:
        if count_upset_promotions(horses) >= max_replacements:
            break
        replaceable = [
            horse for horse in selected
            if horse.number not in protected_numbers
            and horse.number not in promoted_numbers
            and horse.score.special_course_experience_bonus <= 0
        ]
        if not replaceable:
            break
        insider = min(replaceable, key=special_course_replacement_key)
        idx = next(i for i, horse in enumerate(selected) if horse.number == insider.number)
        selected[idx] = outsider
        selected_numbers.remove(insider.number)
        selected_numbers.add(outsider.number)
        promoted_numbers.add(outsider.number)
        outsider.score.upset_boundary_promoted = True
        outsider.score.upset_boundary_rule = "特殊コース実績昇格"
        insider.score.upset_boundary_demoted = True

    remaining = max_replacements - count_upset_promotions(horses)
    for _ in range(max(0, remaining)):
        qualifying_pairs = []
        replaceable = [
            horse for horse in selected
            if horse.number not in protected_numbers
            and horse.number not in promoted_numbers
        ]
        for outsider in original_outsiders:
            if outsider.number in selected_numbers:
                continue
            for insider in replaceable:
                gap = insider.score.core_selection_score - outsider.score.core_selection_score
                if gap > total_gap:
                    continue
                first_gain = insider.score.first_place_rank - outsider.score.first_place_rank
                in_money_gain = insider.score.in_money_rank - outsider.score.in_money_rank
                first_deficit = outsider.score.first_place_rank - insider.score.first_place_rank
                standard = first_gain > 0 and in_money_gain > 0
                partner = (
                    in_money_gain >= UPSET_PARTNER_IN_MONEY_GAIN
                    and first_deficit <= UPSET_PARTNER_FIRST_DEFICIT
                )
                if standard:
                    rule_name, priority = "通常昇格", 2
                elif partner:
                    rule_name, priority = "相手特化昇格", 1
                else:
                    continue
                qualifying_pairs.append((
                    outsider.score.core_selection_score,
                    outsider.score.selection_score,
                    priority,
                    in_money_gain,
                    first_gain,
                    -abs(gap),
                    -outsider.popularity,
                    -outsider.number,
                    rule_name,
                    outsider,
                    insider,
                ))
        if not qualifying_pairs:
            break
        qualifying_pairs.sort(reverse=True, key=lambda row: row[:8])
        rule_name, outsider, insider = qualifying_pairs[0][-3:]
        idx = next(i for i, horse in enumerate(selected) if horse.number == insider.number)
        selected[idx] = outsider
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
        horse.score.current_form_score,
        horse.score.same_condition_peak_score,
        horse.score.base_ability_score,
        horse.score.pace_style_score,
        -horse.popularity,
        -horse.number,
    )

def wins_close_first_place_tiebreak(
    challenger: Horse,
    leader: Horse,
) -> bool:
    """指数差1.5以内で、3つの新グループをすべて上回る馬だけ逆転する。"""
    gap = leader.score.first_place_score - challenger.score.first_place_score
    if gap < 0 or gap > FIRST_PLACE_TIEBREAK_GAP:
        return False
    return (
        challenger.score.base_ability_score > leader.score.base_ability_score
        and challenger.score.condition_performance_score > leader.score.condition_performance_score
        and challenger.score.current_form_score > leader.score.current_form_score
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
        horse.score.stability_score,
        horse.score.condition_performance_score,
        horse.score.core_selection_score,
        horse.score.recent_top3_rate,
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
                "基礎能力": horse.score.base_ability_score,
                "今回条件実績": horse.score.condition_performance_score,
                "同条件最高内容": horse.score.same_condition_peak_score,
                "直近状態": horse.score.current_form_score,
                "展開・脚質": horse.score.pace_style_score,
                "選定基本点": horse.score.core_selection_score,
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
                "特殊コース実績": horse.score.special_course_experience_bonus,
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
                "特殊コース実績": horse.score.special_course_experience_bonus,
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
                "基礎能力": horse.score.base_ability_score,
                "今回条件実績": horse.score.condition_performance_score,
                "同条件最高内容": horse.score.same_condition_peak_score,
                "直近状態": horse.score.current_form_score,
                "展開・脚質": horse.score.pace_style_score,
                "選定基本点": horse.score.core_selection_score,
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
                "特殊コース実績": horse.score.special_course_experience_bonus,
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
# Ranking AI v1.0
# =========================================================

RANKING_SPECS = (
    ("基礎能力", "basic_rank_score", "basic_rank"),
    ("近走状態", "form_rank_score", "form_rank"),
    ("今回条件適性", "condition_rank_score", "condition_rank"),
    ("スピード能力", "speed_rank_score", "speed_rank"),
    ("展開適合", "pace_rank_score", "pace_rank"),
)

RANKING_POINTS = {1: 5, 2: 4, 3: 3, 4: 2, 5: 1}


def weighted_recent_record_score(horse: Horse) -> float:
    """前走40・2走前25・3走前15を中心に現在の状態を測る。"""
    if not horse.records:
        return 40.0

    weights = (0.50, 0.31, 0.19)
    values = []
    used = []
    for index, record in enumerate(horse.records[:3]):
        values.append(record_performance_score(record) * weights[index])
        used.append(weights[index])
    return clamp(sum(values) / sum(used)) if used else 40.0


def growth_context_score(horse: Horse) -> float:
    """成長・休養・馬体変化は近走状態の5％だけに抑える。"""
    score = 50.0
    if horse.age == 3:
        score += 6.0
    elif horse.age == 4:
        score += 3.0

    if 2 <= horse.layoff_weeks <= 8:
        score += 3.0
    elif 9 <= horse.layoff_weeks <= 16 and horse.age <= 4:
        score += 1.5
    elif horse.layoff_weeks >= 26:
        score -= 8.0
    elif horse.layoff_weeks >= 18:
        score -= 4.0

    if horse.weight_change >= 12 and horse.age <= 4:
        score += 4.0
    elif horse.weight_change >= 6 and horse.age <= 4:
        score += 2.0
    elif horse.weight_change <= -12:
        score -= 5.0

    return clamp(score)


def calculate_basic_ranking_score(horse: Horse) -> float:
    """格上実績を重視し、下級条件の勝利だけで上がり過ぎない基礎能力。"""
    recent_top2_score = rate_to_score(
        horse.score.recent_top2_rate,
        baseline=45.0,
        sensitivity=0.75,
    )
    return clamp(
        horse.score.race_level * 0.30
        + horse.score.high_class_close_score * 0.35
        + horse.score.class_adjusted_win_score * 0.20
        + recent_top2_score * 0.10
        + horse.score.stability_score * 0.05
    )


def calculate_form_ranking_score(horse: Horse) -> float:
    """単発好走より継続性を重視し、長期休養明けは50点へ寄せる。"""
    recent_content = weighted_recent_record_score(horse)
    raw = clamp(
        recent_content * 0.60
        + horse.score.trend_score * 0.20
        + horse.score.stability_score * 0.15
        + growth_context_score(horse) * 0.05
    )

    reliability = 1.0
    if len(horse.records) <= 1:
        reliability *= 0.88
    if horse.layoff_weeks >= 28:
        reliability *= 0.72
    elif horse.layoff_weeks >= 20:
        reliability *= 0.82
    elif horse.layoff_weeks >= 14:
        reliability *= 0.92

    return clamp(50.0 + (raw - 50.0) * reliability)

def performance_from_records(records: List[RaceRecord]) -> float:
    """少数実績を消しすぎず、強い1走と平均の両方を残す。"""
    if not records:
        return 50.0
    scores = [record_performance_score(record) for record in records]
    scores.sort(reverse=True)
    best = scores[0]
    mean_top = average(scores[:3], 50.0)
    raw = best * 0.60 + mean_top * 0.40
    reliability = 0.90 if len(scores) == 1 else 0.97 if len(scores) == 2 else 1.0
    return clamp(50.0 + (raw - 50.0) * reliability)


def calculate_condition_components(
    horse: Horse,
    conditions: RaceConditions,
) -> Tuple[float, float, float, float, float]:
    if not horse.records or not has_known_conditions(conditions):
        return 50.0, 50.0, 50.0, 50.0, 50.0

    same_records = []
    distance_records = []
    surface_records = []
    venue_records = []
    going_records = []

    for record in horse.records[:5]:
        same_surface = (
            not conditions.surface
            or not record.surface
            or record.surface == conditions.surface
        )
        distance_diff = (
            abs(record.distance - conditions.distance)
            if conditions.distance and record.distance
            else 9999
        )

        if same_surface and distance_diff <= 200:
            if not conditions.venue or record.venue == conditions.venue:
                same_records.append(record)

        if same_surface and distance_diff <= 400:
            distance_records.append(record)

        if conditions.surface and record.surface == conditions.surface:
            surface_records.append(record)

        if conditions.venue and record.venue == conditions.venue:
            venue_records.append(record)

        if conditions.going and record.going == conditions.going:
            going_records.append(record)

    same_score = performance_from_records(same_records)
    distance_score = performance_from_records(distance_records)
    surface_score = performance_from_records(surface_records)
    venue_score = performance_from_records(venue_records)
    going_score = performance_from_records(going_records)

    return same_score, distance_score, surface_score, venue_score, going_score


def calculate_condition_ranking_score(
    horse: Horse,
    conditions: RaceConditions,
) -> float:
    """今回に近いクラス・距離・競馬場で再現できるかを重視する。"""
    _same, distance, surface, venue, going = calculate_condition_components(
        horse,
        conditions,
    )
    return clamp(
        horse.score.same_condition_score * 0.30
        + horse.score.same_condition_peak_score * 0.25
        + distance * 0.20
        + venue * 0.10
        + surface * 0.10
        + going * 0.05
    )

def clock_group_key(record: RaceRecord) -> Tuple[str, int]:
    if record.distance <= 0:
        return record.surface or "不明", 0
    # 100m単位でまとめ、距離違いの時計を直接比較しない。
    return record.surface or "不明", int(round(record.distance / 100.0) * 100)


def calculate_clock_scores(horses: Dict[int, Horse]) -> Tuple[Dict[int, float], Dict[int, int]]:
    """同じ芝ダート・ほぼ同距離のレース内相対時計。データ不足時は中立。"""
    groups: Dict[Tuple[str, int], List[float]] = {}
    for horse in horses.values():
        for record in horse.records[:5]:
            if record.race_time_sec > 0 and record.distance > 0:
                groups.setdefault(clock_group_key(record), []).append(record.race_time_sec)

    scores: Dict[int, float] = {}
    counts: Dict[int, int] = {}
    recency_weights = (1.00, 0.85, 0.70, 0.55, 0.40)

    for horse in horses.values():
        weighted = []
        used = []
        for index, record in enumerate(horse.records[:5]):
            if record.race_time_sec <= 0 or record.distance <= 0:
                continue
            peers = groups.get(clock_group_key(record), [])
            if len(peers) < 3:
                continue
            median_value = statistics.median(peers)
            scale = max(statistics.pstdev(peers) if len(peers) >= 2 else 1.0, 0.35)
            raw = 65.0 + (median_value - record.race_time_sec) / scale * 10.0
            weight = recency_weights[index]
            weighted.append(clamp(raw, 25.0, 95.0) * weight)
            used.append(weight)
        scores[horse.number] = clamp(sum(weighted) / sum(used)) if used else 50.0
        counts[horse.number] = len(used)

    return scores, counts


def calculate_speed_ranking_score(
    horse: Horse,
    clock_score: float,
    clock_count: int,
) -> float:
    """タイム指数中心。実時計は件数に応じ、直近ピークを補助利用する。"""
    recent_peak = horse.score.recent_peak_score
    if clock_count >= 3:
        return clamp(
            horse.score.time_index * 0.65
            + clock_score * 0.20
            + recent_peak * 0.15
        )
    if clock_count >= 1:
        return clamp(
            horse.score.time_index * 0.75
            + clock_score * 0.10
            + recent_peak * 0.15
        )
    return clamp(
        horse.score.time_index * 0.85
        + recent_peak * 0.15
    )

def pace_scenario(front_count: int) -> str:
    if front_count <= 2:
        return "スロー想定"
    if front_count >= 5:
        return "ハイ想定"
    return "平均想定"


def scenario_style_score(style: str, front_count: int) -> float:
    scenario = pace_scenario(front_count)
    tables = {
        "スロー想定": {"逃げ": 90, "先行": 82, "差し": 58, "追込": 48, "不明": 55},
        "平均想定": {"逃げ": 72, "先行": 78, "差し": 71, "追込": 60, "不明": 58},
        "ハイ想定": {"逃げ": 45, "先行": 63, "差し": 84, "追込": 77, "不明": 60},
    }
    return float(tables[scenario].get(style, 55))


def frame_fit_score(horse: Horse, conditions: RaceConditions) -> float:
    if horse.frame <= 0:
        return 50.0
    score = 50.0
    if conditions.distance and conditions.distance <= 1400:
        if horse.running_style in ("逃げ", "先行") and horse.frame <= 4:
            score += 8.0
        elif horse.running_style == "追込" and horse.frame >= 6:
            score += 3.0
    if conditions.distance and conditions.distance >= 1800:
        if horse.frame <= 4:
            score += 3.0
    return clamp(score)


def average_position_content(horse: Horse) -> float:
    values = [position_content_score(record) for record in horse.records[:5] if record.passing]
    return average(values, 50.0)


def calculate_pace_ranking_score(
    horse: Horse,
    conditions: RaceConditions,
    front_count: int,
) -> float:
    scenario = pace_scenario(front_count)
    style = scenario_style_score(horse.running_style, front_count)
    position = average_position_content(horse)
    closing = horse.score.closing_power
    frame = frame_fit_score(horse, conditions)
    running = horse.score.running_style

    if scenario == "平均想定":
        raw = (
            style * 0.30
            + position * 0.25
            + closing * 0.25
            + frame * 0.10
            + running * 0.10
        )
        # 平均想定は展開予測の確信が弱いため、差を少し縮める。
        return clamp(50.0 + (raw - 50.0) * 0.85)

    # ハイ・スローが明確な場合は脚質適合を強く反映する。
    return clamp(
        style * 0.50
        + position * 0.15
        + closing * 0.20
        + frame * 0.10
        + running * 0.05
    )

def ranking_values(horse: Horse) -> List[Tuple[str, float, int]]:
    return [
        (label, getattr(horse.score, score_field), getattr(horse.score, rank_field))
        for label, score_field, rank_field in RANKING_SPECS
    ]


def gap_bonus_from_lead(lead: float) -> int:
    """項目1位が2位へ付けた点差を、突出度ボーナスへ変換する。"""
    if lead >= 8.0:
        return 3
    if lead >= 5.0:
        return 2
    if lead >= 3.0:
        return 1
    return 0


def assign_five_ranks(horses: Dict[int, Horse]) -> None:
    # 再計算時に前回値を残さない。
    for horse in horses.values():
        horse.score.ranking_gap_bonuses = {}
        horse.score.ranking_gap_bonus = 0
        horse.score.ranking_base_points = 0
        horse.score.top3_count = 0
        horse.score.top5_count = 0
        horse.score.specialist_label = ""
        horse.score.specialist_type = ""
        horse.score.complement_score = 0

    for label, score_field, rank_field in RANKING_SPECS:
        ranked = sorted(
            horses.values(),
            key=lambda horse: (
                getattr(horse.score, score_field),
                -horse.popularity,
                -horse.number,
            ),
            reverse=True,
        )
        for rank, horse in enumerate(ranked, start=1):
            setattr(horse.score, rank_field, rank)

        # 「僅差の1位」と「抜けた1位」を区別する。
        if len(ranked) >= 2:
            lead = (
                getattr(ranked[0].score, score_field)
                - getattr(ranked[1].score, score_field)
            )
            bonus = gap_bonus_from_lead(lead)
            if bonus:
                ranked[0].score.ranking_gap_bonuses[label] = bonus

    for horse in horses.values():
        ranks = [rank for _label, _score, rank in ranking_values(horse)]
        horse.score.ranking_base_points = sum(
            RANKING_POINTS.get(rank, 0) for rank in ranks
        )
        horse.score.ranking_gap_bonus = sum(
            horse.score.ranking_gap_bonuses.values()
        )
        horse.score.ranking_points = (
            horse.score.ranking_base_points
            + horse.score.ranking_gap_bonus
        )
        horse.score.top3_count = sum(rank <= 3 for rank in ranks)
        horse.score.top5_count = sum(rank <= 5 for rank in ranks)
        horse.score.average_rank = round(average(ranks, 99.0), 2)

    overall = sorted(
        horses.values(),
        key=lambda horse: (
            horse.score.ranking_points,
            horse.score.top3_count,
            horse.score.top5_count,
            -horse.score.average_rank,
            horse.score.first_place_score,
            horse.score.in_money_score,
            -horse.popularity,
            -horse.number,
        ),
        reverse=True,
    )
    for rank, horse in enumerate(overall, start=1):
        horse.score.ai_overall_rank = rank
        horse.score.value_gap = (
            horse.popularity - rank
            if horse.popularity != 99
            else 0
        )

def calculate_first_place_adjustment(
    horse: Horse,
    conditions: RaceConditions,
    scenario: str,
) -> float:
    """過去検証で不足した再現性・条件変更・休養・展開を◎専用に補正する。"""
    adjustment = 0.0

    # 同条件で複数回走れている馬を優先。
    if horse.score.same_condition_count >= 3 and horse.score.same_condition_score >= 70:
        adjustment += 3.0
    elif horse.score.same_condition_count >= 2 and horse.score.same_condition_score >= 65:
        adjustment += 2.0
    elif horse.score.same_condition_count >= 1 and horse.score.same_condition_score >= 65:
        adjustment += 1.0

    # 上位クラスでの僅差実績は、下級条件勝ちより強い勝ち切り根拠として扱う。
    if horse.score.high_class_close_score >= 85:
        adjustment += 3.0
    elif horse.score.high_class_close_score >= 75:
        adjustment += 2.0
    elif horse.score.high_class_close_score >= 65:
        adjustment += 1.0

    # 長期休養は能力順位から消さず、◎だけを下げる。
    if horse.layoff_weeks >= 28:
        adjustment -= 5.0
    elif horse.layoff_weeks >= 20:
        adjustment -= 3.0
    elif horse.layoff_weeks >= 14 and horse.age >= 5:
        adjustment -= 1.5

    if horse.records:
        last = horse.records[0]

        # 距離・競馬場を同時に変える馬は、前走の強さを再現しにくい。
        distance_diff = (
            abs(last.distance - conditions.distance)
            if last.distance and conditions.distance
            else 0
        )
        if distance_diff >= 600:
            adjustment -= 3.0
        elif distance_diff >= 400:
            adjustment -= 2.0
        elif distance_diff >= 300:
            adjustment -= 1.0
        if (
            distance_diff >= 300
            and last.venue
            and conditions.venue
            and last.venue != conditions.venue
        ):
            adjustment -= 1.0

        # 昇級初戦は減点。ただし格上好走歴が強ければ軽減する。
        if last.race_class and conditions.race_class:
            class_jump = class_score(conditions.race_class) - class_score(last.race_class)
            class_penalty = 0.0
            if class_jump >= 14:
                class_penalty = 4.0
            elif class_jump >= 8:
                class_penalty = 2.5
            elif class_jump >= 4:
                class_penalty = 1.0

            if horse.score.high_class_close_score >= 85:
                class_penalty = 0.0
            elif horse.score.high_class_close_score >= 75:
                class_penalty *= 0.5
            adjustment -= class_penalty

    # 地方の3歳限定戦から古馬B/C級へ初挑戦する馬は、◎だけ追加で慎重に扱う。
    if horse.score.local_mixed_unproven:
        adjustment -= 2.5

    # 明確な展開では、適合する脚質を◎判定で追加評価する。
    if scenario == "ハイ想定":
        if horse.running_style in ("差し", "追込") and horse.score.pace_rank_score >= 75:
            adjustment += 2.0
        elif horse.running_style == "逃げ" and horse.score.pace_rank_score < 58:
            adjustment -= 2.5
        elif horse.running_style == "先行" and horse.score.pace_rank_score < 62:
            adjustment -= 1.5
    elif scenario == "スロー想定":
        if horse.running_style in ("逃げ", "先行") and horse.score.pace_rank_score >= 75:
            adjustment += 2.0
        elif horse.running_style == "追込" and horse.score.pace_rank_score < 58:
            adjustment -= 2.0

    return clamp(adjustment, -8.0, 8.0)


def assign_ranking_expectancy(
    horses: Dict[int, Horse],
    conditions: RaceConditions,
) -> None:
    front_count = next(iter(horses.values())).front_competitors if horses else 0
    scenario = pace_scenario(front_count)

    for horse in horses.values():
        if scenario == "平均想定":
            raw = (
                horse.score.basic_rank_score * 0.28
                + horse.score.form_rank_score * 0.22
                + horse.score.speed_rank_score * 0.25
                + horse.score.condition_rank_score * 0.18
                + horse.score.pace_rank_score * 0.07
            )
        else:
            raw = (
                horse.score.basic_rank_score * 0.25
                + horse.score.form_rank_score * 0.18
                + horse.score.speed_rank_score * 0.22
                + horse.score.condition_rank_score * 0.20
                + horse.score.pace_rank_score * 0.15
            )

        adjustment = calculate_first_place_adjustment(
            horse,
            conditions,
            scenario,
        )
        horse.score.first_place_adjustment = round(adjustment, 1)
        horse.score.first_place_score = round(clamp(raw + adjustment), 1)

        horse.score.in_money_score = round(clamp(
            horse.score.basic_rank_score * 0.18
            + horse.score.form_rank_score * 0.18
            + horse.score.condition_rank_score * 0.27
            + horse.score.speed_rank_score * 0.17
            + horse.score.pace_rank_score * 0.10
            + horse.score.stability_score * 0.10
        ), 1)

    first_ranked = sorted(
        horses.values(),
        key=lambda h: (h.score.first_place_score, h.score.ranking_points, -h.popularity),
        reverse=True,
    )
    money_ranked = sorted(
        horses.values(),
        key=lambda h: (h.score.in_money_score, h.score.ranking_points, -h.popularity),
        reverse=True,
    )
    for rank, horse in enumerate(first_ranked, 1):
        horse.score.first_place_rank = rank
    for rank, horse in enumerate(money_ranked, 1):
        horse.score.in_money_rank = rank


def ranking_axis_judgement(horses: List[Horse]) -> Tuple[str, str, float, float]:
    """◎候補と、実際に軸として使えるかを分離する。"""
    ranked = sorted(
        horses,
        key=lambda h: (h.score.first_place_score, h.score.ranking_points, -h.popularity),
        reverse=True,
    )
    if not ranked:
        return "軸なし", "見送り", 0.0, 0.0

    first = ranked[0]
    second = ranked[1].score.first_place_score if len(ranked) >= 2 else first.score.first_place_score - 10
    third = ranked[2].score.first_place_score if len(ranked) >= 3 else second - 5
    gap12 = first.score.first_place_score - second
    gap13 = first.score.first_place_score - third

    if (
        first.score.first_place_score >= 72
        and gap12 >= 3.0
        and gap13 >= 4.0
        and first.score.first_place_adjustment > -3.0
    ):
        if first.score.local_mixed_unproven:
            return "B", "古馬同級未経験・最大B", gap12, gap13
        return "A", "単独軸候補", gap12, gap13
    if (
        first.score.first_place_score >= 66
        and gap12 >= 1.8
        and gap13 >= 3.0
        and first.score.first_place_adjustment > -4.0
    ):
        return "B", "軸候補", gap12, gap13
    if first.score.first_place_score < 60 or gap13 <= 2.5:
        return "軸なし", "見送り", gap12, gap13
    return "C", "相手向き", gap12, gap13

def score_horses_ranking_v1(
    horses: Dict[int, Horse],
    conditions: RaceConditions,
    mode: str,
) -> Dict[int, Horse]:
    """五つの独立ランキングを作る新設計。総合点への直接補正は使わない。"""
    for horse in horses.values():
        infer_running_style(horse)

    front_count = sum(
        1 for horse in horses.values()
        if horse.running_style in ("逃げ", "先行")
    )
    assign_weight_allowance(horses)
    closing_scores = score_closing_power_all(horses)
    clock_scores, clock_counts = calculate_clock_scores(horses)

    raw_time: Dict[int, float] = {}
    for horse in horses.values():
        horse.front_competitors = front_count
        horse.score.recent_form = round(score_recent_form(horse), 1)
        horse.score.race_level = round(score_race_level(horse, conditions), 1)
        horse.score.suitability = round(score_suitability(horse, conditions), 1)
        horse.score.running_style = round(score_running_style(horse, front_count), 1)
        horse.score.closing_power = round(closing_scores.get(horse.number, 50.0), 1)
        horse.score.trend_score = round(calculate_trend_score(horse), 1)
        horse.score.stability_score = round(calculate_stability_score(horse), 1)
        horse.score.recent_peak_score = round(recent_peak_score(horse), 1)
        (
            horse.score.same_condition_score,
            horse.score.same_condition_count,
        ) = score_same_condition_recent(horse, conditions)
        horse.score.same_condition_score = round(horse.score.same_condition_score, 1)
        horse.score.same_condition_peak_score = round(
            calculate_same_condition_peak_score(horse, conditions),
            1,
        )
        horse.score.class_adjusted_win_score = round(
            calculate_class_adjusted_win_score(horse, conditions), 1
        )
        horse.score.high_class_close_score = round(
            calculate_high_class_close_score(horse, conditions), 1
        )
        (
            horse.score.recent_win_rate,
            horse.score.recent_top2_rate,
            horse.score.recent_top3_rate,
            horse.score.recent_rate_count,
        ) = recent_finish_rates(horse)
        raw_time[horse.number] = score_time_index(horse, mode)

    normalized_time = blend_field_scores(
        raw_time,
        relative_low=43.0,
        relative_high=91.0,
        absolute_weight=0.72,
    )

    for horse in horses.values():
        horse.score.time_index = round(normalized_time.get(horse.number, 50.0), 1)
        horse.score.clock_score = round(clock_scores.get(horse.number, 50.0), 1)
        horse.score.clock_data_count = clock_counts.get(horse.number, 0)

        basic_score = calculate_basic_ranking_score(horse)
        condition_score = calculate_condition_ranking_score(horse, conditions)
        older_mixed = any(other.age >= 4 for other in horses.values())
        (
            local_basic_adj,
            local_condition_adj,
            local_condition_cap,
            local_mixed_unproven,
            local_class_note,
        ) = local_class_context_adjustment(
            horse, conditions, mode, older_mixed
        )
        horse.score.local_class_basic_adjustment = round(local_basic_adj, 1)
        horse.score.local_class_condition_adjustment = round(local_condition_adj, 1)
        horse.score.local_mixed_unproven = local_mixed_unproven
        horse.score.local_class_note = local_class_note

        basic_score = clamp(basic_score + local_basic_adj)
        condition_score = clamp(condition_score + local_condition_adj)
        if local_condition_cap is not None:
            condition_score = min(condition_score, local_condition_cap)

        horse.score.basic_rank_score = round(basic_score, 1)
        horse.score.form_rank_score = round(calculate_form_ranking_score(horse), 1)
        horse.score.condition_rank_score = round(condition_score, 1)
        horse.score.speed_rank_score = round(
            calculate_speed_ranking_score(
                horse,
                horse.score.clock_score,
                horse.score.clock_data_count,
            ),
            1,
        )
        horse.score.pace_rank_score = round(
            calculate_pace_ranking_score(horse, conditions, front_count), 1
        )

        # 互換表示用。新設計ではこの平均で選定しない。
        horse.score.total = round(average([
            horse.score.basic_rank_score,
            horse.score.form_rank_score,
            horse.score.condition_rank_score,
            horse.score.speed_rank_score,
            horse.score.pace_rank_score,
        ], 50.0), 1)

    assign_ranking_expectancy(horses, conditions)
    assign_five_ranks(horses)
    return horses


def rank_list(horse: Horse) -> List[int]:
    return [rank for _label, _score, rank in ranking_values(horse)]


def overall_selection_order(horse: Horse):
    return (
        horse.score.ranking_points,
        horse.score.top3_count,
        horse.score.top5_count,
        -horse.score.average_rank,
        horse.score.in_money_score,
        horse.score.first_place_score,
        -horse.popularity,
        -horse.number,
    )


def ranking_item_reliable(horse: Horse, label: str) -> bool:
    """突出項目に、最低限の比較データが存在するか確認する。"""
    if label in ("基礎能力", "近走状態", "今回条件適性"):
        return len(horse.records) >= 1
    if label == "スピード能力":
        has_time_index = any(
            value is not None for value in vars(horse.time_index).values()
        )
        return has_time_index or horse.score.clock_data_count > 0
    if label == "展開適合":
        return horse.running_style not in ("", "不明")
    return False


def ranking_item_has_evidence(horse: Horse, label: str) -> bool:
    """5項目の元データ内で、特化順位を支える最低限の裏付けを確認する。"""
    if not ranking_item_reliable(horse, label):
        return False
    if label == "基礎能力":
        return (
            horse.score.race_level >= 50.0
            or horse.score.high_class_close_score >= 50.0
        )
    if label == "近走状態":
        return (
            horse.score.recent_form >= 50.0
            or horse.score.trend_score >= 50.0
        )
    if label == "今回条件適性":
        return (
            horse.score.suitability >= 50.0
            or horse.score.condition_performance_score >= 50.0
        )
    if label == "スピード能力":
        return horse.score.speed_rank_score >= 50.0
    if label == "展開適合":
        return horse.score.pace_rank_score >= 50.0
    return False


def specialist_profiles(horse: Horse, field_size: int) -> List[Dict[str, object]]:
    """強特化型・裏付け特化型として成立する項目を返す。"""
    ranks = rank_list(horse)
    bottom_cut = max(8, int(field_size * 0.75 + 0.999))
    bottom_count = sum(rank >= bottom_cut for rank in ranks)

    profiles: List[Dict[str, object]] = []
    values = ranking_values(horse)
    for label, score, rank in values:
        other_ranks = [other_rank for other_label, _s, other_rank in values if other_label != label]
        second_support = min(other_ranks, default=99)
        gap_bonus = horse.score.ranking_gap_bonuses.get(label, 0)

        # 強特化型：項目1位かつ2位へ3点以上の差、比較データも十分。
        if (
            rank == 1
            and gap_bonus >= 1
            and ranking_item_reliable(horse, label)
        ):
            profiles.append({
                "label": label,
                "type": "強特化",
                "type_priority": 2,
                "rank": rank,
                "score": score,
                "gap_bonus": gap_bonus,
                "second_support": second_support,
            })
            continue

        # 裏付け特化型：項目1～2位＋別項目6位以内＋馬柱/指数の裏付け。
        if (
            rank <= 2
            and second_support <= 6
            and bottom_count < 4
            and ranking_item_has_evidence(horse, label)
        ):
            profiles.append({
                "label": label,
                "type": "裏付け特化",
                "type_priority": 1,
                "rank": rank,
                "score": score,
                "gap_bonus": gap_bonus,
                "second_support": second_support,
            })

    return profiles


def best_specialist_profile(horse: Horse, field_size: int) -> Optional[Dict[str, object]]:
    profiles = specialist_profiles(horse, field_size)
    if not profiles:
        return None
    return max(
        profiles,
        key=lambda p: (
            int(p["type_priority"]),
            int(p["gap_bonus"]),
            -int(p["rank"]),
            -int(p["second_support"]),
            float(p["score"]),
        ),
    )


def specialist_candidate_order(
    horse: Horse,
    profile: Dict[str, object],
):
    return (
        int(profile["type_priority"]),
        int(profile["gap_bonus"]),
        -int(profile["rank"]),
        -int(profile["second_support"]),
        horse.score.ranking_points,
        horse.score.top3_count,
        horse.score.top5_count,
        horse.score.in_money_score,
        horse.score.first_place_score,
        -horse.popularity,
        -horse.number,
    )


def fallback_specialist_order(horse: Horse):
    ranks = sorted(rank_list(horse))
    return (
        -ranks[0],
        -ranks[1],
        horse.score.ranking_points,
        horse.score.top3_count,
        horse.score.top5_count,
        horse.score.in_money_score,
        horse.score.first_place_score,
        -horse.popularity,
        -horse.number,
    )


def ai_rank_complement_points(ai_rank: int) -> int:
    """AI総合1～7位へ7～1点。8位以下は0点。"""
    return max(0, 8 - ai_rank)


def calculate_complement_score(horse: Horse) -> int:
    return (
        ai_rank_complement_points(horse.score.ai_overall_rank)
        + horse.score.top5_count
        + horse.score.top3_count * 2
    )


def complement_order(horse: Horse):
    horse.score.complement_score = calculate_complement_score(horse)
    return (
        horse.score.complement_score,
        -horse.score.condition_rank,
        -horse.score.basic_rank,
        -horse.score.form_rank,
        horse.score.in_money_score,
        horse.score.first_place_score,
        -horse.popularity,
        -horse.number,
    )


def top_ranking_reasons(horse: Horse, limit: int = 2) -> List[str]:
    items = sorted(ranking_values(horse), key=lambda item: (item[2], -item[1]))
    return [f"{label}{rank}位" for label, _score, rank in items[:limit]]


def gap_bonus_reason(horse: Horse) -> str:
    if not horse.score.ranking_gap_bonuses:
        return ""
    return "点差B " + "/".join(
        f"{label}+{bonus}"
        for label, bonus in horse.score.ranking_gap_bonuses.items()
    )

def select_ranking_v1(
    horses: Dict[int, Horse],
    conditions: Optional[RaceConditions] = None,
) -> List[Horse]:
    """有効な5項目1位を保護し、7頭になるまでAI総合上位で補完する。"""
    for horse in horses.values():
        horse.mark = ""
        horse.comment = ""
        horse.score.selection_route = ""
        horse.score.selection_reason = ""
        horse.score.specialist_label = ""
        horse.score.specialist_type = ""
        horse.score.complement_score = calculate_complement_score(horse)

    all_horses = list(horses.values())
    if not all_horses:
        return []

    target_count = min(7, len(all_horses))
    selected: List[Horse] = []
    selected_numbers = set()
    leader_labels: Dict[int, List[str]] = {}

    # 1) 各項目1位を重複なしで保護。
    # 全馬同点・首位同点、または元データ不足の項目は保護対象にしない。
    for label, score_field, _rank_field in RANKING_SPECS:
        ranked = sorted(
            all_horses,
            key=lambda horse: (
                getattr(horse.score, score_field),
                horse.score.ranking_points,
                horse.score.top3_count,
                -horse.popularity,
                -horse.number,
            ),
            reverse=True,
        )
        if not ranked:
            continue

        leader = ranked[0]
        leader_score = float(getattr(leader.score, score_field))
        second_score = (
            float(getattr(ranked[1].score, score_field))
            if len(ranked) >= 2
            else leader_score - 1.0
        )

        # 取得条件が不明な場合、条件適性1位は保護しない。
        if (
            label == "今回条件適性"
            and conditions is not None
            and not has_known_conditions(conditions)
        ):
            continue

        if not ranking_item_reliable(leader, label):
            continue

        # 小数1桁へ丸めた得点が同点なら、人気などで作られた見かけ上の1位を保護しない。
        if len(ranked) >= 2 and abs(leader_score - second_score) < 0.05:
            continue

        leader_labels.setdefault(leader.number, []).append(label)

    # 複数項目1位の馬は1頭として扱う。代表馬同士はAI総合順で並べる。
    protected = sorted(
        (horses[number] for number in leader_labels),
        key=overall_selection_order,
        reverse=True,
    )
    for horse in protected:
        if len(selected) >= target_count:
            break
        horse.score.selection_route = "項目代表"
        horse.score.specialist_label = "/".join(leader_labels[horse.number])
        horse.score.specialist_type = "1位保護"
        selected.append(horse)
        selected_numbers.add(horse.number)

    # 通常は最大5頭だが、将来項目数が増えて7頭を超えた場合はAI総合順で7頭に制限。
    # 2) 残り枠はAI総合順位で補完。
    overall = sorted(all_horses, key=overall_selection_order, reverse=True)
    for horse in overall:
        if len(selected) >= target_count:
            break
        if horse.number in selected_numbers:
            continue
        horse.score.selection_route = "総合補完"
        selected.append(horse)
        selected_numbers.add(horse.number)

    # 選定理由。
    for horse in selected:
        reasons = [horse.score.selection_route]
        if horse.score.selection_route == "項目代表":
            labels = leader_labels.get(horse.number, [])
            reasons.append("/".join(f"{label}1位" for label in labels))
        else:
            reasons.extend([
                f"AI総合{horse.score.ai_overall_rank}位",
                f"ランキング{horse.score.ranking_points}点",
            ])
        reasons.extend(top_ranking_reasons(horse, 2))
        gap_reason = gap_bonus_reason(horse)
        if gap_reason:
            reasons.append(gap_reason)
        if horse.score.local_class_note:
            reasons.append(f"地方補正:{horse.score.local_class_note}")
        horse.score.selection_reason = "・".join(dict.fromkeys(reasons))
        horse.comment = horse.score.selection_reason

    # ◎は1着指数、残る6頭は馬券内指数順。印の「補」は単なる7番手表示。
    first = max(
        selected,
        key=lambda horse: (
            horse.score.first_place_score,
            horse.score.ranking_points,
            -horse.popularity,
        ),
    )
    first.mark = "◎"

    partners = [horse for horse in selected if horse.number != first.number]
    partners.sort(
        key=lambda horse: (
            horse.score.in_money_score,
            horse.score.ranking_points,
            horse.score.top3_count,
            -horse.score.average_rank,
            -horse.popularity,
        ),
        reverse=True,
    )
    for mark, horse in zip(("○", "▲", "△", "☆", "注", "補"), partners):
        horse.mark = mark

    mark_order = {mark: index for index, mark in enumerate(MARKS)}
    return sorted(selected, key=lambda horse: mark_order.get(horse.mark, 99))

def ranking_result_dataframe(selected: List[Horse]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "印": horse.mark,
            "馬番": horse.number,
            "馬名": horse.name,
            "人気": "-" if horse.popularity == 99 else horse.popularity,
            "選定ルート": horse.score.selection_route,
            "ランキング点": horse.score.ranking_points,
            "順位基本点": horse.score.ranking_base_points,
            "点差ボーナス": horse.score.ranking_gap_bonus,
            "上位3項目数": horse.score.top3_count,
            "上位5項目数": horse.score.top5_count,
            "補完スコア": horse.score.complement_score,
            "AI総合順位": horse.score.ai_overall_rank,
            "基礎能力": f"{horse.score.basic_rank_score:.1f}（{horse.score.basic_rank}位）",
            "近走状態": f"{horse.score.form_rank_score:.1f}（{horse.score.form_rank}位）",
            "条件適性": f"{horse.score.condition_rank_score:.1f}（{horse.score.condition_rank}位）",
            "スピード": f"{horse.score.speed_rank_score:.1f}（{horse.score.speed_rank}位）",
            "展開適合": f"{horse.score.pace_rank_score:.1f}（{horse.score.pace_rank}位）",
            "1着期待": horse.score.first_place_score,
            "◎補正": horse.score.first_place_adjustment,
            "馬券内期待": horse.score.in_money_score,
            "評価理由": horse.score.selection_reason,
        }
        for horse in selected
    ])


def ranking_top_dataframe(horses: Dict[int, Horse], score_field: str) -> pd.DataFrame:
    ranked = sorted(
        horses.values(),
        key=lambda horse: (getattr(horse.score, score_field), -horse.popularity),
        reverse=True,
    )[:5]
    return pd.DataFrame([
        {
            "順位": rank,
            "馬番": horse.number,
            "馬名": horse.name,
            "人気": "-" if horse.popularity == 99 else horse.popularity,
            "評価点": getattr(horse.score, score_field),
            "選定": horse.score.selection_route or "選外",
        }
        for rank, horse in enumerate(ranked, 1)
    ])


def ranking_matrix_dataframe(horses: Dict[int, Horse]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "馬番": horse.number,
            "馬名": horse.name,
            "人気": "-" if horse.popularity == 99 else horse.popularity,
            "基礎能力順位": horse.score.basic_rank,
            "近走状態順位": horse.score.form_rank,
            "条件適性順位": horse.score.condition_rank,
            "スピード順位": horse.score.speed_rank,
            "展開順位": horse.score.pace_rank,
            "ランキング点": horse.score.ranking_points,
            "順位基本点": horse.score.ranking_base_points,
            "点差ボーナス": horse.score.ranking_gap_bonus,
            "上位3項目数": horse.score.top3_count,
            "上位5項目数": horse.score.top5_count,
            "補完スコア": horse.score.complement_score,
            "AI総合順位": horse.score.ai_overall_rank,
            "人気差": horse.score.value_gap,
            "選定ルート": horse.score.selection_route or "選外",
        }
        for horse in sorted(horses.values(), key=lambda h: h.score.ai_overall_rank)
    ])


def ranking_diagnostic_dataframe(horses: Dict[int, Horse]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "馬番": horse.number,
            "馬名": horse.name,
            "人気": horse.popularity,
            "基礎能力点": horse.score.basic_rank_score,
            "近走状態点": horse.score.form_rank_score,
            "条件適性点": horse.score.condition_rank_score,
            "スピード点": horse.score.speed_rank_score,
            "展開適合点": horse.score.pace_rank_score,
            "タイム指数点": horse.score.time_index,
            "実時計点": horse.score.clock_score,
            "時計件数": horse.score.clock_data_count,
            "レースレベル": horse.score.race_level,
            "上級僅差力": horse.score.high_class_close_score,
            "格補正勝ち切り": horse.score.class_adjusted_win_score,
            "近走内容": horse.score.recent_form,
            "上昇度": horse.score.trend_score,
            "安定度": horse.score.stability_score,
            "同条件近走": horse.score.same_condition_score,
            "同条件件数": horse.score.same_condition_count,
            "同条件ピーク": horse.score.same_condition_peak_score,
            "地方基礎補正": horse.score.local_class_basic_adjustment,
            "地方条件補正": horse.score.local_class_condition_adjustment,
            "古馬同級未経験": "○" if horse.score.local_mixed_unproven else "",
            "地方補正理由": horse.score.local_class_note,
            "◎補正": horse.score.first_place_adjustment,
            "脚質": horse.running_style,
            "上がり評価": horse.score.closing_power,
            "先行候補数": horse.front_competitors,
        }
        for horse in sorted(horses.values(), key=lambda h: h.number)
    ])



# =========================================================
# UI
# =========================================================

def clear_inputs():
    st.session_state["conditions_input"] = ""
    st.session_state["racecard_input"] = ""
    st.session_state["past_input"] = ""
    st.session_state["timeindex_input"] = ""


st.title("🐎 競馬AI Ranking v1.0.5")
st.caption("基礎能力・近走状態・今回条件適性・スピード能力・展開適合の5ランキング型")
st.caption("有効な5項目1位を重複なしで保護し、7頭になるまでAI総合上位で補完。5項目の採点と◎再現性判定はv1.0.3を維持。")

conditions_text = st.text_input(
    "レース条件（任意）",
    placeholder="例：新潟 1勝 芝1800 良　※分かる項目だけでもOK",
    key="conditions_input",
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
    predict_clicked = st.button("ランキング予想開始", type="primary", use_container_width=True)
with button_col2:
    st.button("クリア", use_container_width=True, on_click=clear_inputs)

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
            "レース条件が不明なため、今回条件適性ランキングは中立寄りになります。"
            "『中京 ダ1400 良 1勝』のように入力すると精度を上げられます。"
        )

    horses = score_horses_ranking_v1(horses, conditions, time_mode)
    selected = select_ranking_v1(horses, conditions)

    first = next((horse for horse in selected if horse.mark == "◎"), None)
    overall_leader = min(horses.values(), key=lambda h: h.score.ai_overall_rank)
    item_representatives = [
        horse for horse in selected if horse.score.selection_route == "項目代表"
    ]
    protected_item_count = sum(
        len([label for label in horse.score.specialist_label.split("/") if label])
        for horse in item_representatives
    )
    scenario = pace_scenario(next(iter(horses.values())).front_competitors) if horses else "不明"
    axis_grade, axis_operation, gap12, gap13 = ranking_axis_judgement(selected)

    st.divider()
    metric1, metric2, metric3, metric4, metric5 = st.columns(5)
    with metric1:
        st.metric(
            "◎ 1着候補",
            f"{first.number}番 {first.name}" if first else "該当なし",
            f"1着期待 {first.score.first_place_score:.1f}" if first else "",
        )
    with metric2:
        st.metric(
            "ランキング総合1位",
            f"{overall_leader.number}番 {overall_leader.name}",
            f"{overall_leader.score.ranking_points}点",
        )
    with metric3:
        st.metric(
            "5項目1位保護",
            f"代表馬 {len(item_representatives)}頭",
            f"有効項目 {protected_item_count}個",
        )
    with metric4:
        st.metric("展開想定", scenario)
    with metric5:
        st.metric(
            "軸判定",
            axis_grade,
            f"{axis_operation}／1-2位差 {gap12:.1f}",
        )

    if axis_grade == "軸なし":
        st.warning(
            f"◎候補は表示しますが、上位が接戦または絶対値不足のため軸は見送り推奨です。"
            f" 1位-3位差 {gap13:.1f}点"
        )
    elif axis_grade == "C":
        st.info(
            f"◎候補は相手向き評価です。単独軸より組み合わせ向き。"
            f" 1位-3位差 {gap13:.1f}点"
        )

    st.subheader("最終選定 7頭")
    st.caption(
        "正常に計算された基礎能力・近走状態・今回条件適性・スピード能力・展開適合の各1位を、"
        "重複なしで先に保護します。残り枠はAI総合上位から補完し、選定された7頭は削らず表示します。"
    )
    st.dataframe(
        ranking_result_dataframe(selected),
        use_container_width=True,
        hide_index=True,
    )

    route_counts = {
        route: sum(h.score.selection_route == route for h in selected)
        for route in ("項目代表", "総合補完")
    }
    st.caption(
        "選定内訳："
        + "／".join(f"{route}{count}頭" for route, count in route_counts.items() if count)
    )

    st.subheader("5ランキング 上位5頭")
    tabs = st.tabs([label for label, _score, _rank in RANKING_SPECS])
    for tab, (label, score_field, _rank_field) in zip(tabs, RANKING_SPECS):
        with tab:
            st.dataframe(
                ranking_top_dataframe(horses, score_field),
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("全頭ランキング比較", expanded=False):
        st.dataframe(
            ranking_matrix_dataframe(horses),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("読み取り・採点詳細", expanded=False):
        st.write(
            f"判定形式：{'中央競馬' if time_mode == 'central' else '地方競馬'}"
        )
        st.write(
            f"対象条件：{conditions.venue or '不明'} "
            f"{conditions.surface or '不明'}{conditions.distance or '不明'} "
            f"{conditions.going or '不明'} {conditions.race_class or 'クラス不明'}"
        )
        clock_count = sum(h.score.clock_data_count for h in horses.values())
        st.write(
            f"比較可能な実時計データ：{clock_count}件。"
            "不足時はスピード能力をタイム指数中心で計算します。"
        )
        st.dataframe(
            ranking_diagnostic_dataframe(horses),
            use_container_width=True,
            hide_index=True,
        )
