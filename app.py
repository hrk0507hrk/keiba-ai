from __future__ import annotations

import calendar
import hashlib
import json
import re
import textwrap
import statistics
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
    if re.search(r"\bL\b", t) or "OP" in t or "オープン" in t:
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
# 時計分析 完全ルールブック v2.0-Beta【完全Python自動判定版】
# ChatGPT / OpenAI API / 外部LLM 不使用
# ============================================================

RULESET_ID = "CLOCK_RULEBOOK_V2_0_BETA_PYTHON_FROZEN_2026-08-13"
RULESET_NAME = "時計分析 完全ルールブック v2.0-Beta【完全Python自動判定】"
IMPLEMENTATION_REV = "python-engine-8-fullfield-audit"

RULEBOOK_TEXT = r"""
【0｜目的】
レース結果を知らない事前状態で、出馬表・馬柱から時計面だけでTOP6を選定する。
目的は単純な時計順ではなく、このチャットで行ってきた時計分析の考え方を、新しい未見レースでも同じ手順で再現すること。
通常時計順位では人気・オッズ・騎手・調教師・血統・枠順・展開・固定AXIS・相手Cを使用しない。
人気は地方転入人気馬ガード、初出走警戒など明文化されたガード用途に限る。

【1｜処理順】
第1段階＝事実抽出。
第2段階＝5軸と競合ルールで通常時計TOP8を作る。
第3段階＝通常順位確定後に絶対時計・地方転入・境界ガードを確認し最終TOP6を作る。
ガードを通常順位へ混ぜない。

【2｜必須事実】
各馬について、同場同距離ベスト、その時計時着差、2本目、3本目、直近時計、同馬場時計、別場同距離、勝利・0.3・0.6・1.0秒以内、クラス、直近時計推移、隣接距離、直接対戦を確認する。
ベスト時計とその時計時着差は必ず1セットで扱う。

【3｜CONDITION】
CONDITIONは点数ではなく、どの証拠を直接比較してよいかを決めるフィルター。
基本信頼順は、同場同距離＋近い馬場 → 同場同距離 → 別場同距離 → 同場隣接距離 → 別場隣接距離。
ただし弱い直接実績より非常に強い隣接距離実績を上にできる。
別競馬場の生時計秒数を直接比較してはならない。

【4｜PEAK】
PEAKは過去全体の最高時計能力。
RAW PEAK＝単純な最速時計。
VALID PEAK＝高い時計水準に加え、その走りで勝利・小差など競争になっている裏付けがあるピーク。
通常順位ではVALID PEAKをRAW PEAKより信頼する。
高速時計でも大差負けならRAW PEAKは高くてもVALID PEAKの信頼度は低い。

【5｜CONTENT】
時計を出した時にどれだけ競争になっていたかを見る。
勝利・0.3秒以内が最重要。次に0.4〜0.6、0.7〜1.0、1.1〜1.5、それ以上の順に弱くする。
CONTENTだけで何秒ものPEAK差を無条件に逆転させない。
クラスは単独加点せず「高クラス＋小差CONTENT」として評価する。
高クラス大敗は強い証拠にしない。

【6｜REPEAT】
REPEATは比較可能な直近5走を基本範囲とする。
CLOCK REPEAT＝ベスト付近・同一能力帯の時計を何度再現したか。
CONTENT REPEAT＝勝利・0.3・0.6・1.0秒以内等の好内容を何度再現したか。
直近3走中2回以上、または直近5走中3回以上の高水準再現は強い。直近5走中2回は中程度、1回のみは単発。
ただし比較可能走が少ない馬は「再現性低」ではなく「材料不足」とする。
古い好時計はPEAKには残すが、最近5比較可能走の外ならREPEATへ足し続けない。

【7｜CURRENT】
CURRENTは比較可能な直近3走で判断する。
高水準維持・上昇・横ばい・下降・判定不能の5分類。
時計水準とCONTENTの双方が改善していれば上昇。過去PEAK後に複数走続けて能力帯が低下しCONTENTも悪化していれば下降。
比較可能な最近材料が1走以下ならCURRENT不明とし、材料不足だけで減点しない。
長期休養ではPEAKを消さず、CURRENTの信頼度を下げるか不明とする。

【8｜時計クラスタ】
PEAK差の大中小を固定秒数で決めない。同競馬場・同距離のメンバー内時計分布から自然な時計の塊と断層を見る。
明確な断層がなければ無理にTOP3等でクラスタを切らない。
クラスタ形成に使う生時計は原則として同競馬場・同距離のみ。
別場から持ち込むのは生時計秒数ではなく、その条件での相対水準、CONTENT、クラス、REPEAT、CURRENT。
比較材料が少なすぎる場合は形式順位だけでクラスタや絶対時計を作らない。

【9｜PEAK差の競合】
同じ時計クラスタ＝PEAK差小。CONTENT・REPEAT・CURRENTで普通に逆転可能。
隣接クラスタ＝PEAK差中。PEAK上位が基本優勢だが、下位側がCURRENT上昇・CLOCK REPEAT強・CONTENT REPEAT強なら逆転可能。
明確な断層を跨ぐ＝PEAK差大。CURRENTや小差だけで簡単に逆転させない。
ただし上位側がRAW PEAKのみ＋大差負け＋再現なしなら、そのPEAK自体の信頼性を下げる。

【10｜時計差 vs 着差】
時計差が小さいほどCONTENTを強く使い、小差好走馬が逆転できる。
時計差が大きいほど絶対時計差を尊重し、着差が少し良いだけでは逆転させない。
固定の「着差を何秒加算」だけで全条件を処理しない。

【11｜PEAK vs REPEAT/CURRENT】
同じPEAKクラスタなら単発最速より高水準を繰り返す馬を通常順位で上にできる。
単発でも最上位VALID PEAKなら絶対時計候補として価値を保持する。
古いPEAKで近走再現がなければ通常順位ではREPEAT・CURRENTを優先するが、PEAKそのものは消さない。
CURRENT差が小さければPEAKを尊重する。明確な上昇・下降がある時にCURRENTを強く使う。

【12｜直接対戦】
今回出走馬同士が同じ過去レースを走っていれば完全に同一条件の共通物差しとして強いタイブレークにする。
直近5比較可能走程度で2回以上直接対戦し、同じ馬が継続して優勢ならDIRECT REPEATとしてさらに強くする。
ただし古い直接対戦だけでCURRENTの明確な逆転を無視しない。

【13｜距離】
直接同距離を基本優先するが、弱い直接実績より強い隣接距離実績を上にできる。
隣接距離は今回距離との差が小さいほど信頼度が高い。延長・短縮そのものには固定加減点を与えない。
方向ではなく距離差＋時計内容＋CONTENTを見る。

【14｜地方競馬】
地方は中央より同場同距離を強く信頼する。
同場同距離PEAK＋CONTENT＋REPEAT＋CURRENTを中心に通常順位を作る。
別場生時計は直接比較しない。

【15｜JRA1600〜1800m】
別場生時計を直接比較しない。
同距離CONTENT → 高クラスでの好内容 → REPEAT → CURRENT → 同場同距離時計の順を基本に比較する。
同じ過去レースの直接対戦は強い比較材料。
高クラスでも大差負けだけなら上げない。

【16｜2000m以上】
直接距離実績を強く重視するが、距離経験があるだけでは保護しない。
同距離で大差負けしかない弱い直接実績より、隣接距離の強いVALID内容を上にできる。

【17｜通常TOP8】
人気・オッズ・ガードを使わず通常1〜8位を作る。
一度TOP8を作った後、隣接順位をペア比較して再確認する。
特に5位vs6位、6位vs7位、7位vs8位を重点確認する。
同じPEAK能力帯ならCONTENT・REPEAT・CURRENTの重要度を上げる。

【18｜絶対時計ガード】
最上位VALID PEAK時計クラスタに所属し、かつ勝利または0.3秒以内の裏付けがある馬をTOP6から落とさない。
形式上の生時計TOP3だけでは発動しない。
比較材料が少なすぎる場合も順位だけで絶対時計扱いしない。

【19｜境界ガード】
通常7〜8位付近で、同距離勝利または0.3秒以内があり、6位馬と同じまたはほぼ同じ時計能力帯でCONTENTの裏付けがある馬を6番手へ保護できる。
境界ガードだけを理由に上位順位へ昇格させない。

【20｜地方転入人気馬ガード】
地方転入初戦、直前までJRAまたは南関等の上位環境、当日3番人気以内。
通常TOP6外なら6番手へ保護。
一度別地方を走った後の「今回競馬場初出走」だけでは転入初戦扱いしない。
人気はこのガード以外の通常順位に使わない。

【21｜警戒表示】
初出走＋5番人気以内＝初出走警戒。
同距離実績なし＋隣接距離に強い内容＝初距離警戒。
最速級RAW PEAK＋大差負け＝高速時計＋大差負け警戒。
警戒表示だけではTOP6へ強制加入させない。

【22｜複数ガード競合 Beta暫定】
ガード候補が多すぎて6枠を超える実例は不足しているため、固定優先順位を新しく発明しない。
競合した場合は「ガード競合」と明示し、5軸とガード根拠を再比較して6枠を決める。
この項目はv2.1候補。

【23｜禁止判断】
通常順位を人気・オッズ・騎手・調教師・血統・枠順・展開で変更しない。
別場生時計を秒数だけで直接比較しない。
固定の競馬場秒補正を作らない。
単発高速時計だけ、クラスだけ、人気だけで自動上位にしない。
境界ガード馬を上位へ昇格させない。
結果を知った後の後付けで事前順位を変えない。
入力に無い事実を推測で補わない。材料不足は「不明」と書く。

【24｜エンジン強制手順】
1. 事実抽出結果を読む
2. CONDITION整理
3. PEAK判定
4. VALID/RAW判定
5. 時計クラスタ確認
6. CONTENT評価
7. REPEAT評価（直近5比較可能走）
8. CURRENT評価（直近3比較可能走）
9. クラス価値
10. 直接対戦
11. 通常TOP8作成
12. 隣接順位ペア比較
13. 通常順位固定
14. 絶対時計ガード
15. 地方転入ガード
16. 境界ガード
17. 最終TOP6固定

【25｜少頭数】
6頭以下：TOP6＝全頭、参考・ノーカウント。
7頭：TOP6は参考。
8頭以上：本集計。

【26｜バージョン管理】
このv2.0-Betaは仮凍結する。検証で改善案が出ても直接上書きしない。
新しい改善はv2.1候補として別管理する。
""".strip()

# ============================================================
# 基本評価ヘルパー
# ============================================================

def _days(r: PastRace, race_date: date) -> int:
    if r.race_date is None:
        return 9999
    return max(0, (race_date - r.race_date).days)


def _margin_level(m: Optional[float]) -> int:
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


def _margin_label(m: Optional[float]) -> str:
    if m is None:
        return "不明"
    if m <= 0.3:
        return "勝利・0.3以内"
    if m <= 0.6:
        return "0.4-0.6"
    if m <= 1.0:
        return "0.7-1.0"
    if m <= 1.5:
        return "1.1-1.5"
    return "1.6以上"


def _recent(rs: List[PastRace]) -> List[PastRace]:
    return sorted(rs, key=lambda r: r.race_date or date.min, reverse=True)


def _surface_runs(h: Optional[HorseHistory], race: RaceInfo) -> List[PastRace]:
    if not h:
        return []
    return [
        r for r in h.races
        if r.surface == race.surface and r.distance is not None and r.time_seconds is not None
    ]


def _same_dist_runs(h: Optional[HorseHistory], race: RaceInfo) -> List[PastRace]:
    return [r for r in _surface_runs(h, race) if r.distance == race.distance]


def _exact_runs(h: Optional[HorseHistory], race: RaceInfo) -> List[PastRace]:
    return [r for r in _same_dist_runs(h, race) if r.track == race.track]


def _adjacent_runs(h: Optional[HorseHistory], race: RaceInfo, same_track: Optional[bool] = None) -> List[PastRace]:
    out = []
    for r in _surface_runs(h, race):
        if r.distance == race.distance or r.distance is None:
            continue
        if abs(r.distance - race.distance) > 400:
            continue
        if same_track is True and r.track != race.track:
            continue
        if same_track is False and r.track == race.track:
            continue
        out.append(r)
    return out


def _comparable_runs(h: Optional[HorseHistory], race: RaceInfo) -> List[PastRace]:
    return _recent([
        r for r in _surface_runs(h, race)
        if r.distance == race.distance or (r.distance is not None and abs(r.distance - race.distance) <= 400)
    ])


def _best_time_run(rs: List[PastRace]) -> Optional[PastRace]:
    valid = [r for r in rs if r.time_seconds is not None]
    return min(valid, key=lambda r: r.time_seconds) if valid else None


def _best_content_run(rs: List[PastRace], race_date: date) -> Optional[PastRace]:
    if not rs:
        return None
    # CONTENTとクラス価値を分離。着差帯→着順→直近性で内容そのものを選ぶ。
    return max(rs, key=lambda r: _content_core_tuple(r, race_date))


def _content_tuple(r: Optional[PastRace], race_date: date) -> Tuple:
    if r is None:
        return (-1, -9, -9999, -1)
    ml = _margin_level(r.margin)
    class_part = r.class_rank if ml >= 3 else -9
    finish_part = 3 if r.finish == 1 else 2 if r.finish == 2 else 1 if r.finish == 3 else 0
    return (ml, class_part, -_days(r, race_date), finish_part)

