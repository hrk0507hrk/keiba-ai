from __future__ import annotations

import calendar
import csv
import io
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


APP_NAME = "競馬AI Fixed Selection v1.1"
LOCAL_TRACKS = {"福島", "新潟", "小倉", "札幌", "函館"}
STEEP_TRACKS = {"中山", "阪神", "中京"}
SUMMER_MONTHS = {6, 7, 8}
WINTER_MONTHS = {12, 1, 2}
JRA_TRACKS = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
ALL_TRACKS = JRA_TRACKS | {"園田", "船橋", "浦和", "佐賀", "金沢", "高知", "大井", "川崎", "門別"}


@dataclass
class RaceInfo:
    race_name: str = ""
    track: str = ""
    surface: str = ""  # 芝 / ダ
    distance: int = 0
    going: str = ""
    class_name: str = ""
    class_rank: int = 0
    is_handicap: bool = False
    field_size: int = 0


@dataclass
class Entry:
    frame: int
    number: int
    name: str
    sex: str
    age: int
    weight: float
    bodyweight: Optional[int]
    body_change: Optional[int]
    odds: Optional[float]
    popularity: int


@dataclass
class PastRace:
    race_date: Optional[date]
    track: str
    finish: Optional[int]
    race_name: str
    class_rank: int
    surface: str
    distance: Optional[int]
    going: str
    margin: Optional[float]
    fourth_corner: Optional[int]


@dataclass
class HorseHistory:
    number: int
    name: str
    style: str
    races: List[PastRace]


# -----------------------------
# Text parsing helpers
# -----------------------------

