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






# ============================================================
# 時計TOP6 完全共通ルール v1.1【凍結版】
# ============================================================

RULESET_ID = "CLOCK_TOP6_COMMON_V1_1_FROZEN_2026-08-13"
RULESET_NAME = "時計TOP6 完全共通ルール v1.1【固定・変更禁止】"
IMPLEMENTATION_REV = "impl2"

RULESET_TEXT = """
【目的】
レース前のレース情報・出馬表・馬柱だけを使い、時計面から馬券内候補TOP6を選ぶ。
人気・オッズは通常時計順位には使用しない。
固定AXIS・相手C・総合指数・騎手・調教師・血統・枠順・展開補正は不使用。

【2段階処理】
第1エンジン：ガードを使わず通常時計順位1〜8位を作る。
第2エンジン：絶対時計・境界・地方転入人気馬ガードを最後に適用し最終TOP6を固定する。

【通常時計分析】
1. 同場同距離を最優先。
2. ベスト時計と、その時計を出した時の着差を必ずセットで評価。
3. 勝利・0.3秒差以内を最重要の好走証拠とする。
4. 0.4〜0.6、0.7〜1.0、1.1〜1.5、それ以上の順で評価を下げる。
5. 単発の高速時計より、同水準を複数回出した再現性を重視。
6. 同程度なら直近性を優先。ただし古い強い時計は完全には消さない。
7. 高速時計でも大差負けを繰り返す場合は過大評価しない。
8. 別競馬場の生時計は秒数だけで直接比較しない。
9. クラスは単独加点ではなく「高クラス＋小差」の時計価値として評価。
10. 同距離材料が弱い時のみ隣接距離を補助に使う。
11. 弱い直接距離実績より、強い隣接距離実績を上にできる。

【JRA 1600〜1800m】
別場生時計を直接比較しない。
同距離での小差好走 → 高クラスでの好内容 → 再現性 → 直近性を先に比較。
同場同距離の実時計は重要なタイブレーク材料として使う。
高クラスでも大差負けだけなら上げない。

【地方競馬】
同競馬場・同距離の実時計比較を中央より強く重視。
同場同距離のベスト時計＋着差＋再現性＋直近性で順位を作る。
別場の生時計は直接比較しない。

【2000m以上】
直接距離実績を強く重視。
ただし同距離で大差負けしかない「弱い直接実績」は保護しない。
強い隣接距離実績が弱い直接実績を上回ることを認める。

【絶対時計ガード】
同場同距離の絶対時計がメンバーTOP3級、
かつ勝利または0.3秒差以内ならTOP6から落とさない。

【境界ガード】
通常7〜8位付近で、
同距離勝利または0.3秒差以内、
かつ時計がTOP6境界から大きく劣らない馬を6番手へ保護。
境界ガードだけを理由に上位順位へ上げない。

【地方転入人気馬ガード】
地方転入初戦＋直近がJRA/南関など上位環境＋当日3番人気以内。
通常TOP6外なら6番手へ保護。
人気を通常時計順位には使わない。

【警戒表示のみ】
初出走＋5番人気以内。
初距離＋隣接距離に強い内容。
高速時計＋大差負け。
これらは単独でTOP6へ強制加入させない。

【少頭数】
6頭以下：TOP6＝全頭、参考・ノーカウント。
7頭：参考。
8頭以上：本集計。

【変更禁止】
検証で新しい改善案が出ても、このv1.1自体は上書きしない。
改善はv1.2候補として別管理し、採用時は別バージョンを新規作成する。
"""


# ============================================================
# v1.1 evidence helpers
# ============================================================

def _days_since(r: PastRace, race_date: date) -> int:
    if r.race_date is None:
        return 9999
    return max(0, (race_date - r.race_date).days)


def _margin_level(m: Optional[float]) -> int:
    """
    大きいほど強い。
    5: 勝利/0.3以内
    4: 0.6以内
    3: 1.0以内
    2: 1.5以内
    1: 2.5以内
    0: それ以上/不明
    """
    if m is None:
        return 0
    if m <= 0.3:
        return 5
    if m <= 0.6:
        return 4
    if m <= 1.0:
        return 3
    if m <= 1.5:
        return 2
    if m <= 2.5:
        return 1
    return 0


def _recency_level(days: int) -> int:
    if days <= 30:
        return 5
    if days <= 60:
        return 4
    if days <= 100:
        return 3
    if days <= 180:
        return 2
    if days <= 365:
        return 1
    return 0


def _run_content_key(r: PastRace, race_date: date) -> Tuple:
    """
    生時計を競馬場横断で比較せず、
    着差→(小差時のみ)クラス→直近性→着順の順で走りの価値を表す。
    """
    ml = _margin_level(r.margin)
    class_when_competitive = r.class_rank if ml >= 3 else -2
    finish_score = 0
    if r.finish == 1:
        finish_score = 3
    elif r.finish == 2:
        finish_score = 2
    elif r.finish == 3:
        finish_score = 1
    return (
        ml,
        class_when_competitive,
        _recency_level(_days_since(r, race_date)),
        finish_score,
    )