def _content_core_tuple(r: Optional[PastRace], race_date: date) -> Tuple:
    """
    CONTENTそのものの比較用。
    v2.0-BetaではクラスをCONTENTと分離し、
    着差帯→着順→直近性の順で見る。
    クラス価値はREPEAT/CURRENTの後で別比較する。
    """
    if r is None:
        return (-1, -1, -9999)
    ml = _margin_level(r.margin)
    finish_part = 3 if r.finish == 1 else 2 if r.finish == 2 else 1 if r.finish == 3 else 0
    return (ml, finish_part, -_days(r, race_date))


def _count_close(rs: List[PastRace], lim: float) -> int:
    return sum(1 for r in rs if r.margin is not None and r.margin <= lim)


def _condition_tier(race: RaceInfo, r: PastRace) -> int:
    if r.distance is None:
        return 99
    delta = abs(r.distance - race.distance)
    if r.track == race.track and r.distance == race.distance and r.going == race.going:
        return 0
    if r.track == race.track and r.distance == race.distance:
        return 1
    if r.distance == race.distance:
        return 2
    if r.track == race.track and delta <= 100:
        return 3
    if r.track == race.track and delta <= 200:
        return 4
    if r.track == race.track and delta <= 400:
        return 5
    if delta <= 100:
        return 6
    if delta <= 200:
        return 7
    if delta <= 400:
        return 8
    return 99


def _condition_text(tier: int) -> str:
    return {
        0: "同場同距離・同馬場",
        1: "同場同距離",
        2: "別場同距離",
        3: "同場隣接100m以内",
        4: "同場隣接200m以内",
        5: "同場隣接400m以内",
        6: "別場隣接100m以内",
        7: "別場隣接200m以内",
        8: "別場隣接400m以内",
    }.get(tier, "材料薄")


# ============================================================
# 時計クラスタ：固定秒差ではなく分布の自然断層を検出
# ============================================================

def build_clock_clusters(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory]) -> Dict:
    """同場同距離ベストの分布から自然断層だけをクラスタ化する。

    impl4では、断層が検出できない時に全馬を擬似的なC1へ押し込まない。
    その場合は raw_rank / continuous_position を保持し、PEAK差は連続量として残す。
    """
    rows = []
    for e in entries:
        br = _best_time_run(_exact_runs(histories.get(e.number), race))
        if br is not None:
            rows.append({
                "number": e.number,
                "name": e.name,
                "time": br.time_seconds,
                "margin": br.margin,
                "date": br.race_date,
            })
    rows.sort(key=lambda x: x["time"])
    n = len(rows)
    if n == 0:
        return {
            "rows": [], "cluster_by_num": {}, "reliable": False,
            "break_after": [], "boundaries": [], "median_time": None,
        }

    gaps = [rows[i+1]["time"] - rows[i]["time"] for i in range(n-1)]
    breaks = []
    reliable = False
    if n >= 4 and len(gaps) >= 3:
        positive = [g for g in gaps if g > 1e-9]
        if positive:
            med = statistics.median(positive)
            s = pd.Series(positive, dtype=float)
            q1 = float(s.quantile(0.25))
            q3 = float(s.quantile(0.75))
            iqr = max(0.0, q3 - q1)
            threshold = max(q3 + 1.5 * iqr, med * 2.5)
            for i, g in enumerate(gaps):
                if g > threshold and g > med * 1.5:
                    breaks.append(i)
            reliable = bool(breaks)

    cluster = 1
    cluster_by_num = {}
    boundaries = []
    for i, row in enumerate(rows):
        row["raw_rank"] = i + 1
        row["continuous_position"] = 1.0 if n == 1 else 1.0 - (i / (n - 1))
        if reliable:
            cluster_by_num[row["number"]] = cluster
            row["cluster"] = cluster
        else:
            row["cluster"] = None
        if i in breaks:
            boundaries.append((rows[i]["time"] + rows[i+1]["time"]) / 2.0)
            cluster += 1

    return {
        "rows": rows,
        "cluster_by_num": cluster_by_num,
        "reliable": reliable,
        "break_after": breaks,
        "boundaries": boundaries,
        "median_time": statistics.median([x["time"] for x in rows]),
    }


def _cluster_for_time(seconds: Optional[float], clusters: Dict) -> Optional[int]:
    if seconds is None or not clusters.get("rows") or not clusters.get("reliable"):
        return None
    c = 1
    for b in clusters.get("boundaries", []):
        if seconds > b:
            c += 1
        else:
            break
    return c


def _continuous_clock_position(seconds: Optional[float], clusters: Dict) -> Optional[float]:
    """自然断層が無い時の同場同距離時計を、固定秒差ではなく分布内位置で表す。"""
    rows = clusters.get("rows", [])
    if seconds is None or not rows:
        return None
    times = sorted(x["time"] for x in rows)
    if len(times) == 1:
        return 1.0
    # 同値は同位置扱い。0〜1で大きいほど速い。
    slower_or_equal = sum(1 for t in times if t >= seconds - 1e-9)
    return (slower_or_equal - 1) / (len(times) - 1)


# ============================================================
# 5軸評価
# ============================================================

def _repeat_grade(last5: List[PastRace], race: RaceInfo, clusters: Dict) -> Dict:
    if len(last5) < 2:
        return {
            "grade": 1, "label": "材料不足", "content_high": 0,
            "clock_high": None, "clock_known": False,
        }

    content_high = sum(1 for r in last5 if r.margin is not None and r.margin <= 1.0)
    last3_high = sum(1 for r in last5[:3] if r.margin is not None and r.margin <= 1.0)

    exact_recent = [
        r for r in last5
        if r.track == race.track and r.distance == race.distance and r.time_seconds is not None
    ]
    clock_high: Optional[int] = None
    clock_known = False

    if exact_recent:
        if clusters.get("reliable"):
            vals = [_cluster_for_time(r.time_seconds, clusters) for r in exact_recent]
            vals = [v for v in vals if v is not None]
            if vals:
                best_cluster = min(vals)
                clock_high = sum(1 for v in vals if v == best_cluster)
                clock_known = True
        elif len(clusters.get("rows", [])) >= 3:
            # 断層なしでは0扱いにしない。レース内の動的中央値より速い時計の再現本数を見る。
            # 固定0.5秒等は使わず、そのレースの同場同距離分布だけを基準にする。
            ref = clusters.get("median_time")
            if ref is not None:
                clock_high = sum(1 for r in exact_recent if r.time_seconds <= ref + 1e-9)
                clock_known = True

    ch = clock_high or 0
    if last3_high >= 2 or content_high >= 3 or ch >= 3:
        grade, label = 3, "強"
    elif content_high >= 2 or ch >= 2:
        grade, label = 2, "中"
    elif content_high >= 1 or ch >= 1:
        grade, label = 1, "単発"
    else:
        grade, label = 0, "弱"
    return {
        "grade": grade, "label": label, "content_high": content_high,
        "clock_high": clock_high, "clock_known": clock_known,
    }


def _run_current_key(r: PastRace, race: RaceInfo, race_date: date, clusters: Dict) -> Tuple:
    ml = _margin_level(r.margin)
    tier = _condition_tier(race, r)
    clock_part = -1.0
    if r.track == race.track and r.distance == race.distance:
        cl = _cluster_for_time(r.time_seconds, clusters)
        if cl is not None:
            clock_part = 10.0 - float(cl)
        else:
            cp = _continuous_clock_position(r.time_seconds, clusters)
            if cp is not None:
                clock_part = cp
    class_part = r.class_rank if ml >= 3 else -9
    # CURRENTでは別場生時計を直接比較しない。時計成分は同場同距離だけ。
    return (ml, clock_part, class_part, -tier, -_days(r, race_date))


def _current_state(
    last3: List[PastRace],
    all_comp: List[PastRace],
    race: RaceInfo,
    race_date: date,
    clusters: Dict,
) -> Dict:
    if len(last3) < 2:
        return {"grade": 2, "label": "判定不能", "detail": "比較可能走1本以下", "near_peak": 0}

    chronological = list(reversed(last3))
    keys = [_run_current_key(r, race, race_date, clusters) for r in chronological]
    ups = sum(1 for a, b in zip(keys, keys[1:]) if b > a)
    downs = sum(1 for a, b in zip(keys, keys[1:]) if b < a)

    # CURRENTは自馬の過去PEAKとの相対水準も確認する。
    all_levels = [_margin_level(r.margin) for r in all_comp if r.margin is not None]
    peak_level = max(all_levels, default=0)
    near_peak_floor = max(1, peak_level - 1) if peak_level > 0 else 1
    near_peak = sum(
        1 for r in last3
        if r.margin is not None and _margin_level(r.margin) >= near_peak_floor
    )

    if len(last3) >= 3 and ups == len(keys) - 1:
        return {"grade": 4, "label": "上昇", "detail": "直近比較可能走で内容水準が連続改善", "near_peak": near_peak}
    if len(last3) >= 3 and downs == len(keys) - 1:
        return {"grade": 0, "label": "下降", "detail": "直近比較可能走で内容水準が連続低下", "near_peak": near_peak}
    if near_peak >= 2:
        return {"grade": 4, "label": "高水準維持", "detail": "直近3走で自馬PEAK帯に近い内容を複数回", "near_peak": near_peak}
    return {"grade": 2, "label": "横ばい", "detail": "明確な連続上昇・下降なし", "near_peak": near_peak}


def _class_value(rs: List[PastRace], race: RaceInfo) -> Dict:
    strong = [r for r in rs if r.margin is not None and r.margin <= 1.0]
    if not strong:
        return {"rank": -9, "label": "強いクラス裏付けなし"}
    best = max(strong, key=lambda r: (r.class_rank, _margin_level(r.margin)))
    if best.class_rank >= race.class_rank:
        label = "今回同等以上クラスで好内容"
    elif best.class_rank >= race.class_rank - 1:
        label = "1クラス下までで好内容"
    else:
        label = "下級条件で好内容"
    return {"rank": best.class_rank, "label": label}



def _content_profile(rs: List[PastRace], race_date: date) -> Dict:
    """CONTENTを「最高1走だけ」で潰さず、能力帯の厚みも保持する。

    REPEATとは役割を分けるため、ここは全履歴の内容証拠。
    直近性・継続性そのものは別途REPEAT/CURRENTで判断する。
    """
    if not rs:
        return {
            "best": None,
            "best_band": 0,
            "second_band": 0,
            "close03": 0,
            "close06": 0,
            "close10": 0,
            "competitive": 0,
            "key": (0, 0, 0, 0, 0, -9999),
        }
    best = _best_content_run(rs, race_date)
    levels = sorted(
        [_margin_level(r.margin) for r in rs if r.margin is not None],
        reverse=True,
    )
    best_band = levels[0] if levels else 0
    second_band = levels[1] if len(levels) >= 2 else 0
    close03 = _count_close(rs, 0.3)
    close06 = _count_close(rs, 0.6)
    close10 = _count_close(rs, 1.0)
    competitive = close10
    best_finish = (
        3 if best is not None and best.finish == 1
        else 2 if best is not None and best.finish == 2
        else 1 if best is not None and best.finish == 3
        else 0
    )
    best_days = -_days(best, race_date) if best is not None else -9999
    # best帯→2本目の帯→僅差本数。古さは最後にしか使わない。
    key = (best_band, second_band, close03, close06, close10, best_finish, best_days)
    return {
        "best": best,
        "best_band": best_band,
        "second_band": second_band,
        "close03": close03,
        "close06": close06,
        "close10": close10,
        "competitive": competitive,
        "key": key,
    }


def _competitive_class_profile(rs: List[PastRace], race: RaceInfo, race_date: date) -> Dict:
    """クラスは必ず競争になった内容とセットで評価する。大敗は入れない。"""
    good = [r for r in rs if r.margin is not None and r.margin <= 1.0]
    if not good:
        return {
            "best_rank": -9,
            "best_band": 0,
            "same_or_up": 0,
            "one_down_or_up": 0,
            "close03_high": 0,
            "key": (-9, 0, 0, 0, 0, -9999),
        }
    # 一番高いクラスで「実際に競争になった」走を代表にする。
    best_rank = max(r.class_rank for r in good)
    at_best = [r for r in good if r.class_rank == best_rank]
    best_run = max(at_best, key=lambda r: (_margin_level(r.margin), -_days(r, race_date)))
    same_or_up = sum(1 for r in good if r.class_rank >= race.class_rank)
    one_down_or_up = sum(1 for r in good if r.class_rank >= race.class_rank - 1)
    close03_high = sum(
        1 for r in good
        if r.class_rank >= race.class_rank - 1 and r.margin is not None and r.margin <= 0.3
    )
    key = (
        best_rank,
        _margin_level(best_run.margin),
        same_or_up,
        one_down_or_up,
        close03_high,
        -_days(best_run, race_date),
    )
    return {
        "best_rank": best_rank,
        "best_band": _margin_level(best_run.margin),
        "same_or_up": same_or_up,
        "one_down_or_up": one_down_or_up,
        "close03_high": close03_high,
        "key": key,
    }


