from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


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
    margin: Optional[float] = None  # 勝馬との差。勝利時は負数も可


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
    """
    JRA + NARのクラスをざっくり序列化。
    時計順位の主役ではなく「同程度の時計なら上位クラスを優先」する補助用。
    """
    t = clean_md(text).upper()

    # JRA / ダートグレード
    if "JPN1" in t or "GI" in t or "G1" in t:
        return 10
    if "JPN2" in t or "GII" in t or "G2" in t:
        return 9
    if "JPN3" in t or "GIII" in t or "G3" in t:
        return 8
    if "重賞" in t:
        return 7
    if re.search(r"L", t) or "OP" in t or "オープン" in t:
        return 6
    if "3勝" in t:
        return 5
    if "2勝" in t:
        return 4
    if "1勝" in t:
        return 3
    if "未勝利" in t:
        return 1
    if "新馬" in t:
        return 0

    # NAR
    # A1/A2 > B1/B2 > B3 > C1 > C2 > C3 > C4
    if re.search(r"A1", t):
        return 6
    if re.search(r"A2", t):
        return 5
    if re.search(r"B1", t):
        return 4
    if "B2B3" in t or "B2・B3" in t:
        return 4
    if re.search(r"B2", t):
        return 4
    if re.search(r"B3", t):
        return 3
    if re.search(r"C1", t):
        return 2
    if re.search(r"C2", t):
        return 1
    if re.search(r"C3", t):
        return 0
    if re.search(r"C4", t):
        return -1
    return -2


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

        margin = None
        # 各過去走セグメントの末尾にある対勝馬着差 (0.3) / (-0.5) を取得。
        # 上がり (39.0) 等も含まれるため、小数括弧の最後を採用する。
        margin_vals = re.findall(r"\((-?\d+\.\d+)\)", seg)
        if margin_vals:
            try:
                margin = float(margin_vals[-1])
            except ValueError:
                margin = None

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
            margin=margin,
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
# 時計分析単独エンジン v3.0
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
    return [r for r in history.races
            if r.surface == race.surface and r.distance is not None and r.time_seconds is not None]


def best_time(rs: List[PastRace]) -> Optional[float]:
    vals = [r.time_seconds for r in rs if r.time_seconds is not None]
    return min(vals) if vals else None


def second_best_time(rs: List[PastRace]) -> Optional[float]:
    vals = sorted(r.time_seconds for r in rs if r.time_seconds is not None)
    return vals[1] if len(vals) >= 2 else None


def recent_time(rs: List[PastRace]) -> Optional[float]:
    valid = [r for r in rs if r.time_seconds is not None]
    if not valid:
        return None
    valid.sort(key=lambda r: r.race_date or date.min, reverse=True)
    return valid[0].time_seconds


def best_close_margin(rs: List[PastRace]) -> Optional[float]:
    vals = [r.margin for r in rs if r.margin is not None]
    return min(vals) if vals else None


def close_run_count(rs: List[PastRace], limit: float = 0.3) -> int:
    return sum(1 for r in rs if r.margin is not None and r.margin <= limit)


def win_count(rs: List[PastRace]) -> int:
    return sum(1 for r in rs if r.finish == 1)


def rank_values(values: Dict[int, Optional[float]]) -> Dict[int, float]:
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


def is_upper_environment(track: str) -> bool:
    return track in JRA_TRACKS or track in {"浦和", "船橋", "大井", "川崎"}


def local_transfer_guard_target(race: RaceInfo, e: Entry, h: Optional[HorseHistory]) -> bool:
    if race.track not in NAR_TRACKS or not h or not h.races or e.popularity > 3:
        return False
    prev = h.races[0]
    if not is_upper_environment(prev.track):
        return False
    # 現競馬場への過去出走が無い＝今回を転入初戦相当として扱う
    return not any(r.track == race.track for r in h.races)


def debut_warning_target(e: Entry, h: Optional[HorseHistory]) -> bool:
    return (not h or not h.races) and e.popularity <= 5



