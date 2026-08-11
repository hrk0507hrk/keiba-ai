from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


APP_NAME = "競馬AI 時計選定 v2.0"
LOCAL_TRACKS = {"福島", "新潟", "小倉", "札幌", "函館"}
STEEP_TRACKS = {"中山", "阪神", "中京"}
WINTER_MONTHS = {12, 1, 2}
# 現行検証ルールに合わせ、夏牡は8月のみ。
SUMMER_MONTHS = {8}
JRA_TRACKS = {"札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"}
NAR_TRACKS = {"盛岡", "水沢", "浦和", "船橋", "大井", "川崎", "金沢", "笠松", "名古屋", "園田", "姫路", "高知", "佐賀", "門別"}
ALL_TRACKS = JRA_TRACKS | NAR_TRACKS


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
    time_seconds: Optional[float]
    final3f: Optional[float]
    fourth_corner: Optional[int]


@dataclass
class HorseHistory:
    number: int
    name: str
    style: str
    races: List[PastRace]


# ============================================================
# Text parsing
# ============================================================

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


def parse_time_seconds(text: str) -> Optional[float]:
    """1:27.3 / 59.8 / 0:58.1 などを秒へ。"""
    t = clean_md(text)
    m = re.search(r"(?<!\d)(\d+):(\d{2})\.(\d)(?!\d)", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10
    m = re.search(r"(?<!\d)(\d{2})\.(\d)(?!\d)", t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 10
    return None


def format_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    if minutes > 0:
        return f"{minutes}:{sec:04.1f}"
    return f"{sec:.1f}"


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


def normalize_going(g: str) -> str:
    return {"稍": "稍重", "不": "不良"}.get(g, g)


def parse_race_info(text: str) -> RaceInfo:
    info = RaceInfo()
    lines = [clean_md(x) for x in text.splitlines() if clean_md(x)]
    if lines:
        info.race_name = re.sub(r"^#+\s*", "", lines[0]).strip()

    m = re.search(r"(芝|ダ)(\d{3,4})m", text)
    if m:
        info.surface = m.group(1)
        info.distance = int(m.group(2))

    for tr in ALL_TRACKS:
        if re.search(rf"(?:\d+回\s*)?{tr}(?:\s*\d+日目)?", text):
            info.track = tr
            break

    m = re.search(r"馬場\s*:\s*(良|稍重|稍|重|不良|不)", text)
    if m:
        info.going = normalize_going(m.group(1))

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


def _reconcile_popularity_with_odds(entries: List[Entry]) -> Tuple[List[Entry], bool]:
    """人気は時計順位には使わないが、出馬表解析確認用に整合だけ取る。"""
    if len(entries) < 2:
        return entries, False
    valid = [e for e in entries if e.odds is not None and e.odds > 0]
    if len(valid) < max(2, int(len(entries) * 0.8)):
        return entries, False

    pops = [e.popularity for e in entries]
    invalid_shape = len(set(pops)) != len(pops) or any(p < 1 or p > len(entries) for p in pops)
    contradiction = False
    for i, a in enumerate(valid):
        for b in valid[i + 1:]:
            if a.odds is None or b.odds is None or abs(a.odds - b.odds) < 1e-9:
                continue
            if a.odds < b.odds and not (a.popularity < b.popularity):
                contradiction = True
                break
            if b.odds < a.odds and not (b.popularity < a.popularity):
                contradiction = True
                break
        if contradiction:
            break
    if not (invalid_shape or contradiction):
        return entries, False

    ranked = sorted(entries, key=lambda e: (
        float("inf") if e.odds is None else e.odds,
        e.popularity if 1 <= e.popularity <= len(entries) else 999,
        e.number,
    ))
    rank_by_num = {e.number: i + 1 for i, e in enumerate(ranked)}
    repaired = [
        Entry(
            frame=e.frame, number=e.number, name=e.name, sex=e.sex, age=e.age,
            weight=e.weight, bodyweight=e.bodyweight, body_change=e.body_change,
            odds=e.odds, popularity=rank_by_num[e.number],
        ) for e in entries
    ]
    return repaired, True


def parse_entries(text: str) -> List[Entry]:
    entries: List[Entry] = []

    # Markdown table
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
                for c in [clean_md(c) for c in raw[horse_idx + 6:]]:
                    if re.fullmatch(r"\d+", c):
                        popularity = int(c)
                        break
            if popularity is None:
                popularity = 999

            entries.append(Entry(
                frame=frame, number=number, name=name, sex=sex, age=age,
                weight=weight, bodyweight=bodyweight, body_change=body_change,
                odds=odds, popularity=popularity,
            ))
        except (IndexError, ValueError):
            continue

    # Plain text
    plain = clean_md(text)
    sexage_matches = list(re.finditer(r"(牡|牝|セ)\s*(\d+)", plain))
    anchors = []
    search_floor = 0
    for m in sexage_matches:
        look_start = max(search_floor, m.start() - 350)
        before = plain[look_start:m.start()]
        pair_matches = list(re.finditer(
            r"(?<!\d)([1-8])\s+([1-9]|1[0-9]|2[0-9])\s+(?=(?:--|[-◎◯○▲△☆✓✔消]+))",
            before,
        ))
        if not pair_matches:
            continue
        pm = pair_matches[-1]
        row_start = look_start + pm.start()
        pair_end = look_start + pm.end()
        frame, number = int(pm.group(1)), int(pm.group(2))
        between = plain[pair_end:m.start()].strip()
        toks = [t for t in re.split(r"\s+", between) if t]
        junk = {"--", "編集", "消", "保存", "閉じる"}
        toks = [t for t in toks if t not in junk and not re.fullmatch(r"[-◎◯○▲△☆✓✔消]+", t)]
        if not toks:
            continue
        name = toks[-1]
        if name in {"馬メモ", "レース別馬メモ"}:
            continue
        anchors.append((row_start, m, frame, number, name))
        search_floor = row_start + 1

    for idx, (row_start, m, frame, number, name) in enumerate(anchors):
        row_end = anchors[idx + 1][0] if idx + 1 < len(anchors) else min(len(plain), m.end() + 500)
        after = plain[m.end():row_end]
        sex, age = m.group(1), int(m.group(2))
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
        if popularity is None:
            nums = re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", after)
            for j in range(len(nums) - 1, 0, -1):
                try:
                    pop_cand = int(float(nums[j]))
                    odds_cand = float(nums[j - 1])
                except ValueError:
                    continue
                if 1 <= pop_cand <= 30 and odds_cand >= 1.0 and abs(odds_cand - weight) > 1e-9:
                    popularity, odds = pop_cand, odds_cand
                    break
        if popularity is None:
            popularity = 999
        entries.append(Entry(
            frame=frame, number=number, name=name, sex=sex, age=age,
            weight=weight, bodyweight=bodyweight, body_change=body_change,
            odds=odds, popularity=popularity,
        ))

    out: Dict[int, Entry] = {}
    for e in entries:
        old = out.get(e.number)
        if old is None:
            out[e.number] = e
        else:
            old_q = int(bool(old.name)) + int(old.bodyweight is not None) + int(old.odds is not None)
            new_q = int(bool(e.name)) + int(e.bodyweight is not None) + int(e.odds is not None)
            if new_q > old_q:
                out[e.number] = e

    result = sorted(out.values(), key=lambda x: x.number)
    # 999しかない場合は整合修復対象外。
    if all(e.popularity != 999 for e in result):
        result, repaired = _reconcile_popularity_with_odds(result)
    else:
        repaired = False
    st.session_state["popularity_auto_repaired"] = repaired
    return result


def _parse_races_from_segment(segment: str) -> List[PastRace]:
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
        race_name = re.sub(r"^(?:映像を見る\s*)+", "", race_name).strip()

        going = ""
        time_seconds = None
        if mc:
            after_cond = seg[mc.end():mc.end() + 100]
            mg = re.search(r"(良|稍重|稍|重|不良|不)", after_cond)
            if mg:
                going = normalize_going(mg.group(1))
            time_seconds = parse_time_seconds(after_cond)

        fourth_corner = None
        pos_all = re.findall(r"(?<!\d)(\d{1,2}(?:-\d{1,2}){1,3})(?!\d)", seg)
        if pos_all:
            fourth_corner = int(pos_all[0].split("-")[-1])

        final3f = None
        mf3 = re.search(r"\d{1,2}(?:-\d{1,2}){1,3}\s*\((\d{2}\.\d)\)", seg)
        if mf3:
            final3f = float(mf3.group(1))

        races.append(PastRace(
            race_date=race_date,
            track=track,
            finish=finish,
            race_name=race_name,
            class_rank=class_rank_from_text(race_name),
            surface=surface,
            distance=distance,
            going=going,
            time_seconds=time_seconds,
            final3f=final3f,
            fourth_corner=fourth_corner,
        ))
    return races


def parse_horse_histories(text: str, entries: Optional[List[Entry]] = None) -> Dict[int, HorseHistory]:
    histories: Dict[int, HorseHistory] = {}

    # Markdown rows
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

    # Plain text
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
                if e.body_change == 0:
                    body_token = f"{e.bodyweight}(0)"
            sexage_token = f"{e.sex}{e.age}"
            for pos in candidates:
                window = plain[pos:pos + 500]
                score = 0
                if body_token:
                    bw_pat = re.escape(body_token).replace(r"\(", r"(?:kg)?\(")
                    if re.search(bw_pat, window):
                        score += 4
                if sexage_token in window:
                    score += 2
                if e.odds is not None and str(e.odds) in window:
                    score += 1
                if re.search(r"(?:逃|先|差|追)(?:連闘|中\d+週)", window):
                    score += 2
                if score > best_score:
                    best_score, best_pos = score, pos
            if best_pos is not None and best_score >= 2:
                header_positions.append((best_pos, e))

        header_positions.sort(key=lambda x: x[0])
        for i, (pos, e) in enumerate(header_positions):
            end = header_positions[i + 1][0] if i + 1 < len(header_positions) else len(plain)
            segment = plain[pos:end]
            ms = re.search(r"(?:^|\s)(逃|先|差|追)(?:連闘|中\d+週)", segment[:500])
            style = ms.group(1) if ms else ""
            races = _parse_races_from_segment(segment)
            if races or e.number not in histories:
                histories[e.number] = HorseHistory(number=e.number, name=e.name, style=style, races=races)

    return histories


# ============================================================
# Fixed AXIS penalty filter (applied only AFTER clock TOP6)
# ============================================================

def subtract_months(d: date, months: int) -> date:
    y, m = d.year, d.month - months
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
        return False
    valid_surfaces = [r.surface for r in history.races if r.surface in {"芝", "ダ"}]
    if not valid_surfaces:
        return False
    return current_surface not in valid_surfaces


def has_steep_good_run(history: Optional[HorseHistory]) -> bool:
    if not history or not history.races:
        return True
    return any(r.track in STEEP_TRACKS and r.finish is not None and r.finish <= 3 for r in history.races)


def previous_race(history: Optional[HorseHistory]) -> Optional[PastRace]:
    return history.races[0] if history and history.races else None


def axis_penalty(
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


# ============================================================
# Clock engine
# ============================================================

def distance_group(distance: int) -> str:
    if distance <= 900:
        return "800"
    if 1000 <= distance <= 1400:
        return "short"
    if distance == 1500:
        return "1500"
    if 1600 <= distance <= 1800:
        return "1600-1800"
    if 2000 <= distance <= 2200:
        return "2000-2200"
    if distance >= 2400:
        return "2400+"
    return "other"


def group_distance_match(current: int, candidate: Optional[int]) -> bool:
    if candidate is None:
        return False
    g = distance_group(current)
    if g == "800":
        return candidate in {800, 850, 900, 1000}
    if g == "short":
        return 1000 <= candidate <= 1400
    if g == "1500":
        return candidate in {1400, 1500}
    if g == "1600-1800":
        return 1600 <= candidate <= 1800
    if g == "2000-2200":
        return 2000 <= candidate <= 2200
    if g == "2400+":
        return candidate >= 2400
    return candidate == current


def timed_races(history: Optional[HorseHistory], race: RaceInfo) -> List[PastRace]:
    if not history:
        return []
    return [
        r for r in history.races
        if r.surface == race.surface and r.distance is not None and r.time_seconds is not None
    ]


def best_time(rs: List[PastRace]) -> Optional[float]:
    vals = [r.time_seconds for r in rs if r.time_seconds is not None]
    return min(vals) if vals else None


def second_best_time(rs: List[PastRace]) -> Optional[float]:
    vals = sorted(r.time_seconds for r in rs if r.time_seconds is not None)
    return vals[1] if len(vals) >= 2 else None


def recent_time(rs: List[PastRace]) -> Optional[float]:
    dated = [r for r in rs if r.time_seconds is not None]
    if not dated:
        return None
    dated.sort(key=lambda r: r.race_date or date.min, reverse=True)
    return dated[0].time_seconds


def best_final3f(rs: List[PastRace]) -> Optional[float]:
    vals = [r.final3f for r in rs if r.final3f is not None]
    return min(vals) if vals else None


def front_positive(rs: List[PastRace]) -> bool:
    return any(r.fourth_corner is not None and r.fourth_corner <= 3 for r in rs[:3])


def rank_values(values: Dict[int, Optional[float]]) -> Dict[int, float]:
    """Lower-is-better field-relative rank. Missing is last+2."""
    valid = sorted((v, n) for n, v in values.items() if v is not None)
    ranks: Dict[int, float] = {}
    last_v = None
    last_rank = 0
    for idx, (v, n) in enumerate(valid, 1):
        if last_v is None or abs(v - last_v) > 1e-9:
            last_rank = idx
            last_v = v
        ranks[n] = float(last_rank)
    miss_rank = float(len(valid) + 2)
    for n in values:
        ranks.setdefault(n, miss_rank)
    return ranks


def build_profiles(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory]) -> Dict[int, Dict]:
    profiles: Dict[int, Dict] = {}
    for e in entries:
        h = histories.get(e.number)
        all_timed = timed_races(h, race)
        exact_track = [r for r in all_timed if r.track == race.track and r.distance == race.distance]
        same_dist = [r for r in all_timed if r.distance == race.distance]
        same_going_dist = [r for r in same_dist if r.going == race.going]
        group_rs = [r for r in all_timed if group_distance_match(race.distance, r.distance)]
        same_track_group = [r for r in group_rs if r.track == race.track]
        adjacent_1400 = [r for r in all_timed if r.track == race.track and r.distance == 1400]
        adjacent_2200 = [r for r in all_timed if r.distance == 2200]

        profiles[e.number] = {
            "entry": e,
            "history": h,
            "exact_track_best": best_time(exact_track),
            "exact_track_recent": recent_time(exact_track),
            "exact_track_second": second_best_time(exact_track),
            "same_dist_best": best_time(same_dist),
            "same_dist_recent": recent_time(same_dist),
            "same_dist_second": second_best_time(same_dist),
            "same_going_best": best_time(same_going_dist),
            "group_best": best_time(group_rs),
            "same_track_group_best": best_time(same_track_group),
            "adj1400_recent": recent_time(adjacent_1400),
            "adj2200_best": best_time(adjacent_2200),
            "final3f": best_final3f(group_rs),
            "front_positive": front_positive(group_rs),
            "exact_count": len(exact_track),
            "same_dist_count": len(same_dist),
        }

    # Cross-distance group percentile/rank: rank within each distance, then take the best
    # normalized field-relative rank for each horse. This avoids directly comparing raw
    # 1600m seconds with raw 1800m seconds.
    all_group_records: Dict[int, Dict[int, float]] = {}
    for e in entries:
        h = histories.get(e.number)
        for r in timed_races(h, race):
            if group_distance_match(race.distance, r.distance):
                all_group_records.setdefault(r.distance, {})
                cur = all_group_records[r.distance].get(e.number)
                if cur is None or (r.time_seconds is not None and r.time_seconds < cur):
                    all_group_records[r.distance][e.number] = r.time_seconds

    normalized_by_horse: Dict[int, List[float]] = {e.number: [] for e in entries}
    for dist, vals in all_group_records.items():
        ordered = sorted(vals.items(), key=lambda x: x[1])
        n = len(ordered)
        if n == 0:
            continue
        last_time = None
        last_rank = 0
        for idx, (num, tm) in enumerate(ordered, 1):
            if last_time is None or abs(tm - last_time) > 1e-9:
                last_rank = idx
                last_time = tm
            normalized_by_horse[num].append(last_rank / n)

    for num in profiles:
        vals = normalized_by_horse.get(num, [])
        profiles[num]["group_relative"] = min(vals) if vals else None

    return profiles


def weighted_rank_order(race: RaceInfo, profiles: Dict[int, Dict]) -> List[int]:
    nums = list(profiles.keys())
    metrics = {
        key: rank_values({n: profiles[n].get(key) for n in nums})
        for key in [
            "exact_track_best", "exact_track_recent", "exact_track_second",
            "same_dist_best", "same_dist_recent", "same_dist_second",
            "same_going_best", "group_relative", "adj1400_recent", "adj2200_best", "final3f",
        ]
    }

    g = distance_group(race.distance)
    if race.distance == 1400:
        weights = {
            "exact_track_best": 5.0,
            "exact_track_recent": 4.0,
            "exact_track_second": 3.0,
            "same_going_best": 3.0,
            "same_dist_best": 2.0,
            "final3f": 1.0,
        }
    elif race.distance == 1500:
        weights = {
            "exact_track_best": 5.0,
            "same_going_best": 4.0,
            "exact_track_recent": 3.0,
            "exact_track_second": 2.5,
            "adj1400_recent": 2.0,
            "final3f": 1.0,
        }
    elif g == "800":
        weights = {
            "exact_track_best": 5.0,
            "exact_track_recent": 4.0,
            "exact_track_second": 3.0,
            "same_dist_best": 3.0,
            "group_relative": 1.5,
        }
    elif g == "short":
        weights = {
            "exact_track_best": 5.0,
            "same_dist_best": 4.0,
            "same_dist_recent": 3.0,
            "same_dist_second": 2.5,
            "final3f": 1.0,
        }
    elif g == "1600-1800":
        weights = {
            "exact_track_best": 4.0,
            "group_relative": 4.0,
            "same_dist_recent": 3.0,
            "same_dist_second": 2.0,
            "same_dist_best": 2.0,
            "final3f": 1.0,
        }
    elif g == "2000-2200":
        # 最新検証：2000m戦では2000mそのものを最優先。2200は補助。
        if race.distance == 2000:
            weights = {
                "same_dist_best": 5.0,
                "same_dist_recent": 4.0,
                "same_going_best": 3.0,
                "same_dist_second": 3.0,
                "exact_track_best": 2.0,
                "adj2200_best": 1.0,
                "final3f": 1.0,
            }
        else:
            weights = {
                "same_dist_best": 5.0,
                "same_dist_recent": 4.0,
                "same_going_best": 3.0,
                "same_dist_second": 3.0,
                "exact_track_best": 2.0,
                "group_relative": 1.0,
                "final3f": 1.0,
            }
    else:
        weights = {
            "same_dist_best": 5.0,
            "same_dist_recent": 4.0,
            "same_dist_second": 3.0,
            "exact_track_best": 2.0,
            "final3f": 1.0,
        }

    scores: Dict[int, float] = {n: 0.0 for n in nums}
    for key, w in weights.items():
        for n in nums:
            scores[n] += metrics[key][n] * w

    # STARTは「前位置なら小さくプラス、後方は減点なし」。
    for n in nums:
        if profiles[n].get("front_positive"):
            scores[n] -= 0.35

    # 同点は人気ではなく、時計の直接根拠→馬番で決着。
    return sorted(
        nums,
        key=lambda n: (
            scores[n],
            float("inf") if profiles[n]["same_dist_best"] is None else profiles[n]["same_dist_best"],
            float("inf") if profiles[n]["exact_track_best"] is None else profiles[n]["exact_track_best"],
            n,
        ),
    )


def evaluation_type(race: RaceInfo, p: Dict) -> str:
    if p["exact_track_best"] is not None and p["exact_track_recent"] == p["exact_track_best"]:
        return "同コース絶対＋直近型"
    if p["same_dist_best"] is not None and p["same_dist_second"] is not None:
        return "同距離高速再現型"
    if race.distance == 1500 and p["adj1400_recent"] is not None:
        return "1400現在値持ち込み型"
    if p["same_dist_best"] is not None:
        return "同距離絶対時計型"
    if p["group_relative"] is not None:
        return "距離帯高速持ち込み型"
    return "時計材料限定型"


def evaluation_text(race: RaceInfo, p: Dict) -> str:
    bits = []
    if p["exact_track_best"] is not None:
        bits.append(f"{race.track}{race.distance}mベスト {format_time(p['exact_track_best'])}")
    elif p["same_dist_best"] is not None:
        bits.append(f"{race.distance}mベスト {format_time(p['same_dist_best'])}")

    if p["same_dist_recent"] is not None:
        bits.append(f"直近同距離 {format_time(p['same_dist_recent'])}")
    if p["same_going_best"] is not None:
        bits.append(f"{race.going}ベスト {format_time(p['same_going_best'])}")
    if p["same_dist_second"] is not None:
        bits.append(f"同距離2本目 {format_time(p['same_dist_second'])}")
    if race.distance == 1500 and p["adj1400_recent"] is not None:
        bits.append(f"同場1400直近 {format_time(p['adj1400_recent'])}")
    if p["final3f"] is not None:
        bits.append(f"上がり最速 {p['final3f']:.1f}")
    if p["front_positive"]:
        bits.append("前位置STARTプラス")
    return " / ".join(bits) if bits else "時計比較材料が少ない"


def build_clock_prediction(
    race: RaceInfo,
    entries: List[Entry],
    histories: Dict[int, HorseHistory],
    race_date: date,
) -> Dict:
    if len(entries) < 3:
        raise ValueError("出馬表から3頭以上を読み取れませんでした。")

    profiles = build_profiles(race, entries, histories)
    order = weighted_rank_order(race, profiles)
    top6_nums = order[: min(6, len(order))]
    top3_nums = order[: min(3, len(order))]

    selected_rows = []
    by_num = {e.number: e for e in entries}
    for idx, n in enumerate(top6_nums, 1):
        e = by_num[n]
        p = profiles[n]
        selected_rows.append({
            "時計順位": idx,
            "馬番": n,
            "馬名": e.name,
            "タイプ": evaluation_type(race, p),
            "同場同距離ベスト": format_time(p["exact_track_best"]),
            "同距離ベスト": format_time(p["same_dist_best"]),
            "直近同距離": format_time(p["same_dist_recent"]),
            "同馬場ベスト": format_time(p["same_going_best"]),
            "2本目": format_time(p["same_dist_second"]),
            "上がり": "—" if p["final3f"] is None else f"{p['final3f']:.1f}",
            "評価": evaluation_text(race, p),
        })

    # 時計TOP6にだけ固定軸の減点ルールを適用。人気では並べない。
    top_weight = max((e.weight for e in entries), default=None) if race.is_handicap else None
    penalty_rows = []
    for n in top6_nums:
        e = by_num[n]
        score, reasons = axis_penalty(e, histories.get(n), race, race_date, top_weight)
        penalty_rows.append({
            "馬番": n,
            "馬名": e.name,
            "減点": score,
            "内訳": "、".join(reasons) if reasons else "減点なし",
            "時計順位": top6_nums.index(n) + 1,
        })

    penalty_rows.sort(key=lambda r: (-r["減点"], r["時計順位"]))

    # 上位3頭分を満たすまで減点グループを採用。境界同点は全頭残す。
    if penalty_rows:
        unique_scores = sorted({r["減点"] for r in penalty_rows}, reverse=True)
        candidate_nums: List[int] = []
        cutoff = unique_scores[-1]
        for s in unique_scores:
            group = [r["馬番"] for r in penalty_rows if r["減点"] == s]
            candidate_nums.extend(group)
            cutoff = s
            if len(candidate_nums) >= 3:
                break
    else:
        candidate_nums, cutoff = [], None

    return {
        "race": asdict(race),
        "race_date": race_date.isoformat(),
        "top3": top3_nums,
        "top6": top6_nums,
        "selected_rows": selected_rows,
        "penalty_rows": penalty_rows,
        "penalty_top": candidate_nums,
        "penalty_cutoff": cutoff,
        "entries": [asdict(e) for e in entries],
    }


# ============================================================
# Result verification
# ============================================================

def parse_result(text: str) -> List[int]:
    nums = [int(x) for x in re.findall(r"\d+", text)]
    return nums[:6]


def verify_result(pred: Dict, result_text: str) -> Dict:
    result = parse_result(result_text)
    if len(result) < 3:
        raise ValueError("結果は最低1〜3着まで『7-10-4』のように入力してください。1〜6着まで入力できます。")

    top3_actual = result[:3]
    top6_actual = result[:6]
    clock_top3 = set(map(int, pred["top3"]))
    clock_top6 = set(map(int, pred["top6"]))
    penalty_top = set(map(int, pred["penalty_top"]))

    top3_hits = sum(1 for n in top3_actual if n in clock_top3)
    top6_ticket_hits = sum(1 for n in top3_actual if n in clock_top6)
    top6_overlap = sum(1 for n in top6_actual if n in clock_top6)
    penalty_hits = sum(1 for n in top3_actual if n in penalty_top)

    return {
        "日付": pred["race_date"],
        "レース": pred["race"].get("race_name", ""),
        "競馬場": pred["race"].get("track", ""),
        "条件": f"{pred['race'].get('surface','')}{pred['race'].get('distance',0)}m",
        "結果": "-".join(map(str, result)),
        "時計TOP3": "・".join(map(str, pred["top3"])),
        "時計TOP6": "・".join(map(str, pred["top6"])),
        "TOP3馬券内": f"{top3_hits}/3",
        "TOP6馬券内": f"{top6_ticket_hits}/3",
        "TOP6完全捕捉": "○" if top6_ticket_hits == 3 else "×",
        "実上位6捕捉": f"{top6_overlap}/{len(top6_actual)}",
        "減点TOP": "・".join(map(str, pred["penalty_top"])),
        "減点TOP頭数": len(pred["penalty_top"]),
        "減点TOP馬券内": f"{penalty_hits}/3",
        "減点TOP完全捕捉": "○" if penalty_hits == 3 else "×",
    }


# ============================================================
# UI
# ============================================================

st.set_page_config(page_title=APP_NAME, page_icon="⏱️", layout="wide")
st.title("⏱️ 競馬AI 時計選定 v2.0")
st.caption("時計TOP6を先に選定 → 時計TOP6だけ固定AXIS減点でグループ化｜人気・オッズは時計順位に不使用")

if "locked_prediction" not in st.session_state:
    st.session_state.locked_prediction = None
if "history" not in st.session_state:
    st.session_state.history = []


def clear_prediction_inputs():
    st.session_state.locked_prediction = None
    st.session_state.race_date_input = date.today()
    st.session_state.race_text_input = ""
    st.session_state.entry_text_input = ""
    st.session_state.history_text_input = ""
    st.session_state.result_text_input = ""


with st.sidebar:
    st.subheader("今回の流れ")
    st.markdown(
        """
**STEP 1｜時計選定**  
人気・オッズを使わず、馬柱の実時計だけでTOP3 / TOP6を作成。

**STEP 2｜減点フィルター**  
時計TOP6だけに旧・固定AXIS v3.0の減点を適用。

**同点処理**  
人気順では切りません。  
上位3頭ラインが同点なら4頭・5頭になっても全頭残します。

**結果検証**  
時計TOP3 / TOP6と、減点TOPグループを同時比較します。
        """
    )
    with st.expander("時計ルールの現在地"):
        st.write("1400m：同コース絶対時計・直近・高速再現性・近い馬同士は上がりで調整")
        st.write("1500m：同コース1500絶対時計＋直近/同馬場＋強い同場1400を補助")
        st.write("1600〜1800m：別競馬場の同距離生時計を絶対視せず、距離帯内の相対高速も評価")
        st.write("2000m：2000m実時計を最優先。2200mは補助")
        st.write("START：前位置のみプラス。後方は減点しない")

pred_tab, hist_tab, rule_tab = st.tabs(["予想・結果検証", "検証履歴", "ルール"]) 

with pred_tab:
    st.subheader("① 入力")
    race_date = st.date_input("レース日", value=date.today(), key="race_date_input")

    c1, c2, c3 = st.columns(3)
    with c1:
        race_text = st.text_area("レース情報", height=220, placeholder="# レース名\n15:25発走 / ダ1700m ...", key="race_text_input")
    with c2:
        entry_text = st.text_area("出馬表", height=220, placeholder="netkeibaの出馬表をそのまま貼り付け", key="entry_text_input")
    with c3:
        history_text = st.text_area("馬柱", height=220, placeholder="全馬の馬柱をそのまま貼り付け", key="history_text_input")

    b1, b2 = st.columns(2)
    with b1:
        predict_clicked = st.button("時計分析する（この時点でロック）", type="primary", use_container_width=True)
    with b2:
        st.button("入力・予想をすべてクリア", use_container_width=True, on_click=clear_prediction_inputs)

    if predict_clicked:
        race = parse_race_info(race_text)
        entries = parse_entries(entry_text)
        histories = parse_horse_histories(history_text, entries)

        if st.session_state.get("popularity_auto_repaired", False):
            st.info("人気表示に矛盾があったためオッズ順で補正しました。※時計順位には人気・オッズを使いません。")

        st.caption(f"解析結果：出馬表 {len(entries)}頭 / 馬柱 {len(histories)}頭")
        problems = []
        notices = []
        if not race.surface or not race.distance:
            problems.append("レース情報から芝/ダート・距離を取得できませんでした。")
        if not race.track:
            problems.append("競馬場を取得できませんでした。")
        if len(entries) < 3:
            problems.append("出馬表から十分な頭数を取得できませんでした。")
        if race.field_size and len(entries) != race.field_size and len(entries) >= 3:
            notices.append(f"レース情報は{race.field_size}頭、出馬表解析は{len(entries)}頭です。解析頭数を優先します。")
        if len(histories) < min(len(entries), 3):
            problems.append(f"馬柱の解析頭数が少ないです（{len(histories)}頭）。")
        timed_count = sum(
            1 for h in histories.values() for r in h.races
            if r.surface == race.surface and r.time_seconds is not None
        )
        if timed_count == 0:
            problems.append("馬柱から走破時計を取得できませんでした。")

        if notices:
            st.warning("\n".join(notices))
        if problems:
            st.error("\n".join(problems))
        else:
            try:
                pred = build_clock_prediction(race, entries, histories, race_date)
                st.session_state.locked_prediction = pred
                st.success("時計分析をロックしました。結果入力時も再計算しません。")
            except Exception as e:
                st.error(f"分析エラー: {e}")

    pred = st.session_state.locked_prediction
    if pred:
        st.divider()
        st.subheader("② ロック済み時計分析")

        top3_text = "・".join(f"{n}" for n in pred["top3"])
        top6_text = "・".join(f"{n}" for n in pred["top6"])
        st.success(f"時計TOP3：{top3_text}")
        st.info(f"時計TOP6：{top6_text}")

        st.markdown("### 選定6頭の時計評価")
        st.dataframe(pd.DataFrame(pred["selected_rows"]), use_container_width=True, hide_index=True)

        st.markdown("### 減点フィルター（時計TOP6のみ）")
        pdf = pd.DataFrame(pred["penalty_rows"])
        if not pdf.empty:
            st.dataframe(pdf[["馬番", "馬名", "減点", "内訳", "時計順位"]], use_container_width=True, hide_index=True)

            groups = []
            for s in sorted(pdf["減点"].unique(), reverse=True):
                rows = pdf[pdf["減点"] == s]
                horses = "・".join(f"{int(r['馬番'])}{r['馬名']}" for _, r in rows.iterrows())
                groups.append(f"**{int(s)}点**：{horses}")
            st.markdown("  \n".join(groups))

            top_names = []
            entry_map = {int(e["number"]): e["name"] for e in pred["entries"]}
            for n in pred["penalty_top"]:
                top_names.append(f"{n}{entry_map.get(int(n), '')}")
            st.warning(f"🔥 減点TOP（同率含む {len(top_names)}頭）：" + "・".join(top_names))

        st.divider()
        st.subheader("③ 結果検証")
        result_text = st.text_input("着順の馬番（最低3着、最大6着）", placeholder="例：7-10-4-9-6-1", key="result_text_input")
        if st.button("結果を照合して履歴に保存", use_container_width=True):
            try:
                record = verify_result(pred, result_text)
                st.session_state.history.append(record)
                st.success(
                    f"結果 {record['結果']}｜時計TOP3 {record['TOP3馬券内']}｜"
                    f"時計TOP6 {record['TOP6馬券内']}｜減点TOP {record['減点TOP馬券内']}"
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
        top3_hits = sum(int(str(x).split("/")[0]) for x in hdf["TOP3馬券内"]) if "TOP3馬券内" in hdf else 0
        top6_hits = sum(int(str(x).split("/")[0]) for x in hdf["TOP6馬券内"]) if "TOP6馬券内" in hdf else 0
        top6_full = int((hdf["TOP6完全捕捉"] == "○").sum()) if "TOP6完全捕捉" in hdf else 0
        penalty_hits = sum(int(str(x).split("/")[0]) for x in hdf["減点TOP馬券内"]) if "減点TOP馬券内" in hdf else 0
        penalty_full = int((hdf["減点TOP完全捕捉"] == "○").sum()) if "減点TOP完全捕捉" in hdf else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("検証数", f"{total}R")
        m2.metric("時計TOP3 馬券内", f"{top3_hits}/{total * 3}")
        m3.metric("時計TOP6 馬券内", f"{top6_hits}/{total * 3}")
        m4.metric("時計TOP6 完全捕捉", f"{top6_full}/{total}")
        m5.metric("減点TOP 完全捕捉", f"{penalty_full}/{total}")
        st.metric("減点TOP 馬券内捕捉", f"{penalty_hits}/{total * 3}")

        csv_bytes = hdf.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "検証履歴CSVをダウンロード",
            data=csv_bytes,
            file_name="keiba_clock_validation_history.csv",
            mime="text/csv",
            use_container_width=True,
        )
        if st.button("履歴を全削除"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("まだ検証履歴はありません。")

with rule_tab:
    st.subheader("時計選定 v2.0")
    st.markdown(
        """
### 基本
- 人気・オッズは時計順位に使わない
- 走破時計・直近時計・高速時計の再現性・馬場・上がり・同コースを使う
- STARTは通過順の代理。前位置のみプラス、後方は減点しない
- パータイムや架空の基礎値は使わない

### 距離別
- **800m**：同場800絶対時計 → 直近800 → 再現性。900〜1000は補助
- **1000〜1400m**：同場同距離を中心。1400は絶対時計・直近・再現性を強める
- **1500m**：同場1500絶対時計・同馬場・直近・再現性。強い同場1400を補助
- **1600〜1800m**：同コース同距離＋距離帯内の相対高速。別競馬場同距離の生時計だけを絶対視しない
- **2000m**：2000m実時計を最優先。直近・同馬場・再現性。2200mは補助
- **2400m以上**：同距離実時計を中心に評価

### 減点フィルター
時計TOP6だけに旧・完全固定AXIS v3.0の減点条件を適用。  
**人気順で同点を切らない。** 上位3頭ラインが同点なら4頭・5頭でも全頭残す。

- −5：初ダート / 初芝
- −5：ダート戦で前走が牝馬限定戦
- −4：前走が重 / 不良
- −4：前走JRAローカル（福島・新潟・小倉・札幌・函館）
- −3：6か月以上休養
- −3：芝14番以降
- −3：ダート1枠 / 2枠
- −3：ハンデ戦トップハンデ
- −2：急坂好走なし
- −2：馬体重±15kg以上
- −1：距離延長
- −1：冬牝 / 8月の牡馬
- 判定不可：減点なし
        """
    )