def clean_md(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("<br>", " ")
    text = text.replace("&#10003", "")
    return re.sub(r"\s+", " ", text).strip()


def split_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_int(text: str) -> Optional[int]:
    m = re.search(r"-?\d+", clean_md(text))
    return int(m.group()) if m else None


def parse_float(text: str) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", clean_md(text))
    return float(m.group()) if m else None


def class_rank_from_text(text: str) -> int:
    t = clean_md(text).upper()
    if "GI" in t or "G1" in t:
        return 8
    if "GII" in t or "G2" in t:
        return 7
    if "GIII" in t or "G3" in t:
        return 6
    if re.search(r"\bL\b", t) or "OP" in t or "オープン" in t:
        return 5
    if "3勝" in t:
        return 4
    if "2勝" in t:
        return 3
    if "1勝" in t:
        return 2
    if "未勝利" in t:
        return 1
    if "新馬" in t:
        return 0
    return -1


def parse_race_info(text: str) -> RaceInfo:
    info = RaceInfo()
    lines = [clean_md(x) for x in text.splitlines() if clean_md(x)]
    if lines:
        first = re.sub(r"^#+\s*", "", lines[0]).strip()
        info.race_name = first

    m = re.search(r"(芝|ダ)(\d{3,4})m", text)
    if m:
        info.surface = m.group(1)
        info.distance = int(m.group(2))

    for tr in JRA_TRACKS:
        if re.search(rf"(?:\d+回\s*)?{tr}(?:\s*\d+日目)?", text):
            info.track = tr
            break

    m = re.search(r"馬場\s*:\s*(良|稍重|稍|重|不良|不)", text)
    if m:
        g = m.group(1)
        info.going = {"稍": "稍重", "不": "不良"}.get(g, g)

    class_candidates = [
        "3歳未勝利", "2歳未勝利", "4歳以上1勝クラス", "3歳以上1勝クラス", "3歳1勝クラス",
        "4歳以上2勝クラス", "3歳以上2勝クラス", "4歳以上3勝クラス", "3歳以上3勝クラス",
        "未勝利", "1勝クラス", "2勝クラス", "3勝クラス", "オープン"
    ]
    for c in class_candidates:
        if c in text:
            info.class_name = c
            break
    if not info.class_name:
        info.class_name = info.race_name
    info.class_rank = class_rank_from_text(info.class_name)
    info.is_handicap = "ハンデ" in text

    m = re.search(r"(\d+)頭", text)
    if m:
        info.field_size = int(m.group(1))
    return info


def parse_entries(text: str) -> List[Entry]:
    """Parse netkeiba entry text.

    Supports both:
    1) Markdown table pasted from ChatGPT/browser source (contains /horse/ links)
    2) Plain text copied directly from the rendered netkeiba page (URLs stripped)
    """
    entries: List[Entry] = []

    # ---- Mode 1: Markdown table ----
    for line in text.splitlines():
        if "/horse/" not in line or not line.lstrip().startswith("|"):
            continue
        raw = split_cells(line)
        horse_idx = next((i for i, c in enumerate(raw) if "/horse/" in c), None)
        if horse_idx is None or horse_idx < 2:
            continue
        try:
            frame = parse_int(raw[0])
            number = parse_int(raw[1])
            name = clean_md(raw[horse_idx])
            sexage = clean_md(raw[horse_idx + 1])
            m_sex = re.search(r"(牡|牝|セ)(\d+)", sexage)
            if not (frame and number and m_sex):
                continue
            sex, age = m_sex.group(1), int(m_sex.group(2))
            weight = parse_float(raw[horse_idx + 2]) or 0.0

            body_raw = clean_md(raw[horse_idx + 5]) if horse_idx + 5 < len(raw) else ""
            m_body = re.search(r"(\d+)(?:kg)?\(([+-]?\d+)\)", body_raw)
            bodyweight = int(m_body.group(1)) if m_body else None
            body_change = int(m_body.group(2)) if m_body else None

            odds = parse_float(raw[horse_idx + 6]) if horse_idx + 6 < len(raw) else None
            popularity = parse_int(raw[horse_idx + 7]) if horse_idx + 7 < len(raw) else None
            if popularity is None:
                tail = [clean_md(c) for c in raw[horse_idx + 6:]]
                for c in tail:
                    if re.fullmatch(r"\d+", c):
                        popularity = int(c)
                        break
            if popularity is None:
                continue

            entries.append(Entry(
                frame=frame, number=number, name=name, sex=sex, age=age,
                weight=weight, bodyweight=bodyweight, body_change=body_change,
                odds=odds, popularity=popularity,
            ))
        except (IndexError, ValueError):
            continue

    # ---- Mode 2: Plain text copied from rendered page ----
    # If Markdown parsing already found enough rows we still run fallback and de-duplicate,
    # because some browsers can produce a mixed format.
    plain = clean_md(text)
    sexage_matches = list(re.finditer(r"(牡|牝|セ)\s*(\d+)", plain))
    last_anchor_end = 0
    for idx, m in enumerate(sexage_matches):
        # Look back to the last frame/horse-number pair before this sex-age token.
        before = plain[max(last_anchor_end, m.start() - 350):m.start()]
        pair_matches = list(re.finditer(r"(?<!\d)([1-8])\s+([1-9]|1[0-9]|2[0-9])(?!\d)", before))
        if not pair_matches:
            continue
        pm = pair_matches[-1]
        frame = int(pm.group(1))
        number = int(pm.group(2))
        if number < 1 or number > 30:
            continue

        between = before[pm.end():].strip()
        # Remove UI/mark tokens, then take the last remaining token as the horse name.
        toks = [t for t in re.split(r"\s+", between) if t]
        junk = {"--", "編集", "消", "保存", "閉じる"}
        toks = [t for t in toks if t not in junk and not re.fullmatch(r"[-◎◯○▲△☆✓✔消]+", t)]
        if not toks:
            continue
        name = toks[-1]
        if name in {"馬メモ", "レース別馬メモ"}:
            continue

        sex, age = m.group(1), int(m.group(2))
        next_start = sexage_matches[idx + 1].start() if idx + 1 < len(sexage_matches) else min(len(plain), m.end() + 500)
        after = plain[m.end():next_start]

        mw = re.search(r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)", after)
        weight = float(mw.group(1)) if mw else 0.0
        mb = re.search(r"(\d{3})(?:kg)?\(([+-]?\d+)\)", after)
        bodyweight = int(mb.group(1)) if mb else None
        body_change = int(mb.group(2)) if mb else None

        odds = None
        popularity = None
        if mb:
            tail = after[mb.end():]
            mop = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s+(?:\(|（)?\s*(\d{1,2})\s*(?:人気)?(?:\)|）)?", tail)
            if mop:
                odds = float(mop.group(1))
                popularity = int(mop.group(2))

        # Another common copy form is: bodyweight  68.5  13
        if popularity is None and mb:
            nums = re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", after[mb.end():mb.end()+120])
            if len(nums) >= 2:
                try:
                    odds = float(nums[0])
                    popularity = int(float(nums[1]))
                except ValueError:
                    pass

        if popularity is None or not (1 <= popularity <= 30):
            continue

        entries.append(Entry(
            frame=frame, number=number, name=name, sex=sex, age=age,
            weight=weight, bodyweight=bodyweight, body_change=body_change,
            odds=odds, popularity=popularity,
        ))
        last_anchor_end = m.end()

    # de-dupe by horse number. Prefer rows with a sensible name/bodyweight/popularity.
    out: Dict[int, Entry] = {}
    for e in entries:
        old = out.get(e.number)
        if old is None:
            out[e.number] = e
        else:
            old_quality = int(bool(old.name)) + int(old.bodyweight is not None) + int(old.popularity > 0)
            new_quality = int(bool(e.name)) + int(e.bodyweight is not None) + int(e.popularity > 0)
            if new_quality > old_quality:
                out[e.number] = e
    return sorted(out.values(), key=lambda x: x.number)

def normalize_going(g: str) -> str:
    return {"稍": "稍重", "不": "不良"}.get(g, g)


def _parse_races_from_segment(segment: str) -> List[PastRace]:
    """Parse past races from one horse segment without relying on Markdown pipes."""
    cleaned = clean_md(segment)
    track_alt = "|".join(sorted(ALL_TRACKS, key=len, reverse=True))
    race_start_re = re.compile(rf"(\d{{4}}\.\d{{2}}\.\d{{2}})\s*({track_alt})\s*(\d{{1,2}})")
    matches = list(race_start_re.finditer(cleaned))
    races: List[PastRace] = []

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        seg = cleaned[m.end():end].strip()
        try:
            race_date = datetime.strptime(m.group(1), "%Y.%m.%d").date()
        except ValueError:
            race_date = None
        track = m.group(2)
        finish = int(m.group(3))

        mc = re.search(r"(芝|ダ|障)\s*(\d{3,4})", seg)
        surface = mc.group(1) if mc else ""
        distance = int(mc.group(2)) if mc else None
        race_name = seg[:mc.start()].strip() if mc else ""
        # Remove obvious table/UI fragments before race name.
        race_name = re.sub(r"^(?:映像を見る\s*)+", "", race_name).strip()

        going = ""
        if mc:
            # Going normally appears shortly after distance/time.
            after_cond = seg[mc.end():mc.end()+80]
            mg = re.search(r"(良|稍重|稍|重|不良|不)", after_cond)
            if mg:
                going = normalize_going(mg.group(1))

        fourth_corner = None
        # Search the whole race segment for a position chain such as 3-4-4-3 or 4-3.
        pos_all = re.findall(r"(?<!\d)(\d{1,2}(?:-\d{1,2}){1,3})(?!\d)", seg)
        if pos_all:
            # The race-position chain is usually the first/only hyphen chain.
            fourth_corner = int(pos_all[0].split("-")[-1])

        margin = None
        parens = re.findall(r"\((-?\d+(?:\.\d+)?)\)", seg)
        if parens:
            vals = [float(x) for x in parens]
            # Winner margin is generally the last parenthesized numeric value.
            plausible = [v for v in vals if -10.0 <= v <= 20.0]
            if plausible:
                margin = plausible[-1]

        races.append(PastRace(
            race_date=race_date, track=track, finish=finish, race_name=race_name,
            class_rank=class_rank_from_text(race_name), surface=surface,
            distance=distance, going=going, margin=margin, fourth_corner=fourth_corner,
        ))
    return races


def parse_horse_histories(text: str, entries: Optional[List[Entry]] = None) -> Dict[int, HorseHistory]:
    """Parse horse histories from Markdown or plain browser copy.

    When entry rows are available, their horse names/bodyweights are used to locate each
    current-horse header. This avoids confusing a horse name mentioned as an opponent in
    another horse's past race with the horse's own row.
    """
    histories: Dict[int, HorseHistory] = {}

    # ---- Mode 1: Markdown rows ----
    for line in text.splitlines():
        if "/horse/" not in line or not line.lstrip().startswith("|"):
            continue
        raw = split_cells(line)
        horse_cells = [i for i, c in enumerate(raw) if "/horse/" in c]
        if not horse_cells:
            continue
        horse_idx = horse_cells[0]
        number = parse_int(raw[1]) if len(raw) > 1 else None
        if number is None:
            continue
        name = clean_md(raw[horse_idx])
        style = ""
        if horse_idx + 4 < len(raw):
            interval = clean_md(raw[horse_idx + 4])
            ms = re.match(r"(逃|先|差|追)", interval)
            if ms:
                style = ms.group(1)
        races = _parse_races_from_segment(line)
        histories[number] = HorseHistory(number=number, name=name, style=style, races=races)

    # ---- Mode 2: Plain text ----
    if entries:
        plain = clean_md(text)
        header_positions: List[Tuple[int, Entry]] = []
        for e in entries:
            candidates = [m.start() for m in re.finditer(re.escape(e.name), plain)]
            best_pos = None
            best_score = -1
            body_token = None
            if e.bodyweight is not None and e.body_change is not None:
                body_token = f"{e.bodyweight}({e.body_change:+d})"
                # netkeiba often writes zero as (0), not (+0)
                if e.body_change == 0:
                    body_token = f"{e.bodyweight}(0)"
            sexage_token = f"{e.sex}{e.age}"
            for pos in candidates:
                window = plain[pos:pos+500]
                score = 0
                if body_token:
                    bw_pat = re.escape(body_token).replace(r"\(", r"(?:kg)?\(")
                    if re.search(bw_pat, window):
                        score += 4
                if sexage_token in window:
                    score += 2
                if e.odds is not None and str(e.odds) in window:
                    score += 1
                if re.search(r"(?:逃|先|差|追)中\d+週", window):
                    score += 2
                if score > best_score:
                    best_score = score
                    best_pos = pos
            if best_pos is not None and best_score >= 2:
                header_positions.append((best_pos, e))

        header_positions.sort(key=lambda x: x[0])
        for i, (pos, e) in enumerate(header_positions):
            end = header_positions[i + 1][0] if i + 1 < len(header_positions) else len(plain)
            segment = plain[pos:end]
            ms = re.search(r"(?:^|\s)(逃|先|差|追)中\d+週", segment[:500])
            style = ms.group(1) if ms else ""
            races = _parse_races_from_segment(segment)
            # Prefer plain parse when it found race rows; otherwise keep Markdown result.
            if races or e.number not in histories:
                histories[e.number] = HorseHistory(number=e.number, name=e.name, style=style, races=races)

    return histories


# -----------------------------
# Rule engine
# -----------------------------

def subtract_months(d: date, months: int) -> date:
    y = d.year
    m = d.month - months
    while m <= 0:
        y -= 1
        m += 12
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def has_six_month_layoff(race_date: date, history: Optional[HorseHistory]) -> bool:
    if not history or not history.races or not history.races[0].race_date:
        return False
    return history.races[0].race_date <= subtract_months(race_date, 6)


def is_first_surface(current_surface: str, history: Optional[HorseHistory]) -> bool:
    if not history or not history.races:
        return False  # 判定不可
    valid_surfaces = [r.surface for r in history.races if r.surface in {"芝", "ダ"}]
    if not valid_surfaces:
        return False
    return current_surface not in valid_surfaces


def has_steep_good_run(history: Optional[HorseHistory]) -> bool:
    if not history or not history.races:
        return True  # 判定不可なので減点しない
    return any(r.track in STEEP_TRACKS and r.finish is not None and r.finish <= 3 for r in history.races)


def previous_race(history: Optional[HorseHistory]) -> Optional[PastRace]:
    return history.races[0] if history and history.races else None


def axis_score(
    entry: Entry,
    history: Optional[HorseHistory],
    race: RaceInfo,
    race_date: date,
    top_weight: Optional[float],
) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    prev = previous_race(history)

    if is_first_surface(race.surface, history):
        score -= 5
        reasons.append(f"初{race.surface} -5")

    if race.surface == "ダ" and prev and "牝" in prev.race_name:
        score -= 5
        reasons.append("ダートで前走牝馬限定戦 -5")

    if prev and prev.going in {"重", "不良"}:
        score -= 4
        reasons.append(f"前走{prev.going} -4")

    if prev and prev.track in LOCAL_TRACKS:
        score -= 4
        reasons.append(f"前走{prev.track} -4")

    if has_six_month_layoff(race_date, history):
        score -= 3
        reasons.append("6か月以上休養 -3")

    if race.surface == "芝" and entry.number >= 14:
        score -= 3
        reasons.append("芝14番以降 -3")

    if race.surface == "ダ" and entry.frame in {1, 2}:
        score -= 3
        reasons.append(f"ダート{entry.frame}枠 -3")

    if race.is_handicap and top_weight is not None and abs(entry.weight - top_weight) < 1e-9:
        score -= 3
        reasons.append("ハンデ戦トップハンデ -3")

    if not has_steep_good_run(history):
        score -= 2
        reasons.append("急坂好走なし -2")

    if entry.body_change is not None and abs(entry.body_change) >= 15:
        score -= 2
        reasons.append(f"馬体重{entry.body_change:+d}kg -2")

    if prev and prev.distance and race.distance and race.distance > prev.distance:
        score -= 1
        reasons.append(f"距離延長 {prev.distance}→{race.distance}m -1")

    if race_date.month in WINTER_MONTHS and entry.sex == "牝":
        score -= 1
        reasons.append("冬牝 -1")
    elif race_date.month in SUMMER_MONTHS and entry.sex == "牡":
        score -= 1
        reasons.append("夏牡 -1")

    return score, reasons


def unfavorable_draw(entry: Entry, race: RaceInfo) -> bool:
    if race.surface == "芝":
        return entry.number >= 14
    if race.surface == "ダ":
        return entry.frame in {1, 2}
    return False


def opponent_score(
    entry: Entry,
    history: Optional[HorseHistory],
    race: RaceInfo,
    race_date: date,
) -> Tuple[int, List[str]]:
    score = 0
    reasons: List[str] = []
    races = history.races if history else []
    prev = races[0] if races else None

    if prev and prev.margin is not None and prev.margin <= 0.5:
        score += 5
        reasons.append("前走0.5秒差以内 +5")

    if any(r.surface == race.surface and r.finish is not None and r.finish <= 3 for r in races):
        score += 4
        reasons.append("同芝/ダート3着以内 +4")

    if race.class_rank >= 0 and any(
        r.finish is not None and r.finish <= 3 and r.class_rank >= race.class_rank
        for r in races if r.class_rank >= 0
    ):
        score += 4
        reasons.append("現級以上3着以内 +4")

    if sum(1 for r in races[:3] if r.finish is not None and r.finish <= 3) >= 2:
        score += 3
        reasons.append("近3走3着以内2回以上 +3")

    if race.distance and any(
        r.finish is not None and r.finish <= 3 and r.distance is not None and abs(r.distance - race.distance) <= 200
        for r in races
    ):
        score += 3
        reasons.append("±200m距離で3着以内 +3")

    if prev and prev.fourth_corner is not None and prev.fourth_corner <= 3:
        score += 3
        reasons.append("前走4角3番手以内 +3")

    if history and history.style in {"逃", "先"}:
        score += 2
        reasons.append(f"{history.style}行型 +2")

    if is_first_surface(race.surface, history):
        score -= 2
        reasons.append(f"初{race.surface} -2")

    if has_six_month_layoff(race_date, history):
        score -= 2
        reasons.append("6か月以上休養 -2")

    if unfavorable_draw(entry, race):
        score -= 1
        reasons.append("不利枠 -1")

    if entry.body_change is not None and abs(entry.body_change) >= 15:
        score -= 1
        reasons.append(f"馬体重{entry.body_change:+d}kg -1")

    return score, reasons


def build_prediction(
    race: RaceInfo,
    entries: List[Entry],
    histories: Dict[int, HorseHistory],
    race_date: date,
) -> Dict:
    if len(entries) < 3:
        raise ValueError("出馬表から3頭以上を読み取れませんでした。")

    by_pop = sorted(entries, key=lambda e: (e.popularity, e.number))
    top3 = [e for e in by_pop if e.popularity <= 3]
    if len(top3) < 3:
        top3 = by_pop[:3]

    top_weight = max((e.weight for e in entries), default=None) if race.is_handicap else None

    axis_rows = []
    for e in top3:
        s, reasons = axis_score(e, histories.get(e.number), race, race_date, top_weight)
        axis_rows.append({
            "人気": e.popularity,
            "馬番": e.number,
            "馬名": e.name,
            "減点": s,
            "内訳": "、".join(reasons) if reasons else "減点なし",
        })

    axis_rows.sort(key=lambda r: (-r["減点"], r["人気"]))  # 0 > -1 > -5, tie by popularity
    axis = axis_rows[0]
    axis_number = axis["馬番"]

    opp_rows = []
    for e in by_pop:
        s, reasons = opponent_score(e, histories.get(e.number), race, race_date)
        opp_rows.append({
            "人気": e.popularity,
            "馬番": e.number,
            "馬名": e.name,
            "相手C": s,
            "内訳": "、".join(reasons) if reasons else "加減点なし",
            "軸": e.number == axis_number,
        })

    def pick_band(min_pop: int, max_pop: Optional[int], count: int) -> List[Dict]:
        candidates = [
            r for r in opp_rows
            if not r["軸"] and r["人気"] >= min_pop and (max_pop is None or r["人気"] <= max_pop)
        ]
        candidates.sort(key=lambda r: (-r["相手C"], r["人気"], r["馬番"]))
        return candidates[:count]

    band_1_5 = pick_band(1, 5, 3)
    band_6_9 = pick_band(6, 9, 2)
    band_10p = pick_band(10, None, 1)
    opponents = band_1_5 + band_6_9 + band_10p

    return {
        "race": asdict(race),
        "race_date": race_date.isoformat(),
        "axis": axis,
        "axis_table": sorted(axis_rows, key=lambda r: r["人気"]),
        "opponent_table": opp_rows,
        "band_1_5": band_1_5,
        "band_6_9": band_6_9,
        "band_10p": band_10p,
        "opponents": opponents,
        "entries": [asdict(e) for e in entries],
    }


# -----------------------------
# Result verification
# -----------------------------

def parse_result(text: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"\d+", text)]
    return nums[:3]