def _jra_direct_floor_profile(
    direct_runs: List[PastRace],
    race: RaceInfo,
    race_date: date,
) -> Dict:
    """JRA1600〜1800mで、同距離実績の「能力床」を診断する。

    最高1走のCONTENTとは別に、同距離で競争になった走が複数あるかを保持する。
    これは新しい加点軸ではなく、v2.0-Beta既存のCONTENT＋REPEAT＋クラス価値を
    一発好走と継続証拠に分解して競合判断へ渡すための実装補助。

    別競馬場の生時計は一切比較しない。使うのは着差・クラス・本数・直近性だけ。
    """
    runs = _recent(list(direct_runs))
    cp = _content_profile(runs, race_date)
    competitive = [r for r in runs if r.margin is not None and r.margin <= 1.0]
    same_up = [r for r in competitive if r.class_rank >= race.class_rank]
    one_down_up = [r for r in competitive if r.class_rank >= race.class_rank - 1]
    recent5 = runs[:5]
    recent_comp = [r for r in recent5 if r.margin is not None and r.margin <= 1.0]
    recent_high = [r for r in recent_comp if r.class_rank >= race.class_rank - 1]

    # 4段階の「床」。単発の最高CONTENTではなく、複数回の同距離好内容だけで上がる。
    if len(same_up) >= 2:
        strength = 4
        label = "同級以上で複数再現"
    elif len(same_up) >= 1 and len(one_down_up) >= 2:
        strength = 3
        label = "同級好内容＋近級複数"
    elif len(one_down_up) >= 2:
        strength = 2
        label = "近級で複数再現"
    elif len(competitive) >= 2:
        strength = 1
        label = "下級含む同距離複数"
    else:
        strength = 0
        label = "同距離の継続床なし"

    best_rank = max((r.class_rank for r in competitive), default=-9)
    recent_high_count = len(recent_high)

    # 最高帯だけ突出し、2本目/僅差本数が乏しい場合は「一発突出」として印を付ける。
    # 最高走そのものを消すのではなく、後段の競合でREPEAT側が逆転可能かを見るためのフラグ。
    isolated_spike = bool(
        cp.get("best_band", 0) >= 4
        and cp.get("close10", 0) <= 1
        and cp.get("second_band", 0) <= 2
    )

    # seed専用のCONTENT帯。単発突出だけを2段階まで圧縮し、最終比較は元のCONTENTを使う。
    # 例: 5→3, 4→3。継続証拠がある馬は元の帯をそのまま保持する。
    seed_content_band = cp.get("best_band", 0)
    if isolated_spike:
        seed_content_band = min(seed_content_band, 3)

    return {
        "strength": strength,
        "label": label,
        "competitive": len(competitive),
        "same_or_up": len(same_up),
        "one_down_or_up": len(one_down_up),
        "recent_high": recent_high_count,
        "best_rank": best_rank,
        "best_band": cp.get("best_band", 0),
        "second_band": cp.get("second_band", 0),
        "isolated_spike": isolated_spike,
        "seed_content_band": seed_content_band,
    }


def _repeat_profile_for_domain(
    domain_runs: List[PastRace],
    race: RaceInfo,
    clusters: Dict,
) -> Dict:
    """選んだ証拠ドメインの直近5走を、好走だけ消さずに丸ごと母数にする。"""
    recent5 = _recent(domain_runs)[:5]
    total = len(recent5)
    close03 = _count_close(recent5, 0.3)
    close06 = _count_close(recent5, 0.6)
    close10 = _count_close(recent5, 1.0)
    last3 = recent5[:3]
    last3_close10 = _count_close(last3, 1.0)

    known = total >= 2
    if not known:
        content_grade, content_label = 1, "材料不足"
    elif last3_close10 >= 2 or close10 >= 3:
        content_grade, content_label = 3, "強"
    elif close10 >= 2:
        content_grade, content_label = 2, "中"
    elif close10 >= 1:
        content_grade, content_label = 1, "単発"
    else:
        content_grade, content_label = 0, "弱"

    # CLOCK REPEATは別場の生時計を混ぜない。同場同距離に限定。
    exact_recent = [
        r for r in recent5
        if r.track == race.track and r.distance == race.distance and r.time_seconds is not None
    ]
    clock_known = len(exact_recent) >= 2
    clock_repeat = 0
    if clock_known:
        if clusters.get("reliable"):
            vals = [_cluster_for_time(r.time_seconds, clusters) for r in exact_recent]
            vals = [v for v in vals if v is not None]
            if vals:
                best_cluster = min(vals)
                clock_repeat = sum(1 for v in vals if v == best_cluster)
        else:
            positions = [_continuous_clock_position(r.time_seconds, clusters) for r in exact_recent]
            positions = [v for v in positions if v is not None]
            if positions:
                best_pos = max(positions)
                # 固定秒差ではなく、そのレース分布内の位置で「自馬ベスト帯」を再現した本数。
                clock_repeat = sum(1 for v in positions if v >= best_pos - 0.20)

    clock_grade = 0
    if clock_known:
        if clock_repeat >= 3:
            clock_grade = 3
        elif clock_repeat >= 2:
            clock_grade = 2
        elif clock_repeat >= 1:
            clock_grade = 1

    combined_grade = max(content_grade if known else 1, clock_grade)
    if not known and not clock_known:
        combined_label = "材料不足"
    elif combined_grade >= 3:
        combined_label = "強"
    elif combined_grade >= 2:
        combined_label = "中"
    elif combined_grade >= 1:
        combined_label = "単発"
    else:
        combined_label = "弱"

    return {
        "recent5": recent5,
        "denominator": total,
        "known": known,
        "content_grade": content_grade,
        "content_label": content_label,
        "close03": close03,
        "close06": close06,
        "close10": close10,
        "last3_close10": last3_close10,
        "clock_known": clock_known,
        "clock_repeat": clock_repeat,
        "clock_grade": clock_grade,
        "grade": combined_grade,
        "label": combined_label,
    }


def _current_for_domain(
    domain_runs: List[PastRace],
    race: RaceInfo,
    race_date: date,
    clusters: Dict,
) -> Dict:
    recent = _recent(domain_runs)
    if not recent:
        return {"grade": 2, "label": "判定不能", "detail": "比較可能走なし", "near_peak": 0, "confidence": "low"}

    state = _current_state(recent[:3], recent, race, race_date, clusters)
    latest_days = _days(recent[0], race_date)

    # 長いブランクでは過去PEAKを消さないが、CURRENTを現在値として断定しない。
    # 150日は固定減点ではなく「CURRENT信頼度を落とす」ための実装上のゲート。
    if latest_days >= 150:
        return {
            "grade": 2,
            "label": "判定不能",
            "detail": f"最新比較可能走が{latest_days}日前：長期ブランクでCURRENT信頼度低",
            "near_peak": state.get("near_peak", 0),
            "confidence": "low",
        }
    state = dict(state)
    state["confidence"] = "normal"
    return state


def build_horse_eval(race: RaceInfo, e: Entry, h: Optional[HorseHistory], race_date: date, clusters: Dict) -> Dict:
    surface = _surface_runs(h, race)
    same = [r for r in surface if r.distance == race.distance]
    exact = [r for r in same if r.track == race.track]
    other_same = [r for r in same if r.track != race.track]
    adj_same = _adjacent_runs(h, race, True)
    adj_other = _adjacent_runs(h, race, False)
    comp = _comparable_runs(h, race)
    last3, last5 = comp[:3], comp[:5]

    raw_exact = _best_time_run(exact)
    raw_same = _best_time_run(same)
    valid_exact = _best_time_run([r for r in exact if r.margin is not None and r.margin <= 1.0])
    valid_same = _best_content_run([r for r in same if r.margin is not None and r.margin <= 1.0], race_date)
    valid_adj_same = _best_content_run([r for r in adj_same if r.margin is not None and r.margin <= 1.0], race_date)
    valid_adj_other = _best_content_run([r for r in adj_other if r.margin is not None and r.margin <= 1.0], race_date)

    evidence_candidates = []
    for rs in (exact, other_same, adj_same, adj_other):
        evidence_candidates.extend(rs)
    best_evidence = min(evidence_candidates, key=lambda r: _condition_tier(race, r)) if evidence_candidates else None
    condition_tier = _condition_tier(race, best_evidence) if best_evidence else 99

    if valid_exact is not None:
        peak_type = "VALID"
        peak_run = valid_exact
    elif valid_same is not None:
        peak_type = "VALID"
        peak_run = valid_same
    elif raw_exact is not None or raw_same is not None:
        peak_type = "RAW"
        peak_run = raw_exact or raw_same
    else:
        peak_type = "不明"
        peak_run = valid_adj_same or valid_adj_other

    peak_cluster = clusters.get("cluster_by_num", {}).get(e.number)
    peak_cluster_reliable = bool(clusters.get("reliable") and peak_cluster is not None)
    best_content = _best_content_run(same if same else (adj_same + adj_other), race_date)
    repeat = _repeat_grade(last5, race, clusters)
    current = _current_state(last3, comp, race, race_date, clusters)
    classv = _class_value(same if same else (adj_same + adj_other), race)

    direct_known_margins = [r.margin for r in same if r.margin is not None]
    weak_direct = bool(direct_known_margins) and min(direct_known_margins) > 2.5

    same_class_close = [
        r for r in same
        if r.class_rank >= race.class_rank
        and r.margin is not None
        and r.margin <= 1.0
    ]
    one_down_close = [
        r for r in same
        if r.class_rank >= race.class_rank - 1
        and r.margin is not None
        and r.margin <= 1.0
    ]
    same_class_close03 = [r for r in same_class_close if r.margin is not None and r.margin <= 0.3]
    same_class_close06 = [r for r in same_class_close if r.margin is not None and r.margin <= 0.6]

    # JRA1600〜1800m：まず「同距離」と「近接距離」を別箱に保つ。
    # 重要：REPEAT用の母数から悪い走を消さない。
    jra_direct_runs = _recent(list(same))
    jra_adj_runs = _recent(list(adj_same + adj_other))
    jra_direct_content = _content_profile(jra_direct_runs, race_date)
    jra_adj_content = _content_profile(jra_adj_runs, race_date)

    jra_direct_good = [r for r in jra_direct_runs if r.margin is not None and r.margin <= 1.0]
    jra_adj_good = [
        r for r in jra_adj_runs
        if r.distance is not None
        and abs(r.distance - race.distance) <= 400
        and r.margin is not None
        and r.margin <= 0.6
        and (r.class_rank >= race.class_rank - 1 or r.margin <= 0.3)
    ]
    jra_adj_very_strong = [r for r in jra_adj_good if r.margin is not None and r.margin <= 0.3]

    # 「弱い直接」は経験不足ではなく、同距離の最良CONTENTが0.7〜1.0以下に留まる状態も含む。
    # その場合、同等クラスで0.6以内の強い近接があれば補強・逆転を許す。
    direct_best_band = jra_direct_content.get("best_band", 0)
    jra_direct_weak = bool(jra_direct_runs) and direct_best_band <= 3
    direct_good_best_class = max([r.class_rank for r in jra_direct_good], default=race.class_rank - 1)
    jra_adj_support = [
        r for r in jra_adj_good
        if r.class_rank >= direct_good_best_class
    ]
    jra_adj_override = jra_direct_weak and bool(jra_adj_support)

    if jra_direct_runs and not jra_direct_weak:
        jra_domain_runs = jra_direct_runs
        jra_selected_source = "同距離"
        jra_evidence_tier = 0
    elif jra_adj_override:
        # 近接だけへ置換せず、弱い直接も母数に残して「直接＋強い近接補強」として扱う。
        jra_domain_runs = _recent(jra_direct_runs + jra_adj_runs)
        jra_selected_source = "同距離＋強い近接補強"
        jra_evidence_tier = 1
    elif not jra_direct_runs and jra_adj_good:
        jra_domain_runs = jra_adj_runs
        jra_selected_source = "強い近接距離"
        jra_evidence_tier = 2
    elif jra_direct_runs:
        jra_domain_runs = jra_direct_runs
        jra_selected_source = "同距離・弱材料"
        jra_evidence_tier = 3
    elif jra_adj_runs:
        jra_domain_runs = jra_adj_runs
        jra_selected_source = "近接距離・補助"
        jra_evidence_tier = 4
    else:
        jra_domain_runs = []
        jra_selected_source = "材料薄"
        jra_evidence_tier = 9

    jra_content = _content_profile(jra_domain_runs, race_date)
    jra_class = _competitive_class_profile(jra_domain_runs, race, race_date)
    jra_repeat = _repeat_profile_for_domain(jra_domain_runs, race, clusters)
    jra_current = _current_for_domain(jra_domain_runs, race, race_date, clusters)
    # impl7: 最高1走と同距離の継続能力床を分離。
    # 既存5軸（CONTENT/REPEAT/クラス）を分解した診断値で、新しい採点軸ではない。
    jra_direct_floor = _jra_direct_floor_profile(jra_direct_runs, race, race_date)

    jra_primary_best = jra_content["best"]
    jra_primary_runs = jra_domain_runs
    jra_primary_content_key = jra_content["key"]
    jra_primary_content_band = jra_content["best_band"]
    jra_primary_source = jra_selected_source
    jra_primary_class_key = jra_class["key"]
    jra_primary_repeat_count = jra_repeat["close10"]
    jra_primary_close03 = jra_repeat["close03"]
    jra_repeat_grade = jra_repeat["grade"]
    jra_repeat_label = jra_repeat["label"]

    # 旧診断表示互換用。順位の絶対tierには使わない。
    if same_class_close:
        jra_tier = 0
        jra_run = _best_content_run(same_class_close, race_date)
    elif one_down_close:
        jra_tier = 1
        jra_run = _best_content_run(one_down_close, race_date)
    elif valid_same is not None:
        jra_tier = 2
        jra_run = valid_same
    elif same:
        jra_tier = 3
        jra_run = _best_content_run(same, race_date)
    elif valid_adj_same or valid_adj_other:
        jra_tier = 4
        jra_run = valid_adj_same or valid_adj_other
    else:
        jra_tier = 9
        jra_run = None

    jra_class_key = (
        max([r.class_rank for r in same_class_close], default=-9),
        max([_margin_level(r.margin) for r in same_class_close], default=0),
        len(same_class_close03),
        len(same_class_close06),
        len(same_class_close),
        -min([_days(r, race_date) for r in same_class_close], default=9999),
    )

    same03 = _count_close(same, 0.3)
    same06 = _count_close(same, 0.6)
    same10 = _count_close(same, 1.0)
    exact03 = _count_close(exact, 0.3)

    return {
        "number": e.number,
        "name": e.name,
        "analysis_date": race_date,
        "current_class_rank": race.class_rank,
        "_clusters_ref": clusters,
        "entry": e,
        "history": h,
        "surface": surface,
        "same": same,
        "exact": exact,
        "other_same": other_same,
        "adj_same": adj_same,
        "adj_other": adj_other,
        "last3": last3,
        "last5": last5,
        "condition_tier": condition_tier,
        "condition_label": _condition_text(condition_tier),
        "raw_exact": raw_exact,
        "raw_same": raw_same,
        "valid_exact": valid_exact,
        "valid_same": valid_same,
        "peak_type": peak_type,
        "peak_run": peak_run,
        "peak_cluster": peak_cluster,
        "peak_cluster_reliable": peak_cluster_reliable,
        "best_content": best_content,
        "best_content_tuple": _content_core_tuple(best_content, race_date),
        "repeat": repeat,
        "current": current,
        "class_value": classv,
        "weak_direct": weak_direct,
        "jra_tier": jra_tier,
        "jra_run": jra_run,
        "jra_content_tuple": _content_core_tuple(jra_run, race_date),
        "jra_class_key": jra_class_key,
        "jra_evidence_tier": jra_evidence_tier,
        "jra_direct_weak": jra_direct_weak,
        "jra_adj_override": jra_adj_override,
        "jra_selected_source": jra_selected_source,
        "jra_domain_runs": jra_domain_runs,
        "jra_content_profile": jra_content,
        "jra_class_profile": jra_class,
        "jra_repeat_profile": jra_repeat,
        "jra_current": jra_current,
        "jra_direct_floor": jra_direct_floor,
        "jra_repeat_grade": jra_repeat_grade,
        "jra_repeat_label": jra_repeat_label,
        "jra_primary_runs": jra_primary_runs,
        "jra_primary_best": jra_primary_best,
        "jra_primary_content_key": jra_primary_content_key,
        "jra_primary_content_band": jra_primary_content_band,
        "jra_primary_source": jra_primary_source,
        "jra_primary_class_key": jra_primary_class_key,
        "jra_primary_repeat_count": jra_primary_repeat_count,
        "jra_primary_close03": jra_primary_close03,
        "jra_adj_competitive_count": len(jra_adj_good),
        "jra_direct_competitive_count": len(jra_direct_good),
        "jra_same_class_close_count": len(same_class_close),
        "jra_same_class_close03": len(same_class_close03),
        "jra_same_class_close06": len(same_class_close06),
        "same03": same03,
        "same06": same06,
        "same10": same10,
        "exact03": exact03,
    }