def margin_penalty(margin: Optional[float]) -> float:
    """
    ベスト時計を出した時の着差ペナルティ。
    生時計を主役に残しつつ、時計差が僅差なら接戦馬を上へ。

    これにより:
    - 1:41.5 / 1.4差 より 1:41.6 / 0.6差を上げられる
    - 2:08.5 / 1.7差 と 2:09.8 / 1.9差なら、生時計差1.3秒を維持しやすい
    """
    if margin is None:
        return 0.35
    if margin <= 0.3:
        return 0.00
    if margin <= 0.6:
        return 0.10
    if margin <= 1.0:
        return 0.25
    if margin <= 1.5:
        return 0.55
    if margin <= 2.0:
        return 0.80
    if margin <= 2.5:
        return 1.05
    if margin <= 3.0:
        return 1.45
    return 2.00



def best_clock_race(rs: List[PastRace]) -> Optional[PastRace]:
    valid = [r for r in rs if r.time_seconds is not None]
    if not valid:
        return None
    return min(valid, key=lambda r: r.time_seconds)


def best_quality_race(rs: List[PastRace]) -> Optional[PastRace]:
    """
    生時計 + 着差ペナルティで「実戦的に価値の高い時計」を選ぶ。
    例:
      1:41.5 / 1.4差  -> 1:43.0相当
      1:41.6 / 0.6差  -> 1:41.8相当
    """
    valid = [r for r in rs if r.time_seconds is not None]
    if not valid:
        return None
    return min(
        valid,
        key=lambda r: (
            r.time_seconds + margin_penalty(r.margin),
            r.time_seconds,
        )
    )


def quality_time(rs: List[PastRace]) -> Optional[float]:
    """
    ベスト時計そのものに、そのレースの着差だけを加味。
    別の遅い勝ち時計へ置き換えない。
    """
    r = best_clock_race(rs)
    if r is None or r.time_seconds is None:
        return None
    return r.time_seconds + margin_penalty(r.margin)



def clock_margin(rs: List[PastRace]) -> Optional[float]:
    """純粋なベスト時計を出したレースの着差。"""
    r = best_clock_race(rs)
    return r.margin if r else None


def quality_margin(rs: List[PastRace]) -> Optional[float]:
    """着差込みで最も価値が高い時計の着差。"""
    r = best_quality_race(rs)
    return r.margin if r else None


def build_profiles(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory]) -> Dict[int, Dict]:
    profiles = {}

    for e in entries:
        h = histories.get(e.number)
        all_timed = timed_races(h, race)

        same_dist_all = [r for r in all_timed if r.distance == race.distance]
        exact = [r for r in same_dist_all if r.track == race.track]
        exact_going = [r for r in exact if r.going == race.going]

        other_track_same_dist = [r for r in same_dist_all if r.track != race.track]

        adjacent_same_track = [
            r for r in all_timed
            if r.track == race.track
            and r.distance != race.distance
            and group_distance_match(race.distance, r.distance)
        ]
        adjacent_other = [
            r for r in all_timed
            if r.track != race.track
            and r.distance != race.distance
            and group_distance_match(race.distance, r.distance)
        ]

        # 上昇度：同場同距離を優先
        trend_src = exact if len(exact) >= 2 else same_dist_all
        recent_for_trend = sorted(
            trend_src, key=lambda r: r.race_date or date.min, reverse=True
        )[:3]
        rec_times = [r.time_seconds for r in recent_for_trend if r.time_seconds is not None]
        improvement = None
        if len(rec_times) >= 2:
            improvement = rec_times[-1] - rec_times[0]

        exact_close = close_run_count(exact, 0.3)
        exact_win = win_count(exact)
        other_close = close_run_count(other_track_same_dist, 0.3)
        other_win = win_count(other_track_same_dist)

        class_src = exact if exact else (
            same_dist_all if same_dist_all else adjacent_same_track + adjacent_other
        )
        class_best = max([r.class_rank for r in class_src], default=-2)

        exact_competitive = sum(
            1 for r in sorted(exact, key=lambda r: r.race_date or date.min, reverse=True)[:3]
            if r.margin is not None and r.margin <= 1.0
        )

        # 同馬場で1秒以内の実戦的好走数
        going_competitive = sum(
            1 for r in exact_going
            if r.margin is not None and r.margin <= 1.0
        )

        best_r = best_clock_race(exact)
        quality_r = best_quality_race(exact)

        profiles[e.number] = {
            "entry": e,
            "history": h,
            "same_dist": same_dist_all,
            "exact": exact,
            "exact_going": exact_going,
            "other_track_same_dist": other_track_same_dist,
            "adjacent_same_track": adjacent_same_track,
            "adjacent_other": adjacent_other,

            "exact_best": best_time(exact),
            "exact_best_margin": best_r.margin if best_r else None,
            "exact_quality_time": quality_time(exact),
            "exact_quality_margin": quality_r.margin if quality_r else None,
            "exact_recent": recent_time(exact),
            "exact_recent_date": max([r.race_date for r in exact if r.race_date is not None], default=None),
            "exact_second": second_best_time(exact),
            "exact_going_best": best_time(exact_going),

            "other_same_dist_best": best_time(other_track_same_dist),
            "adjacent_same_track_best": best_time(adjacent_same_track),
            "adjacent_other_best": best_time(adjacent_other),

            "best_margin": best_close_margin(exact) if exact else best_close_margin(same_dist_all),
            "exact_close_count": exact_close,
            "exact_win_count": exact_win,
            "other_close_count": other_close,
            "other_win_count": other_win,

            "same_dist_count": len(same_dist_all),
            "exact_count": len(exact),
            "exact_competitive": exact_competitive,
            "going_competitive": going_competitive,
            "improvement": improvement,
            "class_best": class_best,
        }

    return profiles