def verify_result(pred: Dict, result_text: str) -> Dict:
    result = parse_result(result_text)
    if len(result) != 3:
        raise ValueError("結果は「15-7-4」のように1〜3着の馬番を3頭入力してください。")

    axis_num = int(pred["axis"]["馬番"])
    opp_nums = {int(x["馬番"]) for x in pred["opponents"]}
    entries = {int(x["number"]): x["name"] for x in pred["entries"]}

    axis_finish = result.index(axis_num) + 1 if axis_num in result else None
    opponent_hits = [n for n in result if n in opp_nums]
    missed = [n for n in result if n != axis_num and n not in opp_nums]
    capture = sum(1 for n in result if n == axis_num or n in opp_nums)

    return {
        "日付": pred["race_date"],
        "レース": pred["race"].get("race_name", ""),
        "競馬場": pred["race"].get("track", ""),
        "条件": f"{pred['race'].get('surface','')}{pred['race'].get('distance',0)}m",
        "結果": "-".join(map(str, result)),
        "軸馬番": axis_num,
        "軸馬": pred["axis"]["馬名"],
        "軸着順": axis_finish if axis_finish is not None else "圏外",
        "軸3着内": "○" if axis_finish is not None else "×",
        "軸1着": "○" if axis_finish == 1 else "×",
        "相手的中": "・".join(f"{n}{entries.get(n, '')}" for n in opponent_hits) if opponent_hits else "なし",
        "未選出馬券内": "・".join(f"{n}{entries.get(n, '')}" for n in missed) if missed else "なし",
        "捕捉": f"{capture}/3",
        "完全捕捉": "○" if capture == 3 else "×",
    }