# ============================================================
# 直接対戦
# ============================================================

def build_direct_matrix(race: RaceInfo, evals: Dict[int, Dict], race_date: date) -> Dict[Tuple[int, int], Dict]:
    groups: Dict[Tuple, Dict[int, PastRace]] = {}
    for n, ev in evals.items():
        for r in ev["surface"]:
            if r.race_date is None or r.distance is None:
                continue
            if abs(r.distance - race.distance) > 400:
                continue
            key = (r.race_date, r.track, r.race_name, r.surface, r.distance, r.going)
            groups.setdefault(key, {})[n] = r

    out = {}
    nums = list(evals)
    for i, a in enumerate(nums):
        for b in nums[i+1:]:
            wa = wb = 0
            meetings = []
            for key, members in groups.items():
                if a not in members or b not in members:
                    continue
                ra, rb = members[a], members[b]
                # 近い比較材料を優先し、極端に古いものも記録はする。
                winner = 0
                if ra.time_seconds is not None and rb.time_seconds is not None:
                    if ra.time_seconds < rb.time_seconds - 1e-9:
                        winner = a
                    elif rb.time_seconds < ra.time_seconds - 1e-9:
                        winner = b
                elif ra.finish is not None and rb.finish is not None:
                    if ra.finish < rb.finish:
                        winner = a
                    elif rb.finish < ra.finish:
                        winner = b
                if winner == a:
                    wa += 1
                elif winner == b:
                    wb += 1
                meetings.append({
                    "days": _days(ra, race_date),
                    "winner": winner,
                    "distance": ra.distance,
                    "same_distance": ra.distance == race.distance,
                    "class_rank": min(ra.class_rank, rb.class_rank),
                })
            out[(a, b)] = {"a_wins": wa, "b_wins": wb, "meetings": meetings}
            out[(b, a)] = {"a_wins": wb, "b_wins": wa, "meetings": meetings}
    return out


def build_shared_race_benchmarks(
    race: RaceInfo,
    evals: Dict[int, Dict],
) -> Dict[int, Dict]:
    """今回出走馬が複数そろった過去の同距離レースを「共通物差し」にする。

    別競馬場の生時計を横比較するのではなく、同じ日・同じ場・同じレース・
    同じ距離を走った馬同士だけ、そのレース内の実時計/着順で直接順位を作る。
    JRA1600〜1800mでは、現在クラス相当以上かつ競争になった共有レースを
    強い比較材料として扱う。馬番や既知の回帰正解は一切参照しない。
    """
    groups: Dict[Tuple, Dict[int, PastRace]] = {}
    for n, ev in evals.items():
        for r in ev.get("same", []):
            if r.race_date is None or r.distance != race.distance:
                continue
            key = (r.race_date, r.track, r.race_name, r.surface, r.distance, r.going)
            groups.setdefault(key, {})[n] = r

    race_date = next((ev.get("analysis_date") for ev in evals.values() if ev.get("analysis_date")), date.today())
    out: Dict[int, Dict] = {}

    for key, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(
            members.items(),
            key=lambda nr: (
                float("inf") if nr[1].time_seconds is None else nr[1].time_seconds,
                999 if nr[1].finish is None else nr[1].finish,
                nr[0],
            ),
        )
        participants = len(ordered)
        competitive_members = sum(
            1 for _, r in ordered
            if r.margin is not None and r.margin <= 1.0
        )
        # 同一レースのはずなので通常は全馬同じ。解析揺れがあっても過大評価しないよう最小値を採用。
        group_class = min((r.class_rank for _, r in ordered), default=-9)
        class_gap = max(0, race.class_rank - group_class)
        group_days = min((_days(r, race_date) for _, r in ordered), default=9999)

        for direct_rank, (n, r) in enumerate(ordered, 1):
            own_competitive = r.margin is not None and r.margin <= 1.0
            strong = bool(
                class_gap == 0
                and competitive_members >= 2
                and own_competitive
                and group_days <= 365
            )
            strength = 2 if strong and participants >= 3 else 1 if strong else 0
            margin_bad = (
                0 if r.margin is not None and r.margin <= 1.0
                else 1 if r.margin is not None and r.margin <= 1.5
                else 2 if r.margin is not None and r.margin <= 2.0
                else 4
            )
            candidate_key = (
                class_gap,
                0 if strong else 1,
                -participants,
                margin_bad,
                group_days,
                direct_rank,
            )
            candidate = {
                "key": candidate_key,
                "strength": strength,
                "strong": strong,
                "participants": participants,
                "direct_rank": direct_rank,
                "group_class": group_class,
                "class_gap": class_gap,
                "days": group_days,
                "race_key": key,
                "reason": (
                    f"共有同距離レース {key[1]} {key[2]}／{participants}頭共通／"
                    f"直接{direct_rank}位／class{group_class}"
                ),
            }
            if n not in out or candidate_key < out[n]["key"]:
                out[n] = candidate

    return out


def attach_shared_race_benchmarks(race: RaceInfo, evals: Dict[int, Dict]) -> Dict[int, Dict]:
    shared = build_shared_race_benchmarks(race, evals)
    for n, ev in evals.items():
        b = shared.get(n)
        ev["shared_benchmark"] = b
        ev["shared_strength"] = b.get("strength", 0) if b else 0
        ev["shared_reason"] = b.get("reason", "共有同距離レースなし") if b else "共有同距離レースなし"
    return shared


def _direct_cmp(a: int, b: int, matrix: Dict[Tuple[int, int], Dict]) -> int:
    d = matrix.get((a, b), {})
    aw, bw = d.get("a_wins", 0), d.get("b_wins", 0)
    if aw >= 2 and bw == 0:
        return 1
    if bw >= 2 and aw == 0:
        return -1
    if aw > bw and aw >= 1:
        return 1
    if bw > aw and bw >= 1:
        return -1
    return 0

def _direct_cmp_recent_same_distance(a: int, b: int, matrix: Dict[Tuple[int, int], Dict]) -> int:
    """JRA中距離で使う強い直接対戦。

    同距離かつ概ね1年以内の共有レースを優先する。
    1回でも明確な先着なら小さなCONTENT差のタイブレークに使い、
    2回以上同じ馬が先着ならDIRECT REPEATとしてさらに強い。
    """
    d = matrix.get((a, b), {})
    meetings = [
        m for m in d.get("meetings", [])
        if m.get("same_distance") and m.get("days", 9999) <= 365 and m.get("winner") in {a, b}
    ]
    if not meetings:
        return 0
    aw = sum(1 for m in meetings if m.get("winner") == a)
    bw = sum(1 for m in meetings if m.get("winner") == b)
    if aw >= 2 and bw == 0:
        return 2
    if bw >= 2 and aw == 0:
        return -2
    if aw > bw:
        return 1
    if bw > aw:
        return -1
    return 0


# ============================================================
# 競合判断
# ============================================================

def _soft_cmp(a: Dict, b: Dict, direct: Dict[Tuple[int, int], Dict], use_peak_time: bool = False) -> int:
    # 1) CONTENT
    if a["best_content_tuple"] != b["best_content_tuple"]:
        return 1 if a["best_content_tuple"] > b["best_content_tuple"] else -1
    # 2) REPEAT
    if a["repeat"]["grade"] != b["repeat"]["grade"]:
        return 1 if a["repeat"]["grade"] > b["repeat"]["grade"] else -1
    # 3) CURRENT（不明=中立2）
    if a["current"]["grade"] != b["current"]["grade"]:
        return 1 if a["current"]["grade"] > b["current"]["grade"] else -1
    # 4) 高クラス＋小差
    if a["class_value"]["rank"] != b["class_value"]["rank"]:
        return 1 if a["class_value"]["rank"] > b["class_value"]["rank"] else -1
    # 5) 直接対戦
    dc = _direct_cmp(a["number"], b["number"], direct)
    if dc:
        return dc
    # 6) 同場同距離なら生時計を最終タイブレーク
    if use_peak_time and a["raw_exact"] is not None and b["raw_exact"] is not None:
        ta, tb = a["raw_exact"].time_seconds, b["raw_exact"].time_seconds
        if ta != tb:
            return 1 if ta < tb else -1
    # 7) 条件近接
    if a["condition_tier"] != b["condition_tier"]:
        return 1 if a["condition_tier"] < b["condition_tier"] else -1
    # 8) 最後は馬番で完全決定（人気は不使用）
    return 1 if a["number"] < b["number"] else -1 if a["number"] > b["number"] else 0


def _can_reverse_adjacent_cluster(lower: Dict, upper: Dict) -> bool:
    # 下位クラスタ側が「VALID＋再現強＋現在高水準/上昇」なら隣接クラスタだけ逆転可能。
    lower_strong = (
        lower["peak_type"] == "VALID"
        and lower["repeat"]["grade"] >= 2
        and lower["current"]["grade"] >= 4
        and lower["best_content"] is not None
        and _margin_level(lower["best_content"].margin) >= 4
    )
    upper_weak = (
        upper["peak_type"] == "RAW"
        or upper["repeat"]["grade"] <= 1
        or upper["current"]["label"] == "下降"
    )
    return lower_strong and upper_weak


def _compare_local(a: Dict, b: Dict, direct: Dict[Tuple[int, int], Dict]) -> int:
    ae, be = bool(a["exact"]), bool(b["exact"])

    if ae and be:
        # 明確な時計クラスタがある場合は能力帯を先に見る。
        if a["peak_cluster_reliable"] and b["peak_cluster_reliable"]:
            ca, cb = a["peak_cluster"], b["peak_cluster"]
            if ca != cb:
                diff = abs(ca - cb)
                upper, lower = (a, b) if ca < cb else (b, a)
                if diff >= 2:
                    # 大差PEAK。ただし上位がRAW大差負け、下位がVALIDなら例外。
                    if upper["peak_type"] == "RAW" and lower["peak_type"] == "VALID" and lower["repeat"]["grade"] >= 2:
                        return 1 if lower is a else -1
                    return 1 if upper is a else -1
                # 隣接クラスタは強いCURRENT/REPEATで逆転可能。
                if _can_reverse_adjacent_cluster(lower, upper):
                    return 1 if lower is a else -1
                return 1 if upper is a else -1
        # 同クラスタ/断層なしならCONTENT・REPEAT・CURRENTを強く使う。
        return _soft_cmp(a, b, direct, use_peak_time=True)

    # 片方だけ同場同距離。強い直接実績なら地方では優先。
    if ae != be:
        ex, other = (a, b) if ae else (b, a)
        ex_valid = ex["valid_exact"] is not None or not ex["weak_direct"]
        other_strong = (
            other["valid_same"] is not None
            and other["repeat"]["grade"] >= 2
            and other["current"]["grade"] >= 4
        )
        if ex_valid and not other_strong:
            return 1 if ex is a else -1
        if ex["weak_direct"] and other_strong:
            return 1 if other is a else -1

    # 同場直接が弱い/無い場合は条件近接＋内容を比較。
    if a["condition_tier"] != b["condition_tier"]:
        # 直接実績が弱い場合は非常に強い隣接が逆転可。
        if a["weak_direct"] and b["peak_type"] == "VALID" and b["best_content"] and _margin_level(b["best_content"].margin) >= 4:
            return -1
        if b["weak_direct"] and a["peak_type"] == "VALID" and a["best_content"] and _margin_level(a["best_content"].margin) >= 4:
            return 1
        return 1 if a["condition_tier"] < b["condition_tier"] else -1
    return _soft_cmp(a, b, direct, use_peak_time=False)