def base_clock_order(race: RaceInfo, profiles: Dict[int, Dict], race_date: date) -> List[int]:
    """
    現チャット検証に合わせた順位決定。

    最優先:
      1. 同競馬場・同距離の時計がある
      2. 「時計 + その時計を出した時の着差」の実戦価値
      3. 純粋な絶対時計
      4. 再現性 / 同馬場 / クラス / 直近性

    別競馬場の生時計は、同場同距離馬と秒数で直接比較しない。
    """
    nums = list(profiles)

    def key(n: int):
        p = profiles[n]

        # 2000m専用：
        # 2000mは同場同距離そのものを最優先。
        # 1800m/2200m等は補助で、2000m実績馬より上には置かない。
        if race.distance == 2000:
            if p["exact_count"] > 0:
                q = p["exact_quality_time"] if p["exact_quality_time"] is not None else 999.0
                raw = p["exact_best"] if p["exact_best"] is not None else 999.0
                bm = p.get("exact_best_margin")

                # 同距離でも「大敗の遅い時計」まで無条件に保護しない。
                # 2.5秒超の大敗は、初距離/隣接距離の有力馬と同じ補助グループへ降格。
                weak_exact = bm is not None and bm > 2.5

                repeat_bonus = (
                    min(0.24, p["exact_close_count"] * 0.08)
                    + min(0.18, p["exact_win_count"] * 0.06)
                    + min(0.15, p["exact_competitive"] * 0.05)
                )

                going_bonus = 0.10 if p["exact_going_best"] is not None else 0.0

                recency_bonus = 0.0
                rd = p.get("exact_recent_date")
                if rd is not None:
                    days = (race_date - rd).days
                    if days <= 30:
                        recency_bonus = 0.08
                    elif days >= 120:
                        recency_bonus = -0.12

                class_bonus = 0.0
                if p["class_best"] >= 4:
                    class_bonus = 0.08
                elif p["class_best"] >= 3:
                    class_bonus = 0.04

                adjusted = q - repeat_bonus - going_bonus - recency_bonus - class_bonus

                if not weak_exact:
                    return (
                        0,
                        adjusted,
                        raw,
                        -p["exact_competitive"],
                        -p["class_best"],
                        n,
                    )

                # 弱い同距離実績:
                # 初距離馬より絶対に上ではなく、時計内容で比較する補助群
                return (
                    1,
                    2,
                    adjusted,
                    -p["class_best"],
                    n,
                )

            # 同場2000mなし。
            # 別場2000m > 同場隣接 > 別場隣接。
            if p["other_track_same_dist"]:
                return (
                    1, 0,
                    -(p["other_close_count"] + p["other_win_count"]),
                    -p["class_best"], n
                )
            if p["adjacent_same_track"]:
                return (1, 1, -p["class_best"], n)
            if p["adjacent_other"]:
                return (1, 3, -p["class_best"], n)
            return (1, 4, -p["class_best"], n)

        # ----------------------------
        # A. 同場同距離実績あり
        # ----------------------------
        if p["exact_count"] > 0:
            q = p["exact_quality_time"]
            raw = p["exact_best"]

            # 再現性は「時計が近い馬同士」の微調整だけにする
            repeat_bonus = 0.0
            repeat_bonus -= min(0.20, p["exact_close_count"] * 0.06)
            repeat_bonus -= min(0.16, p["exact_win_count"] * 0.05)
            repeat_bonus -= min(0.15, p["exact_competitive"] * 0.05)

            # 今回と同じ馬場で好走時計がある馬を優先
            going_bonus = 0.0
            if p["exact_going_best"] is not None:
                going_bonus -= 0.18
                going_bonus -= min(0.10, p["going_competitive"] * 0.05)

            # 直近性。半年近く前の時計より、直近の同場同距離を優先。
            recency_penalty = 0.0
            rd = p.get("exact_recent_date")
            if rd is not None:
                days = (race_date - rd).days
                if days <= 30:
                    recency_penalty -= 0.15
                elif days <= 60:
                    recency_penalty -= 0.08
                elif days >= 150:
                    recency_penalty += 0.30
                elif days >= 100:
                    recency_penalty += 0.18

            # 上位クラスは小さく補助
            class_bonus = 0.0
            if p["class_best"] >= 6:
                class_bonus = -0.18
            elif p["class_best"] >= 4:
                class_bonus = -0.12
            elif p["class_best"] >= 3:
                class_bonus = -0.07
            elif p["class_best"] >= 2:
                class_bonus = -0.03

            # 上昇度も小さく補助
            rise_bonus = 0.0
            if p["improvement"] is not None and p["improvement"] >= 0.5:
                rise_bonus = -min(0.15, p["improvement"] * 0.03)

            adjusted = (
                (q if q is not None else 999.0)
                + repeat_bonus
                + going_bonus
                + recency_penalty
                + class_bonus
                + rise_bonus
            )

            return (
                0,                                  # 同場同距離ありを最優先
                adjusted,                           # 着差込みの時計価値
                raw if raw is not None else 999.0,  # 絶対時計
                -p["exact_competitive"],            # 再現性
                -p["class_best"],                   # クラス
                n,
            )

        # ----------------------------
        # B. 同場同距離なし
        # ----------------------------
        # ここでは別場の「1:38.2」などを大井1:41台と直接比較しない。
        support_level = 3
        if p["adjacent_same_track"]:
            support_level = 0
        elif p["other_track_same_dist"]:
            support_level = 1
        elif p["adjacent_other"]:
            support_level = 2

        support_quality = (
            -(p["other_close_count"] + p["other_win_count"]),
            -p["class_best"],
        )

        return (
            1,                 # exact馬より必ず後ろ
            support_level,
            support_quality,
            n,
        )

    return sorted(nums, key=key)