def _evidence(rs: List[PastRace], race_date: date) -> Dict:
    valid = [r for r in rs if r.time_seconds is not None]
    if not valid:
        return {
            "count": 0,
            "best_time": None,
            "second_time": None,
            "best_clock_margin": None,
            "best_clock_date": None,
            "best_content": (-1, -9, -1, -1),
            "second_content": (-1, -9, -1, -1),
            "win_count": 0,
            "close03": 0,
            "close06": 0,
            "close10": 0,
            "close15": 0,
            "class_close03": -2,
            "class_close10": -2,
            "latest_comp_days": 9999,
            "latest_strong_days": 9999,
            "weak_direct": True,
            "repeat_score": 0,
        }

    by_time = sorted(valid, key=lambda r: r.time_seconds)
    best_clock = by_time[0]

    by_content = sorted(
        valid,
        key=lambda r: _run_content_key(r, race_date),
        reverse=True,
    )
    best_content = _run_content_key(by_content[0], race_date)
    second_content = (
        _run_content_key(by_content[1], race_date)
        if len(by_content) >= 2
        else (-1, -9, -1, -1)
    )

    close03_runs = [r for r in valid if r.margin is not None and r.margin <= 0.3]
    close06_runs = [r for r in valid if r.margin is not None and r.margin <= 0.6]
    close10_runs = [r for r in valid if r.margin is not None and r.margin <= 1.0]
    close15_runs = [r for r in valid if r.margin is not None and r.margin <= 1.5]

    latest_comp_days = min(
        [_days_since(r, race_date) for r in close10_runs],
        default=9999,
    )
    latest_strong_days = min(
        [_days_since(r, race_date) for r in close03_runs],
        default=9999,
    )

    # 同水準を繰り返していることを再現性として扱う。
    repeat_score = (
        len(close03_runs) * 4
        + max(0, len(close06_runs) - len(close03_runs)) * 2
        + max(0, len(close10_runs) - len(close06_runs))
        + sum(1 for r in valid if r.finish == 1) * 2
    )

    # 直接距離経験があっても、全て大差負けなら「弱い直接実績」。
    known_margins = [r.margin for r in valid if r.margin is not None]
    weak_direct = bool(known_margins) and min(known_margins) > 2.5

    return {
        "count": len(valid),
        "best_time": by_time[0].time_seconds,
        "second_time": by_time[1].time_seconds if len(by_time) >= 2 else None,
        "best_clock_margin": best_clock.margin,
        "best_clock_date": best_clock.race_date,
        "best_content": best_content,
        "second_content": second_content,
        "win_count": sum(1 for r in valid if r.finish == 1),
        "close03": len(close03_runs),
        "close06": len(close06_runs),
        "close10": len(close10_runs),
        "close15": len(close15_runs),
        "class_close03": max([r.class_rank for r in close03_runs], default=-2),
        "class_close10": max([r.class_rank for r in close10_runs], default=-2),
        "latest_comp_days": latest_comp_days,
        "latest_strong_days": latest_strong_days,
        "weak_direct": weak_direct,
        "repeat_score": repeat_score,
    }


def _quality_clock_key(ev: Dict) -> Tuple:
    """
    同場同距離でのみ使う実時計比較。
    ベスト時計を主役に残しつつ、その時計時着差・再現性をセット評価。
    lower is better.
    """
    bt = ev["best_time"]
    if bt is None:
        return (9999.0, 9999.0, 9999, 9999)

    m = ev["best_clock_margin"]
    adjusted = bt + margin_penalty(m)

    return (
        adjusted,
        bt,
        -ev["repeat_score"],
        ev["latest_comp_days"],
    )


def _adjacent_strength(rs: List[PastRace], race_date: date) -> Tuple:
    ev = _evidence(rs, race_date)
    return (
        ev["best_content"],
        ev["repeat_score"],
        -ev["latest_comp_days"],
    )



def _shared_race_benchmark(
    race: RaceInfo,
    profiles: Dict[int, Dict],
    race_date: date,
) -> Dict[int, Tuple]:
    """
    同じ過去レースに今回の出走馬が複数いた場合、そのレースは完全に同一条件なので
    直接比較できる「共通物差し」として使う。

    特にJRA1600〜1800mでは、別場生時計の横比較より信頼度が高い。
    戻り値は horse_number -> benchmark tuple。
    tupleは小さいほど強い。
    """
    groups = {}

    for n, p in profiles.items():
        for r in p["same_dist"]:
            if r.time_seconds is None or r.race_date is None:
                continue
            key = (
                r.race_date,
                r.track,
                r.race_name,
                r.surface,
                r.distance,
            )
            groups.setdefault(key, []).append((n, r))

    out = {}

    for key, members in groups.items():
        unique_nums = {n for n, _ in members}
        if len(unique_nums) < 2:
            continue

        # 同じレースなので実時計を直接比較してよい。
        ordered = sorted(
            members,
            key=lambda x: (
                x[1].time_seconds,
                999 if x[1].finish is None else x[1].finish,
            ),
        )

        participants = len(unique_nums)
        for direct_rank, (n, r) in enumerate(ordered, 1):
            # 今回と同クラス以上の共通レースを最優先。
            class_gap = max(0, race.class_rank - r.class_rank)
            margin_bad = 0
            if r.margin is not None:
                if r.margin <= 1.0:
                    margin_bad = 0
                elif r.margin <= 1.5:
                    margin_bad = 1
                elif r.margin <= 2.0:
                    margin_bad = 2
                else:
                    margin_bad = 4
            else:
                margin_bad = 2

            candidate = (
                class_gap,
                margin_bad,
                -participants,              # 3頭共通 > 2頭共通
                direct_rank,                # 同じレース内の直接順位
                _days_since(r, race_date),
            )

            if n not in out or candidate < out[n]:
                out[n] = candidate

    return out