def _compare_jra_middle_with_reason(
    a: Dict,
    b: Dict,
    direct: Dict[Tuple[int, int], Dict],
) -> Tuple[int, str]:
    """JRA1600〜1800mの競合判断（impl6）。

    v2.0-Betaの「CONTENT→競争になったクラス価値→REPEAT→CURRENT」を
    固い辞書順にはしない。CONTENT差が1帯だけなら他軸で逆転可能、
    2帯以上ならCONTENTを尊重する。これで小差を過大解釈しない。
    """
    ta, tb = a.get("jra_evidence_tier", 9), b.get("jra_evidence_tier", 9)
    if (ta == 9) != (tb == 9):
        winner = b if ta == 9 else a
        return (1 if winner is a else -1, "比較可能な同距離/近接距離材料の有無")

    # 同場同距離の自然断層が大きい時だけ、グローバルPEAK差ルールを先に適用。
    if (
        a["raw_exact"] is not None and b["raw_exact"] is not None
        and a["peak_cluster_reliable"] and b["peak_cluster_reliable"]
        and a["peak_cluster"] != b["peak_cluster"]
    ):
        pa, pb = a["peak_cluster"], b["peak_cluster"]
        diff = abs(pa - pb)
        upper, lower = (a, b) if pa < pb else (b, a)
        if diff >= 2:
            lower_rep = lower.get("jra_repeat_profile", {})
            if (
                upper["peak_type"] == "RAW"
                and lower["peak_type"] == "VALID"
                and lower_rep.get("known")
                and lower_rep.get("grade", 0) >= 2
            ):
                return (1 if lower is a else -1, "大PEAK差だが上位RAW／下位VALID再現で逆転")
            return (1 if upper is a else -1, "同場同距離VALID PEAKの大きな自然断層")

    ca = a.get("jra_content_profile", {})
    cb = b.get("jra_content_profile", {})
    ba, bb = ca.get("best_band", 0), cb.get("best_band", 0)
    content_leader = a if ba > bb else b if bb > ba else None
    content_gap = abs(ba - bb)

    # impl7: JRA中距離の「一発突出」と「同距離の継続能力床」を分離する。
    # 最高1走は消さないが、下級/単発の突出だけで、同距離を近いクラスで
    # 複数回まとめている馬を自動的に下へ固定しない。これはv2.0-Betaの
    # 「同PEAK帯ではREPEAT/CURRENTを重視」「高クラスは好内容とセット」の実装。
    fa = a.get("jra_direct_floor", {})
    fb = b.get("jra_direct_floor", {})

    if content_leader is not None:
        follower = b if content_leader is a else a
        lead_floor = fa if content_leader is a else fb
        follow_floor = fb if content_leader is a else fa
        lead_class = lead_floor.get("best_rank", -9)
        follow_class = follow_floor.get("best_rank", -9)
        floor_gap = follow_floor.get("strength", 0) - lead_floor.get("strength", 0)

        # 最高CONTENTが一発突出で、相手に近級以上の同距離好内容が複数ある場合、
        # CONTENT差2帯までならREPEAT＋クラス価値で逆転可能。
        if (
            content_gap <= 2
            and lead_floor.get("isolated_spike", False)
            and follow_floor.get("strength", 0) >= 2
            and floor_gap >= 1
            and follow_class >= lead_class
        ):
            return (1 if follower is a else -1, "一発CONTENT突出より同距離・近級の継続能力床")

        # 1帯差なら、一発判定でなくても同距離継続床が大きく上なら逆転を許す。
        if (
            content_gap == 1
            and follow_floor.get("strength", 0) >= 3
            and floor_gap >= 2
            and follow_class >= lead_class
        ):
            return (1 if follower is a else -1, "CONTENT小差を同距離継続床＋クラスで逆転")

    # CONTENT差が2帯以上なら基本は大差扱い。上の継続能力床例外がない限り尊重する。
    if content_leader is not None and content_gap >= 2:
        return (1 if content_leader is a else -1, f"CONTENT大差 {max(ba, bb)}帯>{min(ba, bb)}帯")

    # CONTENT同帯では、極端な継続床差がある時だけREPEAT/クラスの厚みを先に使う。
    if ba == bb:
        floor_a = (fa.get("strength", 0), fa.get("same_or_up", 0), fa.get("one_down_or_up", 0), fa.get("recent_high", 0))
        floor_b = (fb.get("strength", 0), fb.get("same_or_up", 0), fb.get("one_down_or_up", 0), fb.get("recent_high", 0))
        if abs(fa.get("strength", 0) - fb.get("strength", 0)) >= 2:
            winner = a if floor_a > floor_b else b
            return (1 if winner is a else -1, "同CONTENT帯→同距離継続能力床")

    # 今回クラス未満の証拠同士で最高CONTENT帯が同じなら、
    # 同場同距離PEAKの分布内相対差をCONTENT厚みより先に確認する。
    # これは別場時計比較ではなく、同じ今回競馬場・同距離だけのPEAK差。
    early_rank_a = a.get("jra_class_profile", {}).get("best_rank", -9)
    early_rank_b = b.get("jra_class_profile", {}).get("best_rank", -9)
    if (
        ba == bb
        and early_rank_a == early_rank_b
        and early_rank_a < a.get("current_class_rank", 999)
        and a.get("raw_exact") is not None
        and b.get("raw_exact") is not None
        and not (a.get("peak_cluster_reliable") and b.get("peak_cluster_reliable"))
    ):
        clusters_ref = a.get("_clusters_ref") or b.get("_clusters_ref")
        if clusters_ref and len(clusters_ref.get("rows", [])) >= 3:
            posa = _continuous_clock_position(a["raw_exact"].time_seconds, clusters_ref)
            posb = _continuous_clock_position(b["raw_exact"].time_seconds, clusters_ref)
        else:
            posa = posb = None
        if posa is not None and posb is not None and abs(posa - posb) >= 0.35:
            winner = a if posa > posb else b
            return (1 if winner is a else -1, "下級条件同CONTENT帯→同場同距離PEAK相対差")

    # 同じCONTENT帯では、最高1走だけでなく2本目・僅差証拠の厚みを見る。
    if ba == bb:
        support_a = (
            ca.get("second_band", 0),
            ca.get("close03", 0),
            ca.get("close06", 0),
            ca.get("close10", 0),
        )
        support_b = (
            cb.get("second_band", 0),
            cb.get("close03", 0),
            cb.get("close06", 0),
            cb.get("close10", 0),
        )
        # 2本目の内容帯が2段以上違うなど、明確なCONTENT厚み差だけここで決める。
        if abs(support_a[0] - support_b[0]) >= 2:
            winner = a if support_a > support_b else b
            return (1 if winner is a else -1, "CONTENTの2本目・再現幅に明確差")

    # 競争になった高クラス価値。<=1.0秒の走だけなのでクラス単独ボーナスではない。
    cla = a.get("jra_class_profile", {})
    clb = b.get("jra_class_profile", {})
    rank_a, rank_b = cla.get("best_rank", -9), clb.get("best_rank", -9)
    class_core_a = (
        rank_a,
        cla.get("best_band", 0),
        cla.get("same_or_up", 0),
        cla.get("one_down_or_up", 0),
        cla.get("close03_high", 0),
    )
    class_core_b = (
        rank_b,
        clb.get("best_band", 0),
        clb.get("same_or_up", 0),
        clb.get("one_down_or_up", 0),
        clb.get("close03_high", 0),
    )

    # CONTENTが1帯差だけなら、より高いクラスで競争になった証拠があれば逆転可。
    if content_leader is not None and content_gap == 1 and rank_a != rank_b:
        class_winner = a if class_core_a > class_core_b else b
        if class_winner is not content_leader and abs(rank_a - rank_b) >= 1:
            return (1 if class_winner is a else -1, "CONTENT小差を高クラス好内容で逆転")

    # CONTENT同帯では「クラス順位そのもの」が違う時だけここで決める。
    # 同じクラス内の着差を再びここで比べるとCONTENTの二重評価になるため行わない。
    if ba == bb and rank_a != rank_b:
        winner = a if rank_a > rank_b else b
        return (1 if winner is a else -1, "同CONTENT帯→より高いクラスで好内容")

    # 共有した同距離レースは強いタイブレーク。
    # CONTENT差が大きい時は使わないが、同帯/1帯差なら実際の直接先着を尊重する。
    dcs = _direct_cmp_recent_same_distance(a["number"], b["number"], direct)
    if dcs and content_gap <= 1:
        winner = a if dcs > 0 else b
        label = "DIRECT REPEAT" if abs(dcs) >= 2 else "同距離・直接対戦"
        return (1 if winner is a else -1, label)

    # REPEAT：必ず悪い走も含む「直近5ドメイン走」を母数にする。
    ra = a.get("jra_repeat_profile", {})
    rb = b.get("jra_repeat_profile", {})
    known_a, known_b = bool(ra.get("known")), bool(rb.get("known"))
    if known_a and known_b:
        rep_a = (
            ra.get("grade", 0),
            ra.get("close03", 0),
            ra.get("close06", 0),
            ra.get("close10", 0),
            ra.get("clock_grade", 0),
            ra.get("clock_repeat", 0),
        )
        rep_b = (
            rb.get("grade", 0),
            rb.get("close03", 0),
            rb.get("close06", 0),
            rb.get("close10", 0),
            rb.get("clock_grade", 0),
            rb.get("clock_repeat", 0),
        )
        if rep_a != rep_b:
            winner = a if rep_a > rep_b else b
            # 1帯CONTENT差の側がREPEATで明確に勝つなら逆転を許す。
            if content_leader is None or content_gap <= 1:
                return (1 if winner is a else -1, "REPEAT（直近5比較可能走・悪走込み）")
    elif known_a != known_b:
        known_ev, known_rep = (a, ra) if known_a else (b, rb)
        # 材料不足そのものを減点しない。ただし既知側に複数回の明確な再現がある時だけ採用。
        if known_rep.get("grade", 0) >= 2 and known_rep.get("close10", 0) >= 2:
            return (1 if known_ev is a else -1, "REPEAT既知側に複数再現／相手は材料不足")

    # CURRENT：選択ドメインの直近3走だけ。古いPEAKはここへ混ぜない。
    ua = a.get("jra_current", a["current"])
    ub = b.get("jra_current", b["current"])
    if ua.get("grade", 2) != ub.get("grade", 2):
        winner = a if ua.get("grade", 2) > ub.get("grade", 2) else b
        if content_leader is None or content_gap <= 1:
            return (1 if winner is a else -1, f"CURRENT {winner.get('jra_current', winner['current'])['label']}")

    # ここまでで逆転根拠が無ければ、1帯だけのCONTENTリードを尊重。
    if content_leader is not None:
        return (1 if content_leader is a else -1, "CONTENT小差を他軸で覆す根拠なし")

    # CONTENT同帯で未決なら、残りのCONTENT厚みを弱いタイブレークに使う。
    support_a = (
        ca.get("second_band", 0), ca.get("close03", 0), ca.get("close06", 0), ca.get("close10", 0)
    )
    support_b = (
        cb.get("second_band", 0), cb.get("close03", 0), cb.get("close06", 0), cb.get("close10", 0)
    )
    if support_a != support_b:
        winner = a if support_a > support_b else b
        return (1 if winner is a else -1, "CONTENT厚みタイブレーク")

    # 直接対戦。
    dc = _direct_cmp(a["number"], b["number"], direct)
    if dc:
        return dc, "同一レース直接対戦"

    # 他軸同等時だけ証拠の直接性。
    if ta != tb:
        winner = a if ta < tb else b
        return (1 if winner is a else -1, "主証拠の直接性（他軸同等時）")

    pscore = {"VALID": 2, "RAW": 1, "不明": 0}
    pta, ptb = pscore.get(a["peak_type"], 0), pscore.get(b["peak_type"], 0)
    if pta != ptb:
        winner = a if pta > ptb else b
        return (1 if winner is a else -1, f"PEAK種別 {winner['peak_type']}")

    # 同場同距離生時計は最後だけ。別場生時計は一切ここへ来ない。
    if a["raw_exact"] is not None and b["raw_exact"] is not None:
        if a["raw_exact"].time_seconds != b["raw_exact"].time_seconds:
            winner = a if a["raw_exact"].time_seconds < b["raw_exact"].time_seconds else b
            return (1 if winner is a else -1, "同場同距離生時計・最終タイブレーク")

    if a["condition_tier"] != b["condition_tier"]:
        winner = a if a["condition_tier"] < b["condition_tier"] else b
        return (1 if winner is a else -1, "CONDITION最終タイブレーク")

    if a["number"] == b["number"]:
        return 0, "完全同等"
    winner = a if a["number"] < b["number"] else b
    return (1 if winner is a else -1, "完全同等のため馬番タイブレーク")


def _compare_jra_middle(a: Dict, b: Dict, direct: Dict[Tuple[int, int], Dict]) -> int:
    return _compare_jra_middle_with_reason(a, b, direct)[0]