def guard_lists(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory],
                profiles: Dict[int, Dict], base_order: List[int]) -> Dict[str, List[int]]:
    by_num = {e.number: e for e in entries}
    pos = {n: i + 1 for i, n in enumerate(base_order)}

    # 絶対時計のTOP3級判定も「同場同距離」で行う
    exact_ranks = rank_values({n: profiles[n]["exact_best"] for n in base_order})

    absolute, boundary, transfer, debut, first_distance, fast_big = [], [], [], [], [], []

    # 境界ガードは「0.3秒以内」だけで拾いすぎない。
    # 同場同距離の上位3番手時計から大きく離れる馬は対象外。
    exact_times_all = sorted(
        p["exact_best"] for p in profiles.values()
        if p["exact_best"] is not None
    )
    top3_clock_line = exact_times_all[min(2, len(exact_times_all) - 1)] if exact_times_all else None

    for n in base_order:
        p = profiles[n]
        h = histories.get(n)
        e = by_num[n]

        # 絶対時計ガード：
        # 同場同距離の絶対時計TOP3級 ＋ 同場同距離で勝利/0.3以内
        if (
            p["exact_best"] is not None
            and exact_ranks[n] <= 3
            and (p["exact_win_count"] > 0 or p["exact_close_count"] > 0)
        ):
            absolute.append(n)

        # 境界ガード：
        # 通常7〜8位付近 ＋ 同場同距離の勝利/0.3以内
        # ＋ TOP6最下位時計から大きく離れない
        if (
            pos[n] in {7, 8}
            and p["exact_best"] is not None
            and (p["exact_win_count"] > 0 or p["exact_close_count"] > 0)
        ):
            close_enough = (
                top3_clock_line is None
                or p["exact_best"] <= top3_clock_line + 1.2
            )
            if close_enough:
                boundary.append(n)

        if local_transfer_guard_target(race, e, h):
            transfer.append(n)

        if debut_warning_target(e, h):
            debut.append(n)

        # 初距離は強制加入なし
        if p["exact_count"] == 0 and (
            p["other_track_same_dist"] or p["adjacent_same_track"] or p["adjacent_other"]
        ):
            first_distance.append(n)

        # 監視：同場同距離の絶対時計TOP3級だが、最良着差が0.4〜1.5
        m = p["exact_best_margin"]
        if (
            p["exact_best"] is not None
            and exact_ranks[n] <= 3
            and m is not None
            and 0.3 < m <= 1.5
        ):
            fast_big.append(n)

    return {
        "absolute": absolute,
        "boundary": boundary,
        "transfer": transfer,
        "debut": debut,
        "first_distance": first_distance,
        "fast_big_margin": fast_big,
    }