def _jra_same_distance_strength(
    race: RaceInfo,
    p: Dict,
    race_date: date,
) -> Tuple:
    """
    JRA1600〜1800mの「時計価値」。

    v1.1の意図どおり、
    ・今回と同クラス以上で競争になっている同距離実績
    ・再現性
    ・直近性
    を、下級条件の勝利より先に見る。
    """
    runs = [
        r for r in p["same_dist"]
        if r.time_seconds is not None
    ]

    if not runs:
        return (9, 9, 999, 999, 999)

    # 今回と同クラス以上で、大敗ではない走り
    relevant = [
        r for r in runs
        if r.class_rank >= race.class_rank
        and (r.margin is None or r.margin <= 2.0)
    ]

    if relevant:
        ev = _evidence(relevant, race_date)
        return (
            0,
            -ev["repeat_score"],
            ev["latest_comp_days"],
            -ev["class_close10"],
            tuple(-x for x in ev["best_content"]),
        )

    # 1クラス下でも小差・再現性が高ければ次点
    lower_close = [
        r for r in runs
        if r.class_rank >= race.class_rank - 1
        and r.margin is not None
        and r.margin <= 1.0
    ]
    if lower_close:
        ev = _evidence(lower_close, race_date)
        return (
            1,
            -ev["repeat_score"],
            ev["latest_comp_days"],
            -ev["class_close10"],
            tuple(-x for x in ev["best_content"]),
        )

    # その他の同距離
    ev = _evidence(runs, race_date)
    return (
        2,
        -ev["repeat_score"],
        ev["latest_comp_days"],
        -ev["class_close10"],
        tuple(-x for x in ev["best_content"]),
    )


# ============================================================
# 第1エンジン：通常時計順位
# ============================================================

def _normal_key_jra_middle(
    race: RaceInfo,
    p: Dict,
    race_date: date,
    shared_benchmark: Optional[Tuple] = None,
) -> Tuple:
    """
    JRA 1600〜1800m。

    1) 今回と同クラス以上で競争になった同距離実績
    2) 同じ過去レースでの直接比較（共通物差し）
    3) 再現性・直近性
    4) 同場同距離時計は補助

    別競馬場の生時計だけを横並びにはしない。
    """
    same_ev = _evidence(p["same_dist"], race_date)
    exact_ev = _evidence(p["exact"], race_date)
    adjacent = p["adjacent_same_track"] + p["adjacent_other"]
    adj_ev = _evidence(adjacent, race_date)

    if same_ev["count"] > 0 and not same_ev["weak_direct"]:
        strength = _jra_same_distance_strength(race, p, race_date)

        # 共通レースがある場合は、同一条件の直接比較を強いタイブレークにする。
        # 無い馬を機械的に落とさないよう、strengthの後に置く。
        shared_key = shared_benchmark if shared_benchmark is not None else (9, 9, 9, 99, 9999)

        return (
            0,
            strength,
            shared_key,
            -same_ev["repeat_score"],
            same_ev["latest_comp_days"],
            0 if exact_ev["count"] > 0 else 1,
            _quality_clock_key(exact_ev),
            p["entry"].number,
        )

    # 強い隣接距離は弱い直接実績を上回れる
    if adj_ev["count"] > 0 and adj_ev["best_content"][0] >= 3:
        return (
            1,
            tuple(-x for x in adj_ev["best_content"]),
            -adj_ev["repeat_score"],
            adj_ev["latest_comp_days"],
            p["entry"].number,
        )

    if same_ev["count"] > 0:
        return (
            2,
            _jra_same_distance_strength(race, p, race_date),
            -same_ev["repeat_score"],
            same_ev["latest_comp_days"],
            _quality_clock_key(exact_ev),
            p["entry"].number,
        )

    if adj_ev["count"] > 0:
        return (
            3,
            tuple(-x for x in adj_ev["best_content"]),
            -adj_ev["repeat_score"],
            adj_ev["latest_comp_days"],
            p["entry"].number,
        )

    return (9, p["entry"].number)