def _long_tier(ev: Dict) -> int:
    if ev["valid_exact"] is not None:
        return 0
    if ev["valid_same"] is not None and ev["same"]:
        return 1
    strong_adj = [r for r in ev["adj_same"] + ev["adj_other"] if r.margin is not None and r.margin <= 0.6]
    if strong_adj:
        return 2
    if ev["same"]:
        return 3
    if ev["adj_same"]:
        return 4
    if ev["adj_other"]:
        return 5
    return 9


def _compare_long(a: Dict, b: Dict, direct: Dict[Tuple[int, int], Dict]) -> int:
    ta, tb = _long_tier(a), _long_tier(b)
    if ta != tb:
        # 強い隣接（2）は弱い直接（3）を上回るルールをtier化済み。
        return 1 if ta < tb else -1
    if ta == 0 and a["raw_exact"] is not None and b["raw_exact"] is not None:
        if a["peak_cluster_reliable"] and b["peak_cluster_reliable"] and a["peak_cluster"] != b["peak_cluster"]:
            return 1 if a["peak_cluster"] < b["peak_cluster"] else -1
    return _soft_cmp(a, b, direct, use_peak_time=(ta == 0))


def compare_evals_with_reason(a: Dict, b: Dict, race: RaceInfo, direct: Dict[Tuple[int, int], Dict]) -> Tuple[int, str]:
    """比較結果と、実際にreturnした決着理由を返す。

    impl7でもJRA1600〜1800mの理由表示を比較関数そのものと共通化し、
    表示理由と実際の順位決定が食い違わないようにする。
    """
    if race.track in JRA_TRACKS and 1600 <= race.distance <= 1800:
        return _compare_jra_middle_with_reason(a, b, direct)

    c = compare_evals(a, b, race, direct)
    if race.distance >= 2000:
        reason = "2000m以上ルール（直接距離/強い隣接＋5軸）"
    else:
        reason = "地方・その他ルール（同場同距離＋5軸）"
    return c, reason


def compare_evals(a: Dict, b: Dict, race: RaceInfo, direct: Dict[Tuple[int, int], Dict]) -> int:
    if race.track in JRA_TRACKS and 1600 <= race.distance <= 1800:
        return _compare_jra_middle(a, b, direct)
    if race.distance >= 2000:
        return _compare_long(a, b, direct)
    return _compare_local(a, b, direct)


def _jra_middle_seed_key(race: RaceInfo, ev: Dict) -> Tuple:
    """JRA1600〜1800mの推移的な初期順位（impl7）。

    impl6の粗いability_layerを廃止。最高1走だけでレース全体を硬く階層化せず、
    CONTENTの代表帯→競争になったクラス価値→同距離継続床→CONTENT厚み→
    REPEAT→CURRENTの順でseedを作る。共有同距離レースは強い補助物差し。

    seedはあくまで初期順で、最終的には同じ証拠を使うペア比較で再監査する。
    人気・オッズ・別場の生時計は使わない。
    """
    cp = ev.get("jra_content_profile", {})
    cl = ev.get("jra_class_profile", {})
    rp = ev.get("jra_repeat_profile", {})
    cu = ev.get("jra_current", ev.get("current", {}))
    floor = ev.get("jra_direct_floor", {})
    source_tier = ev.get("jra_evidence_tier", 9)
    has_material = 0 if source_tier == 9 else 1

    # 一発突出をseedだけで硬く固定しない。元のbest_bandは比較関数に残る。
    seed_content_band = floor.get("seed_content_band", cp.get("best_band", 0))
    if ev.get("jra_selected_source") in {"強い近接距離", "同距離＋強い近接補強"}:
        # 強い近接で成立している馬は、直接floorが薄くてもprimary CONTENTを失わせない。
        # ただし一発突出なら1段だけ穏やかにする。
        seed_content_band = cp.get("best_band", 0)
        if (
            cp.get("best_band", 0) >= 4
            and cp.get("close10", 0) <= 1
            and cp.get("second_band", 0) <= 2
        ):
            seed_content_band = max(3, cp.get("best_band", 0) - 1)

    shared = ev.get("shared_benchmark") or {}
    shared_strength = shared.get("strength", 0)
    shared_rank_score = (
        shared.get("participants", 0) - shared.get("direct_rank", 99) + 1
        if shared_strength > 0 else 0
    )

    # 下級証拠同士の最後の補助だけ、同場同距離の分布内位置を使う。
    lower_peak_support = -1.0
    clusters_ref = ev.get("_clusters_ref", {})
    if (
        cl.get("best_rank", -9) < race.class_rank
        and ev.get("raw_exact") is not None
        and len(clusters_ref.get("rows", [])) >= 3
    ):
        lower_peak_support = _continuous_clock_position(
            ev["raw_exact"].time_seconds, clusters_ref
        ) or 0.0

    return (
        has_material,
        seed_content_band,
        cl.get("best_rank", -9),
        cl.get("best_band", 0),
        floor.get("strength", 0),
        floor.get("same_or_up", 0),
        floor.get("one_down_or_up", 0),
        cp.get("second_band", 0),
        cp.get("close03", 0),
        cp.get("close06", 0),
        cp.get("close10", 0),
        shared_strength,
        shared_rank_score,
        rp.get("grade", 0) if rp.get("known") else 1,
        rp.get("close10", 0),
        cu.get("grade", 2),
        -source_tier,
        lower_peak_support,
        -ev.get("condition_tier", 99),
        -ev.get("number", 999),
    )

def _baseline_key(race: RaceInfo, ev: Dict) -> Tuple:
    """pairwise競合の同点処理に使う推移的な骨格。人気・オッズは不使用。"""
    n = ev["number"]
    peak_type_score = {"VALID": 2, "RAW": 1, "不明": 0}.get(ev["peak_type"], 0)
    exact_time = -ev["raw_exact"].time_seconds if ev["raw_exact"] is not None else -9999.0
    cluster_score = -ev["peak_cluster"] if ev["peak_cluster_reliable"] else -99

    if race.track in JRA_TRACKS and 1600 <= race.distance <= 1800:
        cp = ev.get("jra_content_profile", {})
        cl = ev.get("jra_class_profile", {})
        rp = ev.get("jra_repeat_profile", {})
        cu = ev.get("jra_current", ev["current"])
        has_material = 0 if ev.get("jra_evidence_tier", 9) == 9 else 1
        # これは最終ルールではなく、pairwise勝敗同点時の安定化キー。
        return (
            has_material,
            cp.get("best_band", 0),
            cl.get("best_rank", -9),
            cp.get("second_band", 0),
            cp.get("close10", 0),
            rp.get("grade", 0) if rp.get("known") else 1,
            cu.get("grade", 2),
            peak_type_score,
            -ev.get("jra_evidence_tier", 9),
            cluster_score,
            -ev["condition_tier"],
            exact_time,
            -n,
        )

    if race.distance >= 2000:
        return (
            -_long_tier(ev), cluster_score, ev["best_content_tuple"],
            ev["repeat"]["grade"], ev["current"]["grade"], ev["class_value"]["rank"],
            peak_type_score, -ev["condition_tier"], exact_time, -n,
        )

    return (
        1 if ev["exact"] else 0, cluster_score, ev["best_content_tuple"],
        ev["repeat"]["grade"], ev["current"]["grade"], ev["class_value"]["rank"],
        peak_type_score, -ev["condition_tier"], exact_time, -n,
    )


def rank_evals(race: RaceInfo, evals: Dict[int, Dict], direct: Dict[Tuple[int, int], Dict]) -> List[int]:
    """証拠層のseedを作り、競合ルールでTOP8を隣接再監査する。

    JRA1600〜1800mはCopeland型の総当たり勝数を初期順位に使わない。
    非推移な比較で「他馬への勝ち数が多い馬」が共通物差しの直接順位を壊すため、
    CONTENT/競争になったクラス/共有レース/REPEAT/CURRENTの証拠層でseedを作る。
    総当たりは診断ログとして残し、最終形成はseed＋隣接競合で行う。
    """
    attach_shared_race_benchmarks(race, evals)
    items = list(evals.values())
    wins = {ev["number"]: 0 for ev in items}
    losses = {ev["number"]: 0 for ev in items}
    pair_events = []

    for i, a in enumerate(items):
        for b in items[i + 1:]:
            cmpv, reason = compare_evals_with_reason(a, b, race, direct)
            if cmpv > 0:
                winner, loser = a, b
            elif cmpv < 0:
                winner, loser = b, a
            else:
                continue
            wins[winner["number"]] += 1
            losses[loser["number"]] += 1
            pair_events.append({
                "a": a["number"], "b": b["number"],
                "winner": winner["number"], "reason": reason,
            })

    jra_middle = race.track in JRA_TRACKS and 1600 <= race.distance <= 1800
    if jra_middle:
        ordered = sorted(items, key=lambda ev: _jra_middle_seed_key(race, ev), reverse=True)
        seed_mode = "JRA証拠層seed＋隣接監査"
    else:
        ordered = sorted(
            items,
            key=lambda ev: (
                wins[ev["number"]],
                -losses[ev["number"]],
                _baseline_key(race, ev),
            ),
            reverse=True,
        )
        seed_mode = "総当たり勝敗seed＋隣接監査"

    audit_len = min(8, len(ordered))
    baseline_all = tuple(ev["number"] for ev in ordered)
    baseline_head = tuple(ev["number"] for ev in ordered[:audit_len])
    cycle_detected = False
    audit_events = []
    admission_events = []

    if jra_middle and len(ordered) > audit_len:
        # impl8: TOP8へ切る前に全頭を監査する。
        # impl7はseed 9位以下の馬を比較関数へ戻せず、強い近接距離馬などが
        # 永久にTOP8外へ固定される構造だった。
        # ここではseedは「初期候補順」に限定し、TOP8外の全馬に8位境界への挑戦権を与える。
        head = list(ordered[:audit_len])
        tail = list(ordered[audit_len:])

        # 強い競合を先に確認するため、tailは総当たり勝数→seed順で診断順だけ整える。
        seed_pos = {ev["number"]: i for i, ev in enumerate(ordered)}
        tail.sort(
            key=lambda ev: (wins[ev["number"]], -losses[ev["number"]], -seed_pos[ev["number"]]),
            reverse=True,
        )

        # 状態循環を防ぎながら、TOP8外→8位境界→上位へバブルアップ。
        seen_heads = {tuple(ev["number"] for ev in head)}
        max_rounds = max(1, len(items) * 2)
        for round_no in range(max_rounds):
            changed = False
            next_tail = []
            for challenger in tail:
                if not head:
                    head.append(challenger)
                    changed = True
                    continue
                cmpv, reason = compare_evals_with_reason(challenger, head[-1], race, direct)
                if cmpv <= 0:
                    next_tail.append(challenger)
                    continue

                displaced = head[-1]
                head[-1] = challenger
                next_tail.append(displaced)
                changed = True
                admission_events.append({
                    "round": round_no + 1,
                    "IN": challenger["number"],
                    "OUT": displaced["number"],
                    "boundary_reason": reason,
                })

                # 入った馬は、実際の比較関数で勝てるところまで上へ。
                idx = len(head) - 1
                while idx > 0:
                    cmp_up, reason_up = compare_evals_with_reason(head[idx], head[idx - 1], race, direct)
                    if cmp_up <= 0:
                        break
                    audit_events.append({
                        "pass": f"admit-{round_no + 1}",
                        "from": (head[idx - 1]["number"], head[idx]["number"]),
                        "to": (head[idx]["number"], head[idx - 1]["number"]),
                        "reason": reason_up,
                    })
                    head[idx - 1], head[idx] = head[idx], head[idx - 1]
                    idx -= 1

            state = tuple(ev["number"] for ev in head)
            if state in seen_heads and changed:
                cycle_detected = True
                admission_events.append({"round": round_no + 1, "cycle": True, "state": state})
                break
            seen_heads.add(state)
            tail = next_tail
            if not changed:
                break

        # TOP8内部の隣接再監査。seed順ではなく、全頭境界監査後のheadを対象にする。
        seen = {tuple(ev["number"] for ev in head)}
        for pass_no in range(max(1, audit_len)):
            changed = False
            for i in range(len(head) - 1):
                challenger, incumbent = head[i + 1], head[i]
                cmpv, reason = compare_evals_with_reason(challenger, incumbent, race, direct)
                if cmpv > 0:
                    audit_events.append({
                        "pass": pass_no + 1,
                        "from": (incumbent["number"], challenger["number"]),
                        "to": (challenger["number"], incumbent["number"]),
                        "reason": reason,
                    })
                    head[i], head[i + 1] = challenger, incumbent
                    changed = True
            state = tuple(ev["number"] for ev in head)
            if not changed:
                break
            if state in seen:
                cycle_detected = True
                audit_events.append({"pass": pass_no + 1, "cycle": True, "state": state})
                break
            seen.add(state)

        # tailは最終TOP8の外。seed順へ戻して表示を安定化。
        head_nums = {ev["number"] for ev in head}
        tail = [ev for ev in ordered if ev["number"] not in head_nums]
        seed_mode = "JRA証拠層seed＋全頭TOP8境界監査＋隣接監査"
    else:
        head = list(ordered[:audit_len])
        tail = list(ordered[audit_len:])
        seen = {tuple(ev["number"] for ev in head)}
        for pass_no in range(max(1, audit_len)):
            changed = False
            for i in range(len(head) - 1):
                challenger, incumbent = head[i + 1], head[i]
                cmpv, reason = compare_evals_with_reason(challenger, incumbent, race, direct)
                if cmpv > 0:
                    audit_events.append({
                        "pass": pass_no + 1,
                        "from": (incumbent["number"], challenger["number"]),
                        "to": (challenger["number"], incumbent["number"]),
                        "reason": reason,
                    })
                    head[i], head[i + 1] = challenger, incumbent
                    changed = True
            state = tuple(ev["number"] for ev in head)
            if not changed:
                break
            if state in seen:
                cycle_detected = True
                audit_events.append({"pass": pass_no + 1, "cycle": True, "state": state})
                break
            seen.add(state)

    shared_trace = {
        "pairwise_events": pair_events,
        "pairwise_seed": list(baseline_head),
        "seed_mode": seed_mode,
        "evidence_seed": list(baseline_head),
        "evidence_seed_all": list(baseline_all),
        "admission_events": admission_events,
        "shared_benchmarks": {
            ev["number"]: ev.get("shared_reason", "共有同距離レースなし")
            for ev in items if ev.get("shared_benchmark")
        },
        "audit_events": audit_events,
        "cycle_detected": cycle_detected,
    }
    for ev in items:
        ev["ranking_cycle_detected"] = cycle_detected
        ev["pairwise_wins"] = wins[ev["number"]]
        ev["pairwise_losses"] = losses[ev["number"]]
        ev["seed_rank"] = baseline_all.index(ev["number"]) + 1
        ev["ranking_trace"] = shared_trace

    return [x["number"] for x in (head + tail)]