def apply_top6_guards(base_order: List[int], guards: Dict[str, List[int]]) -> List[int]:
    target_len = min(6, len(base_order))
    top6 = list(base_order[:target_len])

    def force(n: int):
        nonlocal top6
        if n in top6:
            return
        if top6:
            top6[-1] = n

    for key in ["transfer", "absolute", "boundary"]:
        for n in guards[key]:
            force(n)

    # 重複除去して時計順で補充
    clean = []
    for n in top6:
        if n not in clean:
            clean.append(n)
    for n in base_order:
        if len(clean) >= target_len:
            break
        if n not in clean:
            clean.append(n)
    return clean


def pick_four(base_order: List[int], top6: List[int], profiles: Dict[int, Dict],
              guards: Dict[str, List[int]]) -> Tuple[List[int], Dict[int, str]]:
    selected, roles = [], {}

    def add(n: Optional[int], role: str):
        if n is not None and n not in selected and len(selected) < 4:
            selected.append(n)
            roles[n] = role

    add(base_order[0] if base_order else None, "時計TOP1")
    add(base_order[1] if len(base_order) > 1 else None, "時計TOP2")

    # 3頭目：上昇度＋再現性
    rem = [n for n in top6 if n not in selected]
    if rem:
        def rise_key(n: int):
            p = profiles[n]
            repeat = (
                p["exact_close_count"] * 2
                + p["exact_win_count"] * 2
                + p["exact_competitive"]
            )
            imp = -999.0 if p["improvement"] is None else p["improvement"]
            return (repeat, imp, -base_order.index(n))

        up = max(rem, key=rise_key)
        add(up, "上昇度・再現性")

    # 4頭目：
    # 「クラス突出」だけで一発実績馬を上げすぎず、
    # 同場同距離の再現性・同馬場実績を合わせる。
    rem = [n for n in top6 if n not in selected]
    if rem:
        def class_repeat_key(n: int):
            p = profiles[n]
            consistency = (
                p["exact_competitive"] * 2
                + p["going_competitive"] * 2
                + min(p["exact_count"], 3)
            )
            return (
                consistency,
                p["class_best"],
                -base_order.index(n),
            )

        cls = max(rem, key=class_repeat_key)
        add(cls, "クラス・再現性")

    for n in top6:
        if len(selected) >= 4:
            break
        add(n, "時計上位補完")

    # 地方転入人気馬ガード
    for n in guards["transfer"]:
        if n not in selected and selected:
            repl = None
            for i in range(len(selected) - 1, -1, -1):
                if roles[selected[i]] not in {"時計TOP1", "時計TOP2"}:
                    repl = i
                    break
            if repl is not None:
                old = selected[repl]
                selected[repl] = n
                roles.pop(old, None)
                roles[n] = "地方転入人気馬ガード"

    selected = sorted(selected[:4], key=lambda n: base_order.index(n))
    return selected, roles




def evaluation_text(race: RaceInfo, p: Dict) -> str:
    bits = []

    if p["exact_best"] is not None:
        bits.append(f"{race.track}{race.distance}m {format_time(p['exact_best'])}")
        if p["exact_best_margin"] is not None:
            bits.append(f"ベスト時計時着差 {p['exact_best_margin']:.1f}")
        if p["exact_quality_time"] is not None:
            bits.append(f"着差補正 {format_time(p['exact_quality_time'])}")
    elif p["other_same_dist_best"] is not None:
        bits.append(f"別場{race.distance}m参考 {format_time(p['other_same_dist_best'])}")
        bits.append("別場生時計は直接比較せず")
    elif p["adjacent_same_track_best"] is not None:
        bits.append(f"同場隣接距離参考 {format_time(p['adjacent_same_track_best'])}")

    if p["exact_recent"] is not None:
        bits.append(f"直近同場同距離 {format_time(p['exact_recent'])}")
    if p["exact_second"] is not None:
        bits.append(f"2本目 {format_time(p['exact_second'])}")
    if p["exact_close_count"]:
        bits.append(f"同場0.3以内 {p['exact_close_count']}回")
    if p["exact_win_count"]:
        bits.append(f"同場同距離勝 {p['exact_win_count']}回")

    return " / ".join(bits) if bits else "同場同距離の時計材料なし"