def _normal_key_2000plus(
    race: RaceInfo,
    p: Dict,
    race_date: date,
) -> Tuple:
    """
    2000m以上:
    直接距離実績を強く重視。
    ただし大差負けしかない弱い直接実績は、強い隣接距離に負ける。
    """
    exact_ev = _evidence(p["exact"], race_date)
    other_ev = _evidence(p["other_track_same_dist"], race_date)
    same_ev = _evidence(p["same_dist"], race_date)
    adj_same_ev = _evidence(p["adjacent_same_track"], race_date)
    adj_other_ev = _evidence(p["adjacent_other"], race_date)

    # 強い同場同距離
    if exact_ev["count"] > 0 and not exact_ev["weak_direct"]:
        return (
            0,
            _quality_clock_key(exact_ev),
            -exact_ev["repeat_score"],
            exact_ev["latest_comp_days"],
            -exact_ev["class_close10"],
            p["entry"].number,
        )

    # 同場は無いが、別場同距離で競走内容が強い
    if other_ev["count"] > 0 and not other_ev["weak_direct"]:
        return (
            1,
            tuple(-x for x in other_ev["best_content"]),
            -other_ev["repeat_score"],
            other_ev["latest_comp_days"],
            -other_ev["class_close10"],
            p["entry"].number,
        )

    # 強い隣接距離は、弱い直接距離実績を上回れる
    best_adj = adj_same_ev
    adj_group = 2
    if adj_other_ev["best_content"] > adj_same_ev["best_content"]:
        best_adj = adj_other_ev
        adj_group = 3

    if best_adj["count"] > 0 and best_adj["best_content"][0] >= 4:
        return (
            adj_group,
            tuple(-x for x in best_adj["best_content"]),
            -best_adj["repeat_score"],
            best_adj["latest_comp_days"],
            p["entry"].number,
        )

    # 弱い直接実績
    if same_ev["count"] > 0:
        return (
            4,
            tuple(-x for x in same_ev["best_content"]),
            -same_ev["repeat_score"],
            same_ev["latest_comp_days"],
            p["entry"].number,
        )

    if best_adj["count"] > 0:
        return (
            5,
            tuple(-x for x in best_adj["best_content"]),
            -best_adj["repeat_score"],
            best_adj["latest_comp_days"],
            p["entry"].number,
        )

    return (9, p["entry"].number)


def _normal_key_local_or_other(
    race: RaceInfo,
    p: Dict,
    race_date: date,
) -> Tuple:
    """
    地方・その他:
    同場同距離のベスト時計＋その着差＋再現性＋直近性を主役にする。
    別場同距離は生時計を直接比較しない。
    """
    exact_ev = _evidence(p["exact"], race_date)
    other_ev = _evidence(p["other_track_same_dist"], race_date)
    adj_same_ev = _evidence(p["adjacent_same_track"], race_date)
    adj_other_ev = _evidence(p["adjacent_other"], race_date)

    if exact_ev["count"] > 0 and not exact_ev["weak_direct"]:
        return (
            0,
            _quality_clock_key(exact_ev),
            -exact_ev["repeat_score"],
            exact_ev["latest_comp_days"],
            -exact_ev["class_close10"],
            # 今回と同馬場の直接実績を補助
            0 if p["exact_going"] else 1,
            p["entry"].number,
        )

    # 同場同距離が大差負けしかない場合、
    # 強い別場同距離/隣接距離が上回ることを認める。
    if other_ev["count"] > 0 and other_ev["best_content"][0] >= 4:
        return (
            1,
            tuple(-x for x in other_ev["best_content"]),
            -other_ev["repeat_score"],
            other_ev["latest_comp_days"],
            -other_ev["class_close10"],
            p["entry"].number,
        )

    if adj_same_ev["count"] > 0 and adj_same_ev["best_content"][0] >= 4:
        return (
            2,
            tuple(-x for x in adj_same_ev["best_content"]),
            -adj_same_ev["repeat_score"],
            adj_same_ev["latest_comp_days"],
            p["entry"].number,
        )

    if exact_ev["count"] > 0:
        return (
            3,
            _quality_clock_key(exact_ev),
            -exact_ev["repeat_score"],
            exact_ev["latest_comp_days"],
            p["entry"].number,
        )

    if other_ev["count"] > 0:
        return (
            4,
            tuple(-x for x in other_ev["best_content"]),
            -other_ev["repeat_score"],
            other_ev["latest_comp_days"],
            p["entry"].number,
        )

    if adj_same_ev["count"] > 0:
        return (
            5,
            tuple(-x for x in adj_same_ev["best_content"]),
            -adj_same_ev["repeat_score"],
            adj_same_ev["latest_comp_days"],
            p["entry"].number,
        )

    if adj_other_ev["count"] > 0:
        return (
            6,
            tuple(-x for x in adj_other_ev["best_content"]),
            -adj_other_ev["repeat_score"],
            adj_other_ev["latest_comp_days"],
            p["entry"].number,
        )

    return (9, p["entry"].number)


def normal_clock_order(
    race: RaceInfo,
    profiles: Dict[int, Dict],
    race_date: date,
) -> List[int]:
    """
    v1.1の第1エンジン。
    人気・オッズ・ガードを一切使わず、通常時計順位を作る。
    """
    nums = list(profiles.keys())

    if race.track in JRA_TRACKS and 1600 <= race.distance <= 1800:
        shared = _shared_race_benchmark(race, profiles, race_date)
        return sorted(
            nums,
            key=lambda n: _normal_key_jra_middle(
                race,
                profiles[n],
                race_date,
                shared.get(n),
            ),
        )

    if race.distance >= 2000:
        return sorted(
            nums,
            key=lambda n: _normal_key_2000plus(race, profiles[n], race_date),
        )

    return sorted(
        nums,
        key=lambda n: _normal_key_local_or_other(race, profiles[n], race_date),
    )


# ============================================================
# 第2エンジン：ガード
# ============================================================