# -----------------------------
# UI
# -----------------------------

st.set_page_config(page_title=APP_NAME, page_icon="🏇", layout="wide")
st.title("🏇 競馬AI Fixed Selection v1.1")
st.caption("完全固定版 v3.0 × 相手C改良版＋人気帯3-2-1｜予想時点で選定をロック")

if "locked_prediction" not in st.session_state:
    st.session_state.locked_prediction = None
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.subheader("固定ルール")
    st.markdown(
        """
**軸**  
1〜3人気限定 → 減点最少 → 同点は人気上位

**相手**  
1〜5人気：3頭（軸除外）  
6〜9人気：2頭  
10人気以下：1頭  
同点は人気上位

**重要**  
結果入力時は予想を再計算しません。
        """
    )
    with st.expander("判定定義"):
        st.write("急坂：中山・阪神・中京／3着以内を好走")
        st.write("夏牡：6〜8月の牡馬／冬牝：12〜2月の牝馬")
        st.write("相手C不利枠：芝14番以降、ダート1・2枠")
        st.write("判定できない項目は加減点なし")

pred_tab, hist_tab, rule_tab = st.tabs(["予想・結果検証", "検証履歴", "ルール全文"])

with pred_tab:
    st.subheader("① 入力")
    race_date = st.date_input("レース日", value=date.today())

    c1, c2, c3 = st.columns(3)
    with c1:
        race_text = st.text_area("レース情報", height=220, placeholder="# 3歳未勝利\n18:30発走 / 芝1400m ...")
    with c2:
        entry_text = st.text_area("出馬表", height=220, placeholder="netkeibaの出馬表をそのまま貼り付け")
    with c3:
        history_text = st.text_area("馬柱", height=220, placeholder="全馬の馬柱をそのまま貼り付け")

    b1, b2 = st.columns([1, 1])
    with b1:
        predict_clicked = st.button("予想する（この時点でロック）", type="primary", use_container_width=True)
    with b2:
        clear_clicked = st.button("ロック解除 / クリア", use_container_width=True)

    if clear_clicked:
        st.session_state.locked_prediction = None
        st.rerun()

    if predict_clicked:
        race = parse_race_info(race_text)
        entries = parse_entries(entry_text)
        histories = parse_horse_histories(history_text, entries)

        st.caption(f"解析結果：出馬表 {len(entries)}頭 / 馬柱 {len(histories)}頭")

        problems = []
        if not race.surface or not race.distance:
            problems.append("レース情報から芝/ダート・距離を取得できませんでした。")
        if not race.track:
            problems.append("競馬場を取得できませんでした。")
        if len(entries) < 3:
            problems.append("出馬表から十分な頭数を取得できませんでした。")
        if race.field_size and len(entries) != race.field_size:
            problems.append(f"頭数不一致：レース情報 {race.field_size}頭 / 出馬表解析 {len(entries)}頭")
        if len(histories) < min(len(entries), 3):
            problems.append(f"馬柱の解析頭数が少ないです（{len(histories)}頭）。")

        if problems:
            st.error("\n".join(problems))
        else:
            try:
                pred = build_prediction(race, entries, histories, race_date)
                st.session_state.locked_prediction = pred
                st.success("予想をロックしました。結果入力時もこの選定を使います。")
            except Exception as e:
                st.error(f"予想計算エラー: {e}")

    pred = st.session_state.locked_prediction
    if pred:
        st.divider()
        st.subheader("② ロック済み予想")
        axis = pred["axis"]
        st.success(f"◎ 軸：{axis['馬番']} {axis['馬名']}　【減点 {axis['減点']}】")

        st.markdown("**軸候補 1〜3人気**")
        st.dataframe(pd.DataFrame(pred["axis_table"]), use_container_width=True, hide_index=True)

        st.markdown("**相手C 全馬採点**")
        opp_df = pd.DataFrame(pred["opponent_table"])
        opp_df["備考"] = opp_df["軸"].map(lambda x: "※軸なので除外" if x else "")
        st.dataframe(
            opp_df[["人気", "馬番", "馬名", "相手C", "内訳", "備考"]],
            use_container_width=True,
            hide_index=True,
        )

        a, b, c = st.columns(3)
        with a:
            st.markdown("**1〜5人気：3頭**")
            for r in pred["band_1_5"]:
                st.write(f"{r['馬番']} {r['馬名']}（{r['相手C']}点）")
        with b:
            st.markdown("**6〜9人気：2頭**")
            for r in pred["band_6_9"]:
                st.write(f"{r['馬番']} {r['馬名']}（{r['相手C']}点）")
        with c:
            st.markdown("**10人気以下：1頭**")
            if pred["band_10p"]:
                for r in pred["band_10p"]:
                    st.write(f"{r['馬番']} {r['馬名']}（{r['相手C']}点）")
            else:
                st.write("対象馬なし")

        opponent_numbers = "・".join(str(x["馬番"]) for x in pred["opponents"])
        st.info(f"最終選定：◎{axis['馬番']} ／ 相手 {opponent_numbers}")

        st.divider()
        st.subheader("③ 結果検証")
        result_text = st.text_input("1〜3着の馬番", placeholder="例：15-7-4")
        if st.button("結果を照合して履歴に保存", use_container_width=True):
            try:
                record = verify_result(pred, result_text)
                st.session_state.history.append(record)
                st.success(
                    f"結果 {record['結果']}｜軸3着内 {record['軸3着内']}｜"
                    f"捕捉 {record['捕捉']}｜未選出 {record['未選出馬券内']}"
                )
            except Exception as e:
                st.error(str(e))