def build_clock_prediction(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory],
                           race_date: date) -> Dict:
    if len(entries) < 3:
        raise ValueError("出馬表から3頭以上を読み取れませんでした。")

    profiles = build_profiles(race, entries, histories)
    base_order = base_clock_order(race, profiles, race_date)
    guards = guard_lists(race, entries, histories, profiles, base_order)
    top6 = apply_top6_guards(base_order, guards)


    four, roles = pick_four(base_order, top6, profiles, guards)
    by_num = {e.number: e for e in entries}

    four_rows = [{
        "馬番": n, "馬名": by_num[n].name, "役割": roles.get(n, ""),
        "評価": evaluation_text(race, profiles[n])
    } for n in four]

    top6_rows = [{
        "時計順位": i, "馬番": n, "馬名": by_num[n].name,
        "同場同距離": format_time(profiles[n]["exact_best"]),
        "ベスト時計時着差": "—" if profiles[n]["exact_best_margin"] is None else f"{profiles[n]['exact_best_margin']:.1f}",
        "着差補正時計": format_time(profiles[n]["exact_quality_time"]),
        "別場同距離参考": format_time(profiles[n]["other_same_dist_best"]),
        "直近同場同距離": format_time(profiles[n]["exact_recent"]),
        "2本目": format_time(profiles[n]["exact_second"]),
        "最小着差": "—" if profiles[n]["best_margin"] is None else f"{profiles[n]['best_margin']:.1f}",
        "同場0.3以内": profiles[n]["exact_close_count"],
        "同場同距離勝": profiles[n]["exact_win_count"],
        "評価": evaluation_text(race, profiles[n]),
    } for i, n in enumerate(top6, 1)]

    if len(entries) <= 6:
        status = "参考・ノーカウント"
    elif len(entries) == 7:
        status = "参考"
    else:
        status = "本集計"

    return {
        "race": asdict(race),
        "race_date": race_date.isoformat(),
        "base_order": base_order,
        "four": four,
        "four_rows": four_rows,
        "top6": top6,
        "top6_rows": top6_rows,
        "top6_status": status,
        "guards": guards,
        "entries": [asdict(e) for e in entries],
    }


# ============================================================
# 結果検証
# ============================================================