def _raw_exact_rank(profiles: Dict[int, Dict]) -> Dict[int, int]:
    pairs = sorted(
        [
            (n, p["exact_best"])
            for n, p in profiles.items()
            if p["exact_best"] is not None
        ],
        key=lambda x: x[1],
    )
    return {n: i + 1 for i, (n, _) in enumerate(pairs)}


def guard_lists_v1_1(
    race: RaceInfo,
    entries: List[Entry],
    histories: Dict[int, HorseHistory],
    profiles: Dict[int, Dict],
    normal_order: List[int],
    race_date: date,
) -> Dict[str, List[int]]:
    by_num = {e.number: e for e in entries}
    pos = {n: i + 1 for i, n in enumerate(normal_order)}
    raw_rank = _raw_exact_rank(profiles)

    absolute = []
    boundary = []
    transfer = []
    debut = []
    first_distance = []
    fast_big_margin = []

    # 「境界から大きく劣らない」は固定秒差ではなく、
    # 同場同距離の時計順位分布で判定する。
    exact_count = len(raw_rank)
    boundary_raw_rank_limit = min(
        8,
        max(6, (exact_count + 1) // 2),
    ) if exact_count else 0

    for n in normal_order:
        p = profiles[n]
        e = by_num[n]
        h = histories.get(n)
        exact_ev = _evidence(p["exact"], race_date)
        same_ev = _evidence(p["same_dist"], race_date)

        # 絶対時計：
        # 同場同距離TOP3級＋0.3以内が基本。
        # JRA1600〜1800mでは、単に新潟持ち時計上位というだけでは不足。
        # 今回同クラス以上で0.3以内の同距離実績があることも確認する。
        absolute_ok = (
            n in raw_rank
            and raw_rank[n] <= 3
            and exact_ev["close03"] > 0
        )

        if absolute_ok and race.track in JRA_TRACKS and 1600 <= race.distance <= 1800:
            same_class_close03 = any(
                r.time_seconds is not None
                and r.class_rank >= race.class_rank
                and r.margin is not None
                and r.margin <= 0.3
                for r in p["same_dist"]
            )
            absolute_ok = same_class_close03

        if absolute_ok:
            absolute.append(n)

        # 境界：通常7〜8位＋同距離勝/0.3以内＋時計分布でも境界圏
        # 同場同距離がある場合はその生時計順位で確認。
        if pos[n] in {7, 8} and same_ev["close03"] > 0:
            close_enough = False

            if n in raw_rank:
                close_enough = raw_rank[n] <= boundary_raw_rank_limit
            else:
                # 別場同距離しか無い時は生時計横比較をせず、
                # 小差実績の再現性が2本以上なら境界候補として認める。
                close_enough = (
                    same_ev["close03"] >= 2
                    or (
                        same_ev["close03"] >= 1
                        and same_ev["class_close03"] >= race.class_rank
                    )
                )

            if close_enough:
                boundary.append(n)

        if local_transfer_guard_target(race, e, h):
            transfer.append(n)

        if debut_warning_target(e, h):
            debut.append(n)

        # 同距離実績そのものが無い馬だけを初距離警戒
        if (
            p["same_dist_count"] == 0
            and (
                p["adjacent_same_track"]
                or p["adjacent_other"]
            )
        ):
            adj_ev = _evidence(
                p["adjacent_same_track"] + p["adjacent_other"],
                race_date,
            )
            if adj_ev["best_content"][0] >= 3:
                first_distance.append(n)

        # 高速時計＋大差負けは警戒表示だけ。
        # 同場同距離TOP3級だがベスト時計時に1.0秒超負け。
        m = p["exact_best_margin"]
        if (
            n in raw_rank
            and raw_rank[n] <= 3
            and m is not None
            and m > 1.0
        ):
            fast_big_margin.append(n)

    return {
        "absolute": absolute,
        "boundary": boundary,
        "transfer": transfer,
        "debut": debut,
        "first_distance": first_distance,
        "fast_big_margin": fast_big_margin,
    }


def apply_guards_v1_1(
    normal_order: List[int],
    guards: Dict[str, List[int]],
) -> List[int]:
    """
    通常TOP6を作った後にだけガードを適用。
    ガード馬は「6番手保護」が基本。
    既に保護した馬を後続ガードで押し出さない。
    """
    target_len = min(6, len(normal_order))
    top6 = list(normal_order[:target_len])
    protected = set()

    # v1.1の確認順
    forced_groups = [
        ("absolute", guards["absolute"]),
        ("boundary", guards["boundary"]),
        ("transfer", guards["transfer"]),
    ]

    for _, horses in forced_groups:
        for n in horses:
            if n in top6:
                protected.add(n)
                continue

            # 最下位側から「未保護」の通常馬を探す
            replace_idx = None
            for i in range(len(top6) - 1, -1, -1):
                if top6[i] not in protected:
                    replace_idx = i
                    break

            if replace_idx is not None:
                top6[replace_idx] = n
                protected.add(n)

    # 重複除去し、足りなければ通常順位から補完
    clean = []
    for n in top6:
        if n not in clean:
            clean.append(n)

    for n in normal_order:
        if len(clean) >= target_len:
            break
        if n not in clean:
            clean.append(n)

    # 通常順位を保ったまま、強制加入馬は原則末尾側へ置く
    normal_pos = {n: i for i, n in enumerate(normal_order)}
    normal_members = [n for n in clean if n in normal_order[:target_len]]
    forced_members = [n for n in clean if n not in normal_order[:target_len]]

    normal_members = sorted(normal_members, key=lambda n: normal_pos[n])
    forced_members = sorted(forced_members, key=lambda n: normal_pos[n])

    final = (normal_members + forced_members)[:target_len]
    return final


# ============================================================
# 表示
# ============================================================

def _normal_reason(
    race: RaceInfo,
    p: Dict,
    race_date: date,
) -> str:
    exact_ev = _evidence(p["exact"], race_date)
    same_ev = _evidence(p["same_dist"], race_date)
    adj_ev = _evidence(
        p["adjacent_same_track"] + p["adjacent_other"],
        race_date,
    )

    parts = []

    if exact_ev["count"] > 0:
        text = f"同場同距離 {format_time(exact_ev['best_time'])}"
        if exact_ev["best_clock_margin"] is not None:
            text += f"／ベスト時{exact_ev['best_clock_margin']:.1f}差"
        parts.append(text)

        if exact_ev["close03"]:
            parts.append(f"0.3以内{exact_ev['close03']}回")
        elif exact_ev["close10"]:
            parts.append(f"1.0以内{exact_ev['close10']}回")

        if exact_ev["repeat_score"] >= 6:
            parts.append("再現性高")

    elif same_ev["count"] > 0:
        parts.append("別場同距離を内容比較")
        if same_ev["close03"]:
            parts.append(f"0.3以内{same_ev['close03']}回")
        elif same_ev["close10"]:
            parts.append(f"1.0以内{same_ev['close10']}回")

    elif adj_ev["count"] > 0:
        parts.append("隣接距離を補助評価")

    if same_ev["class_close03"] >= 0:
        parts.append(f"小差時クラス{same_ev['class_close03']}")

    if same_ev["latest_comp_days"] < 9999:
        parts.append(f"好内容{same_ev['latest_comp_days']}日前")

    if exact_ev["weak_direct"]:
        parts.append("直接実績は弱め")

    return " / ".join(parts) if parts else "時計材料薄め"


def build_prediction_v1_1(
    race: RaceInfo,
    entries: List[Entry],
    histories: Dict[int, HorseHistory],
    race_date: date,
) -> Dict:
    if len(entries) < 3:
        raise ValueError("出馬表から3頭以上を読み取れませんでした。")

    profiles = build_profiles(race, entries, histories)
    normal_order = normal_clock_order(race, profiles, race_date)
    guards = guard_lists_v1_1(
        race, entries, histories, profiles, normal_order, race_date
    )
    top6 = apply_guards_v1_1(normal_order, guards)

    by_num = {e.number: e for e in entries}

    normal_rows = []
    for i, n in enumerate(normal_order[:min(8, len(normal_order))], 1):
        p = profiles[n]
        normal_rows.append({
            "通常順位": i,
            "馬番": n,
            "馬名": by_num[n].name,
            "同場同距離": format_time(p["exact_best"]),
            "ベスト時計時着差": (
                "—"
                if p["exact_best_margin"] is None
                else f"{p['exact_best_margin']:.1f}"
            ),
            "2本目": format_time(p["exact_second"]),
            "別場同距離参考": format_time(p["other_same_dist_best"]),
            "評価理由": _normal_reason(race, p, race_date),
        })

    top6_rows = []
    for i, n in enumerate(top6, 1):
        p = profiles[n]
        tags = []
        if n in guards["absolute"]:
            tags.append("絶対時計")
        if n in guards["boundary"]:
            tags.append("境界")
        if n in guards["transfer"]:
            tags.append("転入")
        top6_rows.append({
            "時計TOP6": i,
            "馬番": n,
            "馬名": by_num[n].name,
            "ガード": "・".join(tags) if tags else "通常選出",
            "同場同距離": format_time(p["exact_best"]),
            "ベスト時計時着差": (
                "—"
                if p["exact_best_margin"] is None
                else f"{p['exact_best_margin']:.1f}"
            ),
            "評価理由": _normal_reason(race, p, race_date),
        })

    if len(entries) <= 6:
        status = "参考・ノーカウント"
    elif len(entries) == 7:
        status = "参考"
    else:
        status = "本集計"

    return {
        "ruleset_id": RULESET_ID,
        "ruleset_name": RULESET_NAME,
        "race": asdict(race),
        "race_date": race_date.isoformat(),
        "entries": [asdict(e) for e in entries],
        "normal_order": normal_order,
        "normal_rows": normal_rows,
        "top6": top6,
        "top6_rows": top6_rows,
        "top6_status": status,
        "guards": guards,
    }


def parse_result_v1_1(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", text)]


def verify_result_v1_1(pred: Dict, result_text: str) -> Dict:
    result = parse_result_v1_1(result_text)
    if len(result) < 3:
        raise ValueError("結果は『7-5-10』のように1〜3着まで入力してください。")

    podium = result[:3]
    top6 = set(map(int, pred["top6"]))
    hits = sum(n in top6 for n in podium)

    def guard_result(nums):
        vals = []
        for n in nums:
            vals.append(
                f"{n}:{podium.index(n)+1 if n in podium else '圏外'}"
            )
        return "・".join(vals)

    g = pred["guards"]

    return {
        "ルール": pred["ruleset_id"],
        "日付": pred["race_date"],
        "レース": pred["race"].get("race_name", ""),
        "競馬場": pred["race"].get("track", ""),
        "条件": (
            f"{pred['race'].get('surface','')}"
            f"{pred['race'].get('distance',0)}m"
        ),
        "頭数": len(pred["entries"]),
        "結果": "-".join(map(str, result[:3])),
        "通常TOP8": "・".join(
            map(str, pred["normal_order"][:8])
        ),
        "時計TOP6": "・".join(map(str, pred["top6"])),
        "TOP6集計区分": pred["top6_status"],
        "TOP6馬券内": f"{hits}/3",
        "TOP6完全捕捉": "○" if hits == 3 else "×",
        "絶対時計": guard_result(g["absolute"]),
        "境界": guard_result(g["boundary"]),
        "地方転入": guard_result(g["transfer"]),
        "初出走警戒": guard_result(g["debut"]),
        "初距離警戒": guard_result(g["first_distance"]),
        "高速時計大差負け": guard_result(g["fast_big_margin"]),
    }


# ============================================================
# UI
# ============================================================

APP_NAME = "競馬AI 時計TOP6 共通ルールv1.1固定版"
st.set_page_config(
    page_title=APP_NAME,
    page_icon="⏱️",
    layout="wide",
)

st.title("⏱️ 競馬AI 時計TOP6")
st.caption(f"完全共通ルール v1.1【凍結版】｜実装 {IMPLEMENTATION_REV}｜API不要｜4頭絞りなし")

st.info(
    "🔒 ルール固定中（文章ルールは変更なし）："
    f"{RULESET_ID}\n\n"
    "今後の検証で改善案が出ても、このv1.1は上書きしません。"
)

if "locked_prediction_v11" not in st.session_state:
    st.session_state.locked_prediction_v11 = None
if "history_v11" not in st.session_state:
    st.session_state.history_v11 = []


def clear_v11():
    st.session_state.locked_prediction_v11 = None
    st.session_state.race_text_v11 = ""
    st.session_state.entry_text_v11 = ""
    st.session_state.history_text_v11 = ""
    st.session_state.result_text_v11 = ""


tab1, tab2, tab3, tab4 = st.tabs(
    ["予想・検証", "検証履歴", "固定ルールv1.1", "既知レース照合"]
)

with tab1:
    st.subheader("① レース情報を貼り付け")

    race_date_input = st.date_input(
        "レース日",
        value=date.today(),
        key="race_date_v11",
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        race_text = st.text_area(
            "レース情報",
            height=230,
            key="race_text_v11",
        )

    with c2:
        entry_text = st.text_area(
            "出馬表",
            height=230,
            key="entry_text_v11",
        )

    with c3:
        history_text = st.text_area(
            "馬柱",
            height=230,
            key="history_text_v11",
        )

    b1, b2 = st.columns(2)

    with b1:
        run = st.button(
            "時計TOP6を分析する（事前固定）",
            type="primary",
            use_container_width=True,
        )

    with b2:
        st.button(
            "入力・予想をクリア",
            use_container_width=True,
            on_click=clear_v11,
        )

    if run:
        try:
            race = parse_race_info(race_text)
            entries = parse_entries(entry_text)
            histories = parse_horse_histories(history_text, entries)

            problems = []
            if not race.track:
                problems.append("競馬場を取得できませんでした。")
            if not race.surface or not race.distance:
                problems.append("芝/ダート・距離を取得できませんでした。")
            if len(entries) < 3:
                problems.append("出馬表を十分に解析できませんでした。")
            if len(histories) < min(3, len(entries)):
                problems.append("馬柱を十分に解析できませんでした。")

            st.caption(
                f"解析：出馬表 {len(entries)}頭 / 馬柱 {len(histories)}頭"
            )

            if problems:
                st.error("\n".join(problems))
            else:
                pred = build_prediction_v1_1(
                    race,
                    entries,
                    histories,
                    race_date_input,
                )
                st.session_state.locked_prediction_v11 = pred
                st.success(
                    "v1.1で事前固定しました。"
                    "結果入力時に順位は再計算しません。"
                )
        except Exception as e:
            st.error(f"解析エラー：{e}")

    pred = st.session_state.locked_prediction_v11

    if pred:
        st.divider()
        st.subheader("② 最終 時計TOP6")

        st.success(
            "時計TOP6【三連系用】："
            + "・".join(map(str, pred["top6"]))
            + f"　｜ {pred['top6_status']}"
        )

        st.dataframe(
            pd.DataFrame(pred["top6_rows"]),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### 第1エンジン｜通常時計順位 TOP8")
        st.caption("この順位を作る段階では人気・オッズ・ガードを使用していません。")
        st.dataframe(
            pd.DataFrame(pred["normal_rows"]),
            use_container_width=True,
            hide_index=True,
        )

        g = pred["guards"]

        st.markdown("### 第2エンジン｜ガード・警戒")
        st.write(
            "**絶対時計ガード**："
            + (
                "・".join(map(str, g["absolute"]))
                if g["absolute"]
                else "該当なし"
            )
        )
        st.write(
            "**絶対時計・境界ガード**："
            + (
                "・".join(map(str, g["boundary"]))
                if g["boundary"]
                else "該当なし"
            )
        )
        st.write(
            "**地方転入人気馬ガード**："
            + (
                "・".join(map(str, g["transfer"]))
                if g["transfer"]
                else "該当なし"
            )
        )
        st.write(
            "**初出走警戒**："
            + (
                "・".join(map(str, g["debut"]))
                if g["debut"]
                else "該当なし"
            )
        )
        st.write(
            "**初距離警戒**："
            + (
                "・".join(map(str, g["first_distance"]))
                if g["first_distance"]
                else "該当なし"
            )
        )
        st.write(
            "**高速時計＋大差負け警戒**："
            + (
                "・".join(map(str, g["fast_big_margin"]))
                if g["fast_big_margin"]
                else "該当なし"
            )
        )

        st.divider()
        st.subheader("③ 結果検証")

        result_text = st.text_input(
            "実着順",
            placeholder="例：7-5-10",
            key="result_text_v11",
        )

        if st.button(
            "結果を照合して履歴に保存",
            use_container_width=True,
        ):
            try:
                record = verify_result_v1_1(pred, result_text)
                st.session_state.history_v11.append(record)

                st.success(
                    f"結果 {record['結果']}｜"
                    f"TOP6馬券内 {record['TOP6馬券内']}｜"
                    f"完全捕捉 {record['TOP6完全捕捉']}"
                )
            except Exception as e:
                st.error(str(e))


with tab2:
    st.subheader("検証履歴")
    st.caption(
        "すべての履歴にルールIDを保存します。"
        "将来v1.2を作ってもv1.1検証と混ざりません。"
    )

    if st.session_state.history_v11:
        hdf = pd.DataFrame(st.session_state.history_v11)
        st.dataframe(
            hdf,
            use_container_width=True,
            hide_index=True,
        )

        counted = hdf[
            hdf["TOP6集計区分"] == "本集計"
        ]

        races = len(counted)
        hits = (
            sum(
                int(str(x).split("/")[0])
                for x in counted["TOP6馬券内"]
            )
            if races
            else 0
        )
        full = (
            int((counted["TOP6完全捕捉"] == "○").sum())
            if races
            else 0
        )

        c1, c2 = st.columns(2)
        c1.metric(
            "TOP6 馬券内捕捉",
            f"{hits}/{races * 3}" if races else "0/0",
        )
        c2.metric(
            "TOP6 完全捕捉",
            f"{full}/{races}" if races else "0/0",
        )

        csv_bytes = hdf.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            "v1.1検証履歴CSVをダウンロード",
            data=csv_bytes,
            file_name="keiba_clock_top6_v1_1_history.csv",
            mime="text/csv",
            use_container_width=True,
        )

        if st.button("v1.1履歴を全削除"):
            st.session_state.history_v11 = []
            st.rerun()
    else:
        st.info("まだv1.1の検証履歴はありません。")


with tab3:
    st.subheader(RULESET_NAME)
    st.code(RULESET_ID)
    st.markdown(RULESET_TEXT)


with tab4:
    st.subheader("既知レースの固定TOP6")
    st.caption(
        "これは検証時の照合用データです。"
        "ランキング計算には一切使用していません。"
    )

    expected = {
        "R34 新潟 柳都S ダ1800稍": [6, 14, 2, 8, 4, 11],
        "R35 浦和 盆の月特別 ダ2000不": [3, 2, 10, 6, 7, 8],
        "R37 大井 武蔵野OP ダ1200不": [3, 5, 6, 9, 10, 11],
        "R38 門別 リンドウ特別 ダ1200良": [10, 7, 5, 6, 8, 9],
        "R39 大井 トゥインクルバースデー賞 ダ1600不": [2, 6, 10, 14, 11, 1],
    }

    rdf = pd.DataFrame([
        {
            "レース": name,
            "固定TOP6": "・".join(map(str, nums)),
        }
        for name, nums in expected.items()
    ])

    st.dataframe(
        rdf,
        use_container_width=True,
        hide_index=True,
    )

    pred = st.session_state.locked_prediction_v11
    if pred:
        target = st.selectbox(
            "現在の予想を照合",
            list(expected.keys()),
        )

        actual = list(map(int, pred["top6"]))
        exp = expected[target]

        st.write(
            "**現在：** "
            + "・".join(map(str, actual))
        )
        st.write(
            "**固定正解：** "
            + "・".join(map(str, exp))
        )

        if actual == exp:
            st.success("完全一致（6頭＋順番）")
        elif set(actual) == set(exp):
            st.warning("6頭の集合は一致。順番のみ不一致。")
        else:
            missing = [n for n in exp if n not in actual]
            extra = [n for n in actual if n not in exp]

            st.error(
                "不一致｜不足："
                + (
                    "・".join(map(str, missing))
                    if missing
                    else "なし"
                )
                + "｜余分："
                + (
                    "・".join(map(str, extra))
                    if extra
                    else "なし"
                )
            )