with hist_tab:
    st.subheader("検証履歴")

    uploaded = st.file_uploader("過去の検証CSVを読み込む（任意）", type=["csv"])
    if uploaded is not None:
        try:
            df_import = pd.read_csv(uploaded)
            if st.button("このCSVを履歴に読み込む"):
                st.session_state.history = df_import.fillna("").to_dict("records")
                st.success("履歴を読み込みました。")
                st.rerun()
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")

    if st.session_state.history:
        hdf = pd.DataFrame(st.session_state.history)
        st.dataframe(hdf, use_container_width=True, hide_index=True)

        total = len(hdf)
        axis_top3 = int((hdf["軸3着内"] == "○").sum())
        axis_win = int((hdf["軸1着"] == "○").sum())
        full = int((hdf["完全捕捉"] == "○").sum())
        capture_sum = sum(int(str(x).split("/")[0]) for x in hdf["捕捉"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("検証数", f"{total}R")
        m2.metric("軸3着内", f"{axis_top3}/{total}")
        m3.metric("軸1着", f"{axis_win}/{total}")
        m4.metric("完全捕捉", f"{full}/{total}")
        st.metric("馬券内捕捉", f"{capture_sum}/{total * 3}頭")

        csv_bytes = hdf.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "検証履歴CSVをダウンロード",
            data=csv_bytes,
            file_name="keiba_fixed_validation_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if st.button("履歴を全削除"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("まだ検証履歴はありません。")

with rule_tab:
    st.subheader("完全固定版 v3.0")
    st.markdown(
        """
### 軸選定
候補は**1〜3人気のみ**。減点が最も少ない馬を軸。同点は人気上位。判定不可は減点なし。

- −5：初ダート / 初芝
- −5：ダート戦で前走が牝馬限定戦
- −4：前走が重 / 不良（稍重は対象外）
- −4：前走JRAローカル（福島・新潟・小倉・札幌・函館）
- −3：6か月以上休養
- −3：芝14番以降
- −3：ダート1枠 / 2枠
- −3：ハンデ戦トップハンデ
- −2：急坂好走なし
- −2：馬体重±15kg以上
- −1：距離延長
- −1：冬牝 / 夏牡（セン馬は夏牡対象外）
- 0：昇級初戦 / 右左回り好走なし / 前走逃げ好走

### 相手C改良版
- +5：前走0.5秒差以内
- +4：同芝/ダートで3着以内
- +4：現級以上で3着以内
- +3：近3走で3着以内2回以上
- +3：現在距離±200mで3着以内
- +3：前走4角3番手以内
- +2：逃げ・先行
- −2：初芝 / 初ダート
- −2：6か月以上休養
- −1：不利枠
- −1：馬体重±15kg以上
- 前走重 / 不良：相手Cでは減点なし

### 人気帯
- 1〜5人気：3頭（軸除外）
- 6〜9人気：2頭
- 10人気以下：1頭
- 同点：人気上位
        """
    )