def parse_result(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", text)][:6]


def verify_result(pred: Dict, result_text: str) -> Dict:
    result = parse_result(result_text)
    if len(result) < 3:
        raise ValueError("結果は『7-5-10』のように1〜3着まで入力してください。")

    podium = result[:3]
    four = set(map(int, pred["four"]))
    top6 = set(map(int, pred["top6"]))
    four_hits = sum(n in four for n in podium)
    top6_hits = sum(n in top6 for n in podium)

    def guard_result(nums):
        return "・".join(f"{n}:{podium.index(n)+1 if n in podium else '圏外'}" for n in nums)

    g = pred["guards"]
    return {
        "日付": pred["race_date"],
        "レース": pred["race"].get("race_name", ""),
        "競馬場": pred["race"].get("track", ""),
        "条件": f"{pred['race'].get('surface','')}{pred['race'].get('distance',0)}m",
        "頭数": len(pred["entries"]),
        "結果": "-".join(map(str, result)),
        "4頭": "・".join(map(str, pred["four"])),
        "4頭勝ち馬": "○" if result[0] in four else "×",
        "4頭馬券内2頭以上": "○" if four_hits >= 2 else "×",
        "4頭1・2着": "○" if result[0] in four and result[1] in four else "×",
        "4頭馬券内数": f"{four_hits}/3",
        "時計TOP6": "・".join(map(str, pred["top6"])),
        "TOP6集計区分": pred["top6_status"],
        "TOP6馬券内": f"{top6_hits}/3",
        "TOP6完全捕捉": "○" if top6_hits == 3 else "×",
        "絶対時計ガード": guard_result(g["absolute"]),
        "境界ガード": guard_result(g["boundary"]),
        "地方転入ガード": guard_result(g["transfer"]),
        "初出走警戒": guard_result(g["debut"]),
        "初距離警戒": guard_result(g["first_distance"]),
        "高速時計大差負け監視": guard_result(g["fast_big_margin"]),
    }


# ============================================================
# UI
# ============================================================

APP_NAME = "競馬AI 時計分析 v3.5"
st.set_page_config(page_title=APP_NAME, page_icon="⏱️", layout="wide")
st.title("⏱️ 競馬AI 時計分析 v3.5")
st.caption("時計分析単独｜4頭絞り【2連系用】＋時計TOP6【三連系用】＋検証ガード")

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
    st.subheader("現行ルール")
    st.markdown("""
- 人気・オッズは時計順位に不使用
- 固定AXIS / 相手C / ハイブリッドは廃止
- **同場同距離**の実時計＋着差＋再現性＋直近性
- 別競馬場の同距離生時計は直接比較しない
- 4頭＝TOP1＋TOP2＋上昇度＋クラス突出
- 絶対時計 / 境界 / 地方転入ガード
- 初出走・初距離は警戒表示のみ
""")

pred_tab, hist_tab, rule_tab = st.tabs(["予想・結果検証", "検証履歴", "ルール"])

with pred_tab:
    st.subheader("① 入力")
    race_date = st.date_input("レース日", value=date.today(), key="race_date_input")
    c1, c2, c3 = st.columns(3)
    with c1:
        race_text = st.text_area("レース情報", height=220, key="race_text_input")
    with c2:
        entry_text = st.text_area("出馬表", height=220, key="entry_text_input")
    with c3:
        history_text = st.text_area("馬柱", height=220, key="history_text_input")

    b1, b2 = st.columns(2)
    with b1:
        predict_clicked = st.button("時計分析する（事前固定）", type="primary", use_container_width=True)
    with b2:
        st.button("入力・予想をクリア", use_container_width=True, on_click=clear_prediction_inputs)

    if predict_clicked:
        race = parse_race_info(race_text)
        entries = parse_entries(entry_text)
        histories = parse_horse_histories(history_text, entries)
        problems = []
        if not race.surface or not race.distance:
            problems.append("芝/ダート・距離を取得できませんでした。")
        if not race.track:
            problems.append("競馬場を取得できませんでした。")
        if len(entries) < 3:
            problems.append("出馬表を十分に解析できませんでした。")
        if len(histories) < min(len(entries), 3):
            problems.append("馬柱解析頭数が不足しています。")
        st.caption(f"解析：出馬表 {len(entries)}頭 / 馬柱 {len(histories)}頭")
        if problems:
            st.error("\n".join(problems))
        else:
            try:
                pred = build_clock_prediction(race, entries, histories, race_date)
                st.session_state.locked_prediction = pred
                st.success("事前分析を固定しました。結果入力時に再計算しません。")
            except Exception as e:
                st.error(f"分析エラー: {e}")

    pred = st.session_state.locked_prediction
    if pred:
        st.divider()
        st.subheader("② 事前固定")
        st.success("4頭絞り【2連系用】： " + "・".join(map(str, pred["four"])))
        st.info(f"時計TOP6【三連系用】： {'・'.join(map(str, pred['top6']))}｜{pred['top6_status']}")

        st.markdown("### 4頭絞り")
        st.dataframe(pd.DataFrame(pred["four_rows"]), use_container_width=True, hide_index=True)

        st.markdown("### 時計TOP6")
        st.dataframe(pd.DataFrame(pred["top6_rows"]), use_container_width=True, hide_index=True)

        g = pred["guards"]
        st.markdown("### ガード・警戒")
        st.write("**絶対時計ガード**：" + ("・".join(map(str, g["absolute"])) if g["absolute"] else "該当なし"))
        st.write("**絶対時計・境界ガード**：" + ("・".join(map(str, g["boundary"])) if g["boundary"] else "該当なし"))
        st.write("**地方転入人気馬ガード**：" + ("・".join(map(str, g["transfer"])) if g["transfer"] else "該当なし"))
        st.write("**初出走警戒**：" + ("・".join(map(str, g["debut"])) if g["debut"] else "該当なし"))
        st.write("**初距離警戒**：" + ("・".join(map(str, g["first_distance"])) if g["first_distance"] else "該当なし"))
        st.write("**高速時計＋大差負け監視**：" + ("・".join(map(str, g["fast_big_margin"])) if g["fast_big_margin"] else "該当なし"))

        st.divider()
        st.subheader("③ 結果検証")
        result_text = st.text_input("着順", placeholder="例：7-5-10", key="result_text_input")
        if st.button("結果を照合して履歴に保存", use_container_width=True):
            try:
                record = verify_result(pred, result_text)
                st.session_state.history.append(record)
                st.success(
                    f"結果 {record['結果']}｜4頭勝ち馬 {record['4頭勝ち馬']}｜"
                    f"4頭1・2着 {record['4頭1・2着']}｜TOP6 {record['TOP6馬券内']}"
                )
            except Exception as e:
                st.error(str(e))

with hist_tab:
    st.subheader("検証履歴")
    uploaded = st.file_uploader("過去検証CSVを読み込む", type=["csv"])
    if uploaded is not None:
        try:
            df_import = pd.read_csv(uploaded)
            if st.button("CSVを履歴に読み込む"):
                st.session_state.history = df_import.fillna("").to_dict("records")
                st.rerun()
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")

    if st.session_state.history:
        hdf = pd.DataFrame(st.session_state.history)
        st.dataframe(hdf, use_container_width=True, hide_index=True)

        total4 = len(hdf)
        win4 = int((hdf["4頭勝ち馬"] == "○").sum())
        two4 = int((hdf["4頭馬券内2頭以上"] == "○").sum())
        exact12 = int((hdf["4頭1・2着"] == "○").sum())

        counted = hdf[hdf["TOP6集計区分"] == "本集計"] if "TOP6集計区分" in hdf else hdf
        nr = len(counted)
        top6_hits = sum(int(str(x).split("/")[0]) for x in counted["TOP6馬券内"]) if nr else 0
        top6_full = int((counted["TOP6完全捕捉"] == "○").sum()) if nr else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("4頭 勝ち馬捕捉", f"{win4}/{total4}")
        c2.metric("4頭 馬券内2頭以上", f"{two4}/{total4}")
        c3.metric("4頭 1・2着両捕捉", f"{exact12}/{total4}")
        c4, c5 = st.columns(2)
        c4.metric("TOP6 馬券内", f"{top6_hits}/{nr*3}" if nr else "0/0")
        c5.metric("TOP6 完全捕捉", f"{top6_full}/{nr}" if nr else "0/0")

        csv_bytes = hdf.to_csv(index=False).encode("utf-8-sig")
        st.download_button("検証履歴CSVをダウンロード", data=csv_bytes,
                           file_name="keiba_clock_v3_history.csv",
                           mime="text/csv", use_container_width=True)
        if st.button("履歴を全削除"):
            st.session_state.history = []
            st.rerun()
    else:
        st.info("まだ検証履歴はありません。")

with rule_tab:
    st.subheader("時計分析 v3.5")
    st.markdown("""
### ベース
- **同競馬場・同距離の実時計を最優先**
- 別競馬場の同距離生時計は秒数で直接比較しない
- 同場同距離が無い場合のみ別場同距離・隣接距離を補助
- 速い時計でも1.0秒超の大差負けは強く抑える
- 同距離実時計
- 着差
- 直近性
- 再現性
- 上昇度
- クラス
- 同距離材料が薄い場合のみ隣接距離

### 4頭絞り
**時計TOP1 + 時計TOP2 + 上昇度突出 + クラス突出**

### ガード
- 絶対時計：同距離TOP3級 + 勝利 / 0.3秒以内
- 境界：通常7〜8位 + 同距離勝利 / 0.3秒以内
- 地方転入人気馬：転入初戦相当 + JRA/南関等 + 3番人気以内
- 初出走：5番人気以内を警戒表示
- 初距離：隣接距離材料がある場合に警戒表示
- 高速時計＋0.4〜1.5秒差は監視対象として記録し、現時点では強制加入しない

### 少頭数
- 6頭以下：TOP6参考・ノーカウント
- 7頭：参考
- 8頭以上：本集計

### 不使用
固定AXIS / 相手C / ハイブリッド / 枠順補正 / 脚質補正 /
騎手 / 調教師 / 血統 / 人気補正 / オッズ補正 / 当日馬場傾向補正
""")