# ============================================================
# ガード
# ============================================================

def _is_upper_environment(track: str) -> bool:
    return track in JRA_TRACKS or track in {"浦和", "船橋", "大井", "川崎"}


def _transfer_candidate(race: RaceInfo, ev: Dict) -> bool:
    e: Entry = ev["entry"]
    h: Optional[HorseHistory] = ev["history"]
    if race.track not in NAR_TRACKS or e.popularity > 3 or not h or not h.races:
        return False
    recent = _recent(h.races)
    prev = recent[0]
    # 直前が上位環境で、今回場の過去歴がない時のみ。
    return _is_upper_environment(prev.track) and not any(r.track == race.track for r in recent)


def _same_ability_band(a: Dict, b: Dict) -> bool:
    if a["peak_cluster_reliable"] and b["peak_cluster_reliable"]:
        return a["peak_cluster"] == b["peak_cluster"]
    # クラスタが作れない時は、条件層とCONTENT帯が近い場合のみ同等扱い。
    ca = _margin_level(a["best_content"].margin) if a["best_content"] else 0
    cb = _margin_level(b["best_content"].margin) if b["best_content"] else 0
    return abs(a["condition_tier"] - b["condition_tier"]) <= 1 and abs(ca - cb) <= 1


def apply_guards(race: RaceInfo, entries: List[Entry], evals: Dict[int, Dict], normal: List[int], clusters: Dict, direct: Dict[Tuple[int, int], Dict]) -> Tuple[List[int], Dict]:
    by_num = {e.number: e for e in entries}
    pos = {n: i+1 for i, n in enumerate(normal)}
    target_len = min(6, len(normal))
    base = list(normal[:target_len])

    absolute = []
    transfer = []
    boundary = []
    debut = []
    first_dist = []
    fast_big = []

    # 警戒・絶対
    for n, ev in evals.items():
        e = by_num[n]
        if not ev["history"] or not ev["history"].races:
            if e.popularity <= 5:
                debut.append(n)

        if not ev["same"] and (ev["adj_same"] or ev["adj_other"]):
            adj = ev["adj_same"] + ev["adj_other"]
            if any(r.margin is not None and r.margin <= 1.0 for r in adj):
                first_dist.append(n)

        if ev["raw_exact"] is not None and ev["raw_exact"].margin is not None and ev["raw_exact"].margin > 1.0:
            raw_rank = next((x.get("raw_rank") for x in clusters.get("rows", []) if x["number"] == n), None)
            if (ev["peak_cluster_reliable"] and ev["peak_cluster"] == 1) or (raw_rank is not None and raw_rank <= 3):
                fast_big.append(n)

        # 絶対時計ガードは「RAW最速がC1」だけでは不可。
        # 勝利/0.3以内を記録したその走自体がVALID PEAKの最上位クラスタに属する時だけ。
        valid_peak_cluster1 = any(
            r.margin is not None
            and r.margin <= 0.3
            and _cluster_for_time(r.time_seconds, clusters) == 1
            for r in ev["exact"]
            if r.time_seconds is not None
        )
        if clusters.get("reliable") and valid_peak_cluster1:
            absolute.append(n)

        if _transfer_candidate(race, ev):
            transfer.append(n)

    # 境界は通常7〜8位だけ。6位と同等能力帯＋同距離0.3以内。
    sixth = normal[5] if len(normal) >= 6 else None
    if sixth is not None:
        for n in normal:
            if pos[n] not in {7, 8}:
                continue
            ev = evals[n]
            if ev["same03"] > 0 and _same_ability_band(ev, evals[sixth]):
                boundary.append(n)

    conflict = False
    forced_outside = []
    for kind, nums in (("absolute", absolute), ("transfer", transfer)):
        for n in nums:
            if n not in base and n not in [x[1] for x in forced_outside]:
                forced_outside.append((kind, n))

    # 境界ガードは「6位枠だけ」の保護。7〜8位に複数候補がいる時は、
    # その候補同士を5軸比較して1頭だけを6位枠へ送る。上位5頭は通常時に触らない。
    boundary_outside = [n for n in boundary if n not in base]
    if boundary_outside:
        chosen_boundary = boundary_outside[0]
        for n in boundary_outside[1:]:
            if compare_evals(evals[n], evals[chosen_boundary], race, direct) > 0:
                chosen_boundary = n
        forced_outside.append(("boundary", chosen_boundary))
        if len(boundary_outside) > 1:
            conflict = True

    conflict = conflict or (
        len(forced_outside)
        > max(0, target_len - sum(1 for n in base if n in absolute or n in transfer or n in boundary))
    )

    top6 = list(base)
    protected = set(n for n in top6 if n in absolute or n in transfer or n in boundary)
    for kind, n in forced_outside:
        if n in top6:
            protected.add(n)
            continue
        candidates = [x for x in top6 if x not in protected]
        if not candidates:
            # 全枠がガード競合した場合は5軸比較で最弱を置換。
            candidates = list(top6)
            conflict = True

        if kind == "boundary" and top6[-1] not in protected:
            # 通常の境界保護は必ず現在6位だけを置換。上位5頭へ昇格させない。
            replace = top6[-1]
        else:
            # 絶対/転入、または既に6位枠が別ガードで保護された競合時だけ5軸再比較。
            replace = candidates[-1]
            for x in reversed(candidates):
                if compare_evals(evals[n], evals[x], race, direct) >= 0:
                    replace = x
                    break
        idx = top6.index(replace)
        top6[idx] = n
        protected.add(n)

    # 重複除去し、通常順で補完。
    clean = []
    for n in top6:
        if n not in clean:
            clean.append(n)
    for n in normal:
        if len(clean) >= target_len:
            break
        if n not in clean:
            clean.append(n)

    # 通常選出は通常順位順。ガード外加入は末尾側へ。
    normal_pos = {n: i for i, n in enumerate(normal)}
    normal_members = sorted([n for n in clean if n in normal[:target_len]], key=lambda n: normal_pos[n])
    forced_members = sorted([n for n in clean if n not in normal[:target_len]], key=lambda n: normal_pos[n])
    final = (normal_members + forced_members)[:target_len]

    return final, {
        "absolute": absolute,
        "transfer": transfer,
        "boundary": boundary,
        "debut_warning": debut,
        "first_distance_warning": first_dist,
        "fast_big_margin_warning": fast_big,
        "guard_conflict": conflict,
    }


# ============================================================
# 表示・理由
# ============================================================

def _fmt_time_run(r: Optional[PastRace]) -> str:
    if r is None or r.time_seconds is None:
        return "—"
    return format_time(r.time_seconds)


def _eval_reason(ev: Dict) -> str:
    parts = [ev["condition_label"]]
    if ev["raw_exact"] is not None:
        parts.append(f"同場同距離{format_time(ev['raw_exact'].time_seconds)}")
        if ev["raw_exact"].margin is not None:
            parts.append(f"ベスト時{ev['raw_exact'].margin:.1f}差")
    elif ev["valid_same"] is not None:
        parts.append(f"同距離{_margin_label(ev['valid_same'].margin)}")
    elif ev["best_content"] is not None:
        parts.append(f"隣接距離{_margin_label(ev['best_content'].margin)}")
    if ev["peak_cluster_reliable"]:
        parts.append(f"時計クラスタ{ev['peak_cluster']}")
    parts.append(f"PEAK {ev['peak_type']}")
    if ev.get("shared_strength", 0) > 0:
        sb = ev.get("shared_benchmark", {})
        parts.append(f"共有物差し{sb.get('participants', 0)}頭・直接{sb.get('direct_rank', '-')}位")
    parts.append(f"REPEAT {ev['repeat']['label']}")
    parts.append(f"CURRENT {ev['current']['label']}")
    return " / ".join(parts)


def _five_axis_row(ev: Dict) -> Dict:
    peak_text = "材料不足"
    if ev["peak_run"] is not None:
        peak_text = _fmt_time_run(ev["peak_run"])
        if ev["peak_run"].margin is not None:
            peak_text += f"／{ev['peak_run'].margin:.1f}差"
        if ev["peak_cluster_reliable"]:
            peak_text += f"／C{ev['peak_cluster']}"
    content_text = "材料不足"
    if ev["best_content"] is not None:
        content_text = f"{_margin_label(ev['best_content'].margin)}／class{ev['best_content'].class_rank}"
    return {
        "馬番": ev["number"],
        "馬名": ev["name"],
        "CONDITION": ev["condition_label"],
        "PEAK": peak_text,
        "PEAK種別": ev["peak_type"],
        "CONTENT": content_text,
        "REPEAT": f"{ev['repeat']['label']}（好内容{ev['repeat']['content_high']}／時計再現{ev['repeat']['clock_high'] if ev['repeat'].get('clock_known') else '判定不能'}）",
        "CURRENT": f"{ev['current']['label']}｜{ev['current']['detail']}",
        "クラス価値": ev["class_value"]["label"],
        "JRA主証拠": (
            f"{ev.get('jra_primary_source','材料薄')}／{_margin_label(ev['jra_primary_best'].margin)}／class{ev['jra_primary_best'].class_rank}"
            if ev.get("jra_primary_best") is not None else "材料薄"
        ),
        "JRA主証拠本数": len(ev.get("jra_domain_runs", [])),
        "JRA_CONTENT帯": ev.get("jra_content_profile", {}).get("best_band", 0),
        "JRA_CONTENT2本目": ev.get("jra_content_profile", {}).get("second_band", 0),
        "JRA_REP母数": ev.get("jra_repeat_profile", {}).get("denominator", 0),
        "JRA_REP0.3内": ev.get("jra_repeat_profile", {}).get("close03", 0),
        "JRA_REP0.6内": ev.get("jra_repeat_profile", {}).get("close06", 0),
        "JRA_REP1.0内": ev.get("jra_repeat_profile", {}).get("close10", 0),
        "JRA_CLOCK_REP": ev.get("jra_repeat_profile", {}).get("clock_repeat", 0) if ev.get("jra_repeat_profile", {}).get("clock_known") else "材料不足",
        "JRA_CURRENT": ev.get("jra_current", ev["current"])["label"],
        "JRA強近接本数": ev.get("jra_adj_competitive_count", 0),
        "JRA同距離好内容本数": ev.get("jra_direct_competitive_count", 0),
        "JRA同等以上1.0以内": ev.get("jra_same_class_close_count", 0),
        "JRA同等以上0.3以内": ev.get("jra_same_class_close03", 0),
        "JRA同距離能力床": ev.get("jra_direct_floor", {}).get("label", "材料不足"),
        "JRA能力床強度": ev.get("jra_direct_floor", {}).get("strength", 0),
        "JRA一発突出": "○" if ev.get("jra_direct_floor", {}).get("isolated_spike", False) else "",
        "JRA_seed_CONTENT": ev.get("jra_direct_floor", {}).get("seed_content_band", ev.get("jra_content_profile", {}).get("best_band", 0)),
        "共有レース物差し": ev.get("shared_reason", "共有同距離レースなし"),
    }


def build_prediction(race: RaceInfo, entries: List[Entry], histories: Dict[int, HorseHistory], race_date: date) -> Dict:
    if len(entries) < 3:
        raise ValueError("出馬表から3頭以上を読み取れませんでした。")
    clusters = build_clock_clusters(race, entries, histories)
    evals = {e.number: build_horse_eval(race, e, histories.get(e.number), race_date, clusters) for e in entries}
    direct = build_direct_matrix(race, evals, race_date)
    normal = rank_evals(race, evals, direct)
    pre_guard_top6 = list(normal[:min(6, len(normal))])
    top6, guards = apply_guards(race, entries, evals, normal, clusters, direct)
    guard_added = [n for n in top6 if n not in pre_guard_top6]
    guard_removed = [n for n in pre_guard_top6 if n not in top6]

    pair_checks = []
    top8_for_check = normal[:min(8, len(normal))]
    for idx in range(len(top8_for_check) - 1):
        a, b = top8_for_check[idx], top8_for_check[idx + 1]
        cmpv, reason = compare_evals_with_reason(evals[a], evals[b], race, direct)
        winner = a if cmpv >= 0 else b
        pair_checks.append({
            "比較": f"{idx+1}位vs{idx+2}位",
            "馬": f"{a} vs {b}",
            "優勢": winner,
            "主な決着理由": reason,
        })

    if len(entries) <= 6:
        status = "参考・ノーカウント"
        top6 = normal[:len(entries)]
    elif len(entries) == 7:
        status = "参考"
    else:
        status = "本集計"

    return {
        "ruleset_id": RULESET_ID,
        "implementation": IMPLEMENTATION_REV,
        "race": asdict(race),
        "race_date": race_date.isoformat(),
        "normal_order": normal,
        "pre_guard_top6": pre_guard_top6,
        "top6": top6,
        "guard_added": guard_added,
        "guard_removed": guard_removed,
        "status": status,
        "guards": guards,
        "pair_checks": pair_checks,
        "ranking_trace": (next(iter(evals.values())).get("ranking_trace", {}) if evals else {}),
        "five_axis_rows": [_five_axis_row(evals[n]) for n in normal],
        "normal_rows": [
            {
                "通常順位": i+1,
                "馬番": n,
                "馬名": evals[n]["name"],
                "同場同距離": _fmt_time_run(evals[n]["raw_exact"]),
                "時計クラスタ": evals[n]["peak_cluster"] if evals[n]["peak_cluster_reliable"] else "連続/不足",
                "総当たり勝": evals[n].get("pairwise_wins", 0),
                "総当たり敗": evals[n].get("pairwise_losses", 0),
                "評価理由": _eval_reason(evals[n]),
            }
            for i, n in enumerate(normal[:min(8, len(normal))])
        ],
        "top6_rows": [
            {
                "時計TOP6": i+1,
                "馬番": n,
                "馬名": evals[n]["name"],
                "ガード": "・".join([
                    x for x, arr in (("絶対", guards["absolute"]), ("転入", guards["transfer"]), ("境界", guards["boundary"])) if n in arr
                ]) or "通常選出",
                "評価理由": _eval_reason(evals[n]),
            }
            for i, n in enumerate(top6)
        ],
        "cluster_rows": [
            {
                "馬番": x["number"], "馬名": x["name"], "同場同距離ベスト": format_time(x["time"]),
                "着差": "—" if x["margin"] is None else f"{x['margin']:.1f}",
                "生時計順位": x.get("raw_rank"), "時計クラスタ": x.get("cluster") if clusters.get("reliable") else "自然断層なし",
            }
            for x in clusters.get("rows", [])
        ],
        "cluster_reliable": clusters.get("reliable", False),
        "ranking_cycle_detected": any(ev.get("ranking_cycle_detected", False) for ev in evals.values()),
    }


def parse_result_numbers(text: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d+", text)]


def verify_prediction(pred: Dict, text: str) -> Dict:
    res = parse_result_numbers(text)
    if len(res) < 3:
        raise ValueError("結果は『7-5-10』のように1〜3着まで入力してください。")
    podium = res[:3]
    s = set(pred["top6"])
    hits = sum(n in s for n in podium)
    return {
        "ルール": pred["ruleset_id"],
        "実装": pred["implementation"],
        "日付": pred["race_date"],
        "レース": pred["race"].get("race_name", ""),
        "競馬場": pred["race"].get("track", ""),
        "条件": f"{pred['race'].get('surface','')}{pred['race'].get('distance',0)}m",
        "頭数": len(pred["normal_order"]),
        "結果": "-".join(map(str, podium)),
        "通常TOP8": "・".join(map(str, pred["normal_order"][:8])),
        "時計TOP6": "・".join(map(str, pred["top6"])),
        "TOP6集計区分": pred["status"],
        "TOP6馬券内": f"{hits}/3",
        "TOP6完全捕捉": "○" if hits == 3 else "×",
    }


# ============================================================
# Streamlit UI
# ============================================================

APP_NAME = "競馬AI 時計分析 v2.0-Beta 完全Python版 impl8"
st.set_page_config(page_title=APP_NAME, page_icon="⏱️", layout="wide")
st.title("⏱️ 競馬AI 時計分析 v2.0-Beta impl7")
st.caption("完全Python自動判定｜impl7 direct-floor｜ChatGPT不要｜OpenAI API不要｜外部AI不要")
st.info(
    f"🔒 {RULESET_NAME}\n\n"
    "馬柱解析から5軸評価・競合判断・通常TOP8・ガード・最終TOP6まで、このPythonだけで完結します。"
)

if "prediction_py20" not in st.session_state:
    st.session_state.prediction_py20 = None
if "history_py20" not in st.session_state:
    st.session_state.history_py20 = []


def clear_all():
    st.session_state.prediction_py20 = None
    st.session_state.race_text_py20 = ""
    st.session_state.entry_text_py20 = ""
    st.session_state.history_text_py20 = ""
    st.session_state.result_text_py20 = ""


tab1, tab2, tab3, tab4 = st.tabs(["予想・検証", "検証履歴", "完全ルールブック", "回帰テスト正解"])

with tab1:
    st.subheader("① 入力")
    race_date_input = st.date_input("レース日", value=date.today(), key="race_date_py20")
    c1, c2, c3 = st.columns(3)
    with c1:
        race_text = st.text_area("レース情報", height=230, key="race_text_py20")
    with c2:
        entry_text = st.text_area("出馬表", height=230, key="entry_text_py20")
    with c3:
        history_text = st.text_area("馬柱", height=230, key="history_text_py20")

    b1, b2 = st.columns(2)
    with b1:
        run = st.button("時計TOP6を完全Python分析", type="primary", use_container_width=True)
    with b2:
        st.button("入力・予想をクリア", use_container_width=True, on_click=clear_all)

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
            st.caption(f"解析：出馬表 {len(entries)}頭 / 馬柱 {len(histories)}頭")
            if problems:
                st.error("\n".join(problems))
            else:
                pred = build_prediction(race, entries, histories, race_date_input)
                st.session_state.prediction_py20 = pred
                st.success("完全Pythonで事前固定しました。結果入力時に順位は再計算しません。")
        except Exception as e:
            st.exception(e)

    pred = st.session_state.prediction_py20
    if pred:
        st.divider()
        st.subheader("② 最終 時計TOP6")
        st.success("時計TOP6：" + "・".join(map(str, pred["top6"])) + f"　｜ {pred['status']}")
        st.dataframe(pd.DataFrame(pred["top6_rows"]), use_container_width=True, hide_index=True)

        st.markdown("### ガード適用前 → 適用後")
        st.write("**ガード前TOP6：** " + "・".join(map(str, pred.get("pre_guard_top6", []))))
        added = pred.get("guard_added", [])
        removed = pred.get("guard_removed", [])
        if added or removed:
            st.warning(
                "ガード変動｜IN：" + ("・".join(map(str, added)) if added else "なし")
                + " ／ OUT：" + ("・".join(map(str, removed)) if removed else "なし")
            )
        else:
            st.caption("ガードによる入替なし")

        st.markdown("### 通常時計順位 TOP8")
        st.caption("人気・オッズ・ガードを使わず作成。impl8はJRA1600〜1800mでseed上位8頭だけを先に固定せず、全頭にTOP8境界への挑戦権を与えてから隣接再監査。seedは初期順にのみ使用し、強い近接距離馬などが9位以下で永久除外される問題を修正。REPEATは悪走込み直近5走、CURRENTは直近3走。")
        st.dataframe(pd.DataFrame(pred["normal_rows"]), use_container_width=True, hide_index=True)

        st.markdown("### 5軸評価")
        st.dataframe(pd.DataFrame(pred["five_axis_rows"]), use_container_width=True, hide_index=True)

        st.markdown("### 時計クラスタ")
        if pred["cluster_rows"]:
            st.caption("自然断層あり" if pred["cluster_reliable"] else "自然な断層なし／材料不足：形式TOP3では切りません。")
            st.dataframe(pd.DataFrame(pred["cluster_rows"]), use_container_width=True, hide_index=True)
        else:
            st.info("同場同距離の時計材料がありません。")

        st.markdown("### TOP8 隣接ペア比較・決着理由")
        if pred["pair_checks"]:
            st.dataframe(pd.DataFrame(pred["pair_checks"]), use_container_width=True, hide_index=True)

        with st.expander("順位形成ログ（seed＋全頭境界監査＋隣接監査）", expanded=False):
            trace = pred.get("ranking_trace", {})
            st.write("**seed方式：** " + trace.get("seed_mode", "不明"))
            st.write("**初期TOP8 seed：** " + "・".join(map(str, trace.get("evidence_seed", []))))
            if trace.get("evidence_seed_all"):
                st.write("**全頭seed順：** " + "・".join(map(str, trace.get("evidence_seed_all", []))))
            admission = trace.get("admission_events", [])
            if admission:
                st.caption("TOP8外からの境界侵入ログ")
                st.dataframe(pd.DataFrame(admission), use_container_width=True, hide_index=True)
            shared_info = trace.get("shared_benchmarks", {})
            if shared_info:
                st.caption("共有同距離レースの共通物差し")
                st.dataframe(pd.DataFrame([{"馬番": n, "共有物差し": reason} for n, reason in shared_info.items()]), use_container_width=True, hide_index=True)
            audit = trace.get("audit_events", [])
            if audit:
                st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)
            else:
                st.caption("隣接入替なし")
            pair_events = trace.get("pairwise_events", [])
            if pair_events:
                st.caption("全ペアの決着理由（診断用）")
                st.dataframe(pd.DataFrame(pair_events), use_container_width=True, hide_index=True)

        g = pred["guards"]
        st.markdown("### ガード・警戒")
        st.write("**絶対時計ガード**：" + ("・".join(map(str, g["absolute"])) if g["absolute"] else "該当なし"))
        st.write("**地方転入人気馬ガード**：" + ("・".join(map(str, g["transfer"])) if g["transfer"] else "該当なし"))
        st.write("**境界ガード**：" + ("・".join(map(str, g["boundary"])) if g["boundary"] else "該当なし"))
        st.write("**初出走警戒**：" + ("・".join(map(str, g["debut_warning"])) if g["debut_warning"] else "該当なし"))
        st.write("**初距離警戒**：" + ("・".join(map(str, g["first_distance_warning"])) if g["first_distance_warning"] else "該当なし"))
        st.write("**高速時計＋大差負け警戒**：" + ("・".join(map(str, g["fast_big_margin_warning"])) if g["fast_big_margin_warning"] else "該当なし"))
        if g["guard_conflict"]:
            st.warning("複数ガード競合あり：固定優先順位は作らず、5軸比較で処理しました。v2.1検討対象です。")

        st.divider()
        st.subheader("③ 結果検証")
        result_text = st.text_input("実着順", placeholder="例：7-5-10", key="result_text_py20")
        if st.button("結果を照合して履歴に保存", use_container_width=True):
            try:
                rec = verify_prediction(pred, result_text)
                st.session_state.history_py20.append(rec)
                st.success(f"結果 {rec['結果']}｜TOP6馬券内 {rec['TOP6馬券内']}｜完全捕捉 {rec['TOP6完全捕捉']}")
            except Exception as e:
                st.error(str(e))

with tab2:
    st.subheader("検証履歴")
    if st.session_state.history_py20:
        hdf = pd.DataFrame(st.session_state.history_py20)
        st.dataframe(hdf, use_container_width=True, hide_index=True)
        counted = hdf[hdf["TOP6集計区分"] == "本集計"]
        races = len(counted)
        hits = sum(int(str(x).split("/")[0]) for x in counted["TOP6馬券内"]) if races else 0
        full = int((counted["TOP6完全捕捉"] == "○").sum()) if races else 0
        c1, c2 = st.columns(2)
        c1.metric("TOP6 馬券内捕捉", f"{hits}/{races*3}" if races else "0/0")
        c2.metric("TOP6 完全捕捉", f"{full}/{races}" if races else "0/0")
        csv = hdf.to_csv(index=False).encode("utf-8-sig")
        st.download_button("検証履歴CSV", data=csv, file_name="keiba_clock_v2_0_beta_python_history.csv", mime="text/csv", use_container_width=True)
        if st.button("履歴を全削除"):
            st.session_state.history_py20 = []
            st.rerun()
    else:
        st.info("まだ検証履歴はありません。")

with tab3:
    st.subheader(RULESET_NAME)
    st.code(RULESET_ID)
    st.markdown(RULEBOOK_TEXT)

with tab4:
    st.subheader("既知レースの固定TOP6")
    st.caption("回帰テスト用。計算には使用しません。")
    expected = {
        "R34 新潟 柳都S ダ1800稍": [6, 14, 2, 8, 4, 11],
        "R35 浦和 盆の月特別 ダ2000不": [3, 2, 10, 6, 7, 8],
        "R37 大井 武蔵野OP ダ1200不": [3, 5, 6, 9, 10, 11],
        "R38 門別 リンドウ特別 ダ1200良": [10, 7, 5, 6, 8, 9],
        "R39 大井 トゥインクルバースデー賞 ダ1600不": [2, 6, 10, 14, 11, 1],
    }
    st.dataframe(pd.DataFrame([{"レース": k, "固定TOP6": "・".join(map(str, v))} for k, v in expected.items()]), use_container_width=True, hide_index=True)
    pred = st.session_state.prediction_py20
    if pred:
        target = st.selectbox("現在の予想を照合", list(expected.keys()))
        actual = pred["top6"]
        exp = expected[target]
        st.write("**現在：** " + "・".join(map(str, actual)))
        st.write("**固定正解：** " + "・".join(map(str, exp)))
        if actual == exp:
            st.success("完全一致（6頭＋順番）")
        elif set(actual) == set(exp):
            st.warning("6頭の集合は一致。順番のみ不一致。")
        else:
            missing = [n for n in exp if n not in actual]
            extra = [n for n in actual if n not in exp]
            st.error("不一致｜不足：" + ("・".join(map(str, missing)) if missing else "なし") + "｜余分：" + ("・".join(map(str, extra)) if extra else "なし"))
