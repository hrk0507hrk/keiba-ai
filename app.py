import streamlit as st
import re
from dataclasses import dataclass, field
from itertools import permutations

st.set_page_config(page_title="競馬AI2.0", layout="wide")
st.title("競馬AI2.0｜馬柱重視版")
st.caption("出走表＋馬柱から、1〜3番人気の軸・相手ランキング・馬連/ワイド/3連単を作成します。")

if "clear_count" not in st.session_state:
    st.session_state.clear_count = 0

if st.button("🗑️ 入力内容をクリア"):
    st.session_state.clear_count += 1

col1, col2 = st.columns(2)

with col1:
    racecard_text = st.text_area(
        "① 出走表を貼ってください（PC/スマホ想定）",
        height=430,
        key=f"racecard_{st.session_state.clear_count}",
    )

with col2:
    past_text = st.text_area(
        "② 馬柱を貼ってください（できれば9走分）",
        height=430,
        key=f"past_{st.session_state.clear_count}",
    )

col3, col4 = st.columns(2)

with col3:
    good_frame_text = st.text_input(
        "③ 有利枠（例：1,3,8）",
        key=f"frames_{st.session_state.clear_count}",
    )

with col4:
    good_track_text = st.text_input(
        "④ 今回の馬場状態が得意な馬番（例：2,7,11）",
        key=f"track_horses_{st.session_state.clear_count}",
    )

track_condition = st.selectbox(
    "馬場状態",
    ["良", "稍重", "重", "不良"],
    index=0,
    key=f"condition_{st.session_state.clear_count}",
)

st.divider()


@dataclass
class RaceRecord:
    date: str = ""
    place: str = ""
    surface: str = ""
    distance: int = 0
    condition: str = ""
    finish: int = 99
    popularity: int = 99
    margin: float = 99.0
    passing: str = ""
    jockey: str = ""
    weight: float = 0.0
    bodyweight: int = 0
    field_size: int = 0
    race_time: str = ""
    race_time_sec: float = 0.0
    last3f: float = 0.0
    raw: str = ""


@dataclass
class Horse:
    frame: int = 0
    number: int = 0
    name: str = ""
    popularity: int = 99
    odds: float | None = None
    jockey: str = ""
    weight: float = 0.0
    bodyweight: int = 0
    races: list[RaceRecord] = field(default_factory=list)

    recent_score: int = 0
    distance_score: int = 0
    track_score: int = 0
    course_score: int = 0
    pace_score: int = 0
    value_score: int = 0
    manual_score: int = 0
    time_score: int = 0
    closing_score: int = 0
    best_time_sec: float = 0.0
    best_last3f: float = 0.0
    total: int = 0
    style: str = ""
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)


IGNORE_WORDS = [
    "馬メモ", "レース別馬メモ", "全角100文字以内で入力してください",
    "削除保存", "閉じる", "編集", "次走買い", "次走消し",
    "不利", "馬場向かず", "ペース合わず", "ハイレベル戦", "好ラップ",
    "映像を見る",
]


def clean_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(w in line for w in IGNORE_WORDS):
            continue
        if re.fullmatch(r"\d+/100|\d+/500", line):
            continue
        lines.append(line)
    return lines


def extract_odds_popularity(text: str):
    odds = None
    popularity = 99

    # 1) 一番よくある形式：11.9 (4人気)
    m = re.search(r"(\d+\.\d+)\s*\((\d+)\s*人気\)", text)
    if m:
        return float(m.group(1)), int(m.group(2))

    # 2) 「4人気」だけ拾う
    m = re.search(r"(\d+)\s*人気", text)
    if m:
        popularity = int(m.group(1))

    # 3) オッズ候補を拾う
    # 斤量 56.0 や馬体重 472kg を拾わないように、45.0〜65.0は基本除外
    decimals = []
    for x in re.findall(r"\b(\d+\.\d+)\b", text):
        try:
            v = float(x)
            if 1.0 <= v <= 999.9 and not (45.0 <= v <= 65.0):
                decimals.append(v)
        except:
            pass

    if decimals:
        odds = decimals[0]

    return odds, popularity


def infer_popularity_from_rows(rows: list[str], start: int, end: int, odds):
    """PC版でオッズと人気が別行・人気だけ数字行の場合に拾う"""
    pop = 99

    # まず「〇人気」を探す
    for row in rows[start:end]:
        m = re.search(r"(\d+)\s*人気", row)
        if m:
            return int(m.group(1))

    # オッズ行の直後に「人気数字だけ」が来る地方PC版に対応
    # 例：
    # 490(-3)    37.8
    # 9
    if odds is not None:
        odds_str = str(odds)
        for idx in range(start, end):
            row = rows[idx]
            if odds_str in row:
                for j in range(idx + 1, min(idx + 6, end)):
                    candidate = rows[j].strip()
                    if re.fullmatch(r"\d+", candidate):
                        v = int(candidate)
                        if 1 <= v <= 30:
                            return v

    # オッズと人気が同じブロック内で「小数行→整数行」になっている場合
    for idx in range(start, min(end - 1, len(rows) - 1)):
        row = rows[idx].strip()
        nxt = rows[idx + 1].strip()

        # 37.8 のようなオッズ行
        if re.fullmatch(r"\d+\.\d+", row) and re.fullmatch(r"\d+", nxt):
            v = int(nxt)
            if 1 <= v <= 30:
                return v

        # 490(-3) 37.8 のような馬体重＋オッズ行
        if re.search(r"\d{3}\([+-]?\d+\)\s+\d+\.\d+", row) and re.fullmatch(r"\d+", nxt):
            v = int(nxt)
            if 1 <= v <= 30:
                return v

    # 最後の保険：馬体重形式の次以降に出る単独数字を人気候補にする
    body_seen = False
    for row in rows[start:end]:
        if re.search(r"\d{3}\([+-]?\d+\)", row) or re.search(r"\d{3}kg", row):
            body_seen = True
            continue
        if body_seen and re.fullmatch(r"\d+", row):
            v = int(row)
            if 1 <= v <= 30:
                return v

    return pop


def parse_racecard_pc(lines: list[str]) -> list[Horse]:
    horses = []
    i = 0

    while i < len(lines):
        m = re.match(r"^(\d+)\s+(\d+)$", lines[i])
        if not m:
            i += 1
            continue

        frame = int(m.group(1))
        number = int(m.group(2))

        # 馬名行を探す
        j = i + 1
        while j < len(lines) and lines[j] == "--":
            j += 1

        if j >= len(lines):
            i += 1
            continue

        name = lines[j].strip()

        if (
            not name
            or name == "--"
            or name == "編集"
            or re.fullmatch(r"\d+", name)
            or "人気" in name
        ):
            i += 1
            continue

        # 次の馬番行までを1頭分ブロックとして取得
        k = j + 1
        block = []
        while k < len(lines):
            if re.match(r"^\d+\s+\d+$", lines[k]):
                break
            block.append(lines[k])
            k += 1

        block_text = " ".join(block)

        odds = None
        pop = 99
        jockey = ""
        weight = 0.0
        bodyweight = 0

        # 地方PC版：
        # 牝4 54.0 町田直希 川崎 高月賢一 490(-3) 37.8
        # 9
        # 編集
        info_line = block[0] if block else ""
        info_parts = info_line.split()

        # 斤量
        for p in info_parts:
            try:
                v = float(p)
                if 45.0 <= v <= 65.0:
                    weight = v
                    break
            except:
                pass

        # 騎手：斤量の次に来ることが多い
        for idx, p in enumerate(info_parts):
            try:
                v = float(p)
                if 45.0 <= v <= 65.0 and idx + 1 < len(info_parts):
                    jockey = info_parts[idx + 1]
                    break
            except:
                pass

        # 馬体重
        bw = re.search(r"\b(\d{3})\([+-]?\d+\)", info_line)
        if bw:
            bodyweight = int(bw.group(1))
        else:
            bw = re.search(r"\b(\d{3})kg", info_line)
            if bw:
                bodyweight = int(bw.group(1))

        # オッズ：馬体重の後の小数を優先
        odds_candidates = []
        for x in re.findall(r"\b(\d+\.\d+)\b", block_text):
            try:
                v = float(x)
                # 斤量を除外
                if not (45.0 <= v <= 65.0):
                    odds_candidates.append(v)
            except:
                pass
        if odds_candidates:
            odds = odds_candidates[-1]  # 地方PC版は最後の小数がオッズになりやすい

        # 人気：オッズ行/情報行の直後にある単独数字を取得
        # 例：37.8 の次行 9
        for idx, row in enumerate(block):
            row = row.strip()

            # 〇人気表記がある場合
            mp = re.search(r"(\d+)\s*人気", row)
            if mp:
                pop = int(mp.group(1))
                break

            # 情報行にオッズがあり、その次の単独数字が人気
            if odds is not None and str(odds) in row:
                for nxt in block[idx + 1:idx + 5]:
                    nxt = nxt.strip()
                    if re.fullmatch(r"\d+", nxt):
                        v = int(nxt)
                        if 1 <= v <= 30:
                            pop = v
                            break
                if pop != 99:
                    break

        # さらに保険：ブロック内の「編集」の直前の単独数字を人気扱い
        if pop == 99:
            for idx, row in enumerate(block):
                if row == "編集" and idx > 0 and re.fullmatch(r"\d+", block[idx - 1].strip()):
                    v = int(block[idx - 1].strip())
                    if 1 <= v <= 30:
                        pop = v
                        break

        # 中央PCなど、別形式への保険
        if pop == 99 or odds is None:
            o2, p2 = extract_odds_popularity(block_text)
            if odds is None:
                odds = o2
            if pop == 99:
                pop = p2

        horses.append(
            Horse(
                frame=frame,
                number=number,
                name=name,
                popularity=pop,
                odds=odds,
                jockey=jockey,
                weight=weight,
                bodyweight=bodyweight,
            )
        )

        i = k

    return horses

def parse_racecard_smartphone(lines: list[str]) -> list[Horse]:
    horses = []
    i = 0

    while i < len(lines):
        if not re.fullmatch(r"\d+", lines[i]):
            i += 1
            continue

        number = int(lines[i])
        found = False
        name = ""

        for j in range(i + 1, min(i + 12, len(lines))):
            if "のデータベース" in lines[j]:
                name = lines[j - 1].strip()
                found = True
                break

        if not found or not name or re.fullmatch(r"\d+", name):
            i += 1
            continue

        block = " ".join(lines[i:min(i + 45, len(lines))])
        odds, pop = extract_odds_popularity(block)

        jockey = ""
        weight = 0.0
        bodyweight = 0

        wm = re.search(r"\b(\d{2}(?:\.\d)?)\b", block)
        if wm:
            try:
                w = float(wm.group(1))
                if 45 <= w <= 65:
                    weight = w
            except:
                pass

        bw = re.search(r"(\d{3})kg", block)
        if bw:
            bodyweight = int(bw.group(1))

        # データベース行から騎手を拾う
        for j in range(i + 1, min(i + 15, len(lines))):
            if "のデータベース" in lines[j]:
                tail = lines[j].replace(f"{name}のデータベース", "").strip()
                tail = re.sub(r"^[牡牝セ]\d+\s*", "", tail)
                tail = re.sub(r"\d{2}(?:\.\d)?", "", tail).strip()
                if tail:
                    jockey = tail.split()[0]
                break

        frame = (number + 1) // 2
        horses.append(Horse(frame, number, name, pop, odds, jockey, weight, bodyweight))
        i += 1

    return horses


def parse_racecard(text: str) -> list[Horse]:
    lines = clean_lines(text)

    candidates = []
    if any("のデータベース" in line for line in lines):
        candidates.append(parse_racecard_smartphone(lines))
    candidates.append(parse_racecard_pc(lines))

    best = []
    best_score = -1
    for c in candidates:
        unique = {}
        for h in c:
            if h.number and h.name:
                unique[h.number] = h
        c = list(unique.values())
        score = len(c) * 10 + sum(1 for h in c if h.popularity != 99)
        if score > best_score:
            best = c
            best_score = score

    return sorted(best, key=lambda h: h.number)


def split_past_blocks(text: str, horses: list[Horse]) -> dict[int, list[str]]:
    lines = clean_lines(text)
    blocks = {h.number: [] for h in horses}
    current_no = None
    horse_names = {h.name: h.number for h in horses}

    for idx, line in enumerate(lines):
        # スマホ：馬番→馬名→データベース
        if re.fullmatch(r"\d+", line):
            n = int(line)
            look = lines[idx + 1:idx + 8]
            if any("のデータベース" in x for x in look) and n in blocks:
                current_no = n
                continue

        # PC：枠 馬番
        m = re.match(r"^\d+\s+(\d+)$", line)
        if m:
            n = int(m.group(1))
            if n in blocks:
                current_no = n
                continue

        # 馬名そのもの
        if line in horse_names:
            current_no = horse_names[line]
            continue

        if current_no is not None:
            blocks[current_no].append(line)

    return blocks


def parse_margin_from_lines(lines: list[str]) -> float:
    for row in reversed(lines):
        row = row.strip()
        if "kg" in row or "頭" in row:
            continue
        if re.match(r"^(?:-?\s*\d|\d+-\d+)", row):
            continue
        m = re.search(r"\(([-+]?\d+\.\d+)\)\s*$", row)
        if m:
            try:
                return abs(float(m.group(1)))
            except ValueError:
                pass
    return 99.0

def parse_passing_from_lines(lines: list[str]) -> str:
    for row in lines:
        m = re.search(r"-\s*(\d+)\s+(\d+)\s+(\d+)", row)
        if m:
            return "-".join(m.groups())

        m = re.search(r"(\d+(?:-\d+)+)\s+\(", row)
        if m:
            return m.group(1)

        # 地方の 7 5 5 5
        if re.fullmatch(r"\d+\s+\d+\s+\d+\s+\d+", row):
            return "-".join(re.findall(r"\d+", row))

    return ""


def parse_finish_from_local_race(lines: list[str]) -> int:
    for row in lines[1:8]:
        if re.fullmatch(r"\d+", row):
            v = int(row)
            if 1 <= v <= 30:
                return v
    return 99


def race_time_to_seconds(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        if ":" in value:
            minute, second = value.split(":", 1)
            return int(minute) * 60 + float(second)
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_race_time_from_lines(lines: list[str]) -> tuple[str, float]:
    for row in lines:
        m = re.search(r"(?:芝|ダ)\d+\s+(\d+:\d{2}\.\d|\d{2}\.\d)", row)
        if m:
            value = m.group(1)
            return value, race_time_to_seconds(value)
    return "", 0.0


def parse_last3f_from_lines(lines: list[str]) -> float:
    for row in lines:
        row = row.strip()
        if not (
            re.search(r"\d+(?:-\d+)+\s+\(\d{2}\.\d\)", row)
            or re.search(r"-\s*\d+\s+\d+\s+\d+\s+\(\d{2}\.\d\)", row)
        ):
            continue
        m = re.search(r"\((\d{2}\.\d)\)", row)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return 0.0


def parse_current_race_conditions(text: str) -> tuple[str, int]:
    m = re.search(r"(芝|ダ)\s*(\d{3,4})", text or "")
    if not m:
        return "", 0
    return m.group(1), int(m.group(2))

def parse_past_performances(text: str, horses: list[Horse]) -> list[Horse]:
    blocks = split_past_blocks(text, horses)
    horse_map = {h.number: h for h in horses}

    for no, block in blocks.items():
        races = []

        for i, line in enumerate(block):
            # 中央PC例: 2026.06.07 東京5
            jra = re.match(r"^(\d{4}\.\d{2}\.\d{2})\s+(.+?)(\d+|中)$", line)
            # 地方スマホ例: 06/02  船橋 1R
            local = re.match(r"^(\d{2}/\d{2})\s+(.+?)\s+\d+R", line)

            if not jra and not local:
                continue

            race_lines = block[i:i + 22]
            race_text = " ".join(race_lines)
            r = RaceRecord(raw=race_text)

            if jra:
                r.date = jra.group(1)
                r.place = re.sub(r"\d+$", "", jra.group(2)).strip()
                fin_raw = jra.group(3)
                if fin_raw.isdigit():
                    r.finish = int(fin_raw)
            else:
                r.date = local.group(1)
                r.place = local.group(2).strip()
                r.finish = parse_finish_from_local_race(race_lines)

            dm = re.search(r"(芝|ダ)(\d+)", race_text)
            if dm:
                r.surface = dm.group(1)
                r.distance = int(dm.group(2))

            if "不良" in race_text:
                r.condition = "不良"
            elif "稍" in race_text or "稍重" in race_text:
                r.condition = "稍重"
            elif "重" in race_text:
                r.condition = "重"
            elif "良" in race_text:
                r.condition = "良"

            pm = re.search(r"(\d+)人気", race_text)
            if pm:
                r.popularity = int(pm.group(1))

            fs = re.search(r"(\d+)頭", race_text)
            if fs:
                r.field_size = int(fs.group(1))

            wm = re.search(r"\b(\d{2}(?:\.\d)?)\b", race_text)
            if wm:
                try:
                    w = float(wm.group(1))
                    if 45 <= w <= 65:
                        r.weight = w
                except:
                    pass

            bw = re.search(r"(\d{3})kg", race_text)
            if bw:
                r.bodyweight = int(bw.group(1))

            r.margin = parse_margin_from_lines(race_lines)
            r.passing = parse_passing_from_lines(race_lines)
            r.race_time, r.race_time_sec = parse_race_time_from_lines(race_lines)
            r.last3f = parse_last3f_from_lines(race_lines)

            # 騎手
            for row in race_lines:
                if re.match(r"^[ァ-ヴ一-龥]{2,6}$", row):
                    r.jockey = row
                    break

            races.append(r)

        horse = horse_map.get(no)
        if horse:
            horse.races = races[:9]

    return horses


def parse_manual_numbers(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text or "")]


def running_style_from_races(horse: Horse) -> str:
    front = 0
    stalk = 0
    close = 0
    rear = 0

    for r in horse.races[:5]:
        nums = re.findall(r"\d+", r.passing or "")
        if not nums:
            continue
        pos = int(nums[0])
        if pos <= 2:
            front += 1
        elif pos <= 5:
            stalk += 1
        elif pos <= 9:
            close += 1
        else:
            rear += 1

    mx = max(front, stalk, close, rear)
    if mx == 0:
        return "不明"
    if mx == front:
        return "逃げ"
    if mx == stalk:
        return "先行"
    if mx == close:
        return "差し"
    return "追込"



def choose_target_distance(horses: list[Horse], current_surface: str, current_distance: int) -> tuple[str, int]:
    if current_surface and current_distance:
        return current_surface, current_distance
    counts = {}
    for horse in horses:
        for race in horse.races[:3]:
            if race.surface and race.distance:
                key = (race.surface, race.distance)
                counts[key] = counts.get(key, 0) + 1
    if not counts:
        return "", 0
    return max(counts, key=counts.get)


def calculate_clock_profiles(horses: list[Horse], current_surface: str, current_distance: int):
    surface, distance = choose_target_distance(horses, current_surface, current_distance)
    time_profiles = []
    closing_profiles = []

    for horse in horses:
        relevant = [
            r for r in horse.races[:9]
            if r.race_time_sec > 0
            and (not surface or r.surface == surface)
            and (not distance or abs(r.distance - distance) <= 100)
        ]
        horse.best_time_sec = min((r.race_time_sec for r in relevant), default=0.0)
        horse.best_last3f = min((r.last3f for r in relevant if r.last3f > 0), default=0.0)

        if horse.best_time_sec > 0:
            time_profiles.append((horse.number, horse.best_time_sec))
        if horse.best_last3f > 0:
            closing_profiles.append((horse.number, horse.best_last3f))

    time_profiles.sort(key=lambda x: x[1])
    closing_profiles.sort(key=lambda x: x[1])

    def rank_points(rank: int, total: int, points: tuple[int, int, int, int]) -> int:
        if total <= 0:
            return 0
        ratio = rank / total
        if rank == 1:
            return points[0]
        if ratio <= 0.25:
            return points[1]
        if ratio <= 0.50:
            return points[2]
        if ratio <= 0.75:
            return points[3]
        return 0

    time_rank = {no: (i + 1, value) for i, (no, value) in enumerate(time_profiles)}
    closing_rank = {no: (i + 1, value) for i, (no, value) in enumerate(closing_profiles)}

    for horse in horses:
        horse.time_score = 0
        horse.closing_score = 0

        if horse.number in time_rank:
            rank, value = time_rank[horse.number]
            horse.time_score = rank_points(rank, len(time_profiles), (20, 16, 12, 6))
            if horse.time_score > 0:
                horse.reasons.append(f"持ち時計評価({value:.1f}秒) +{horse.time_score}")

        if horse.number in closing_rank:
            rank, value = closing_rank[horse.number]
            horse.closing_score = rank_points(rank, len(closing_profiles), (16, 12, 8, 4))
            if horse.closing_score > 0:
                horse.reasons.append(f"上がり時計評価({value:.1f}) +{horse.closing_score}")

        recent_last3f = [r.last3f for r in horse.races[:3] if r.last3f > 0]
        if len(recent_last3f) >= 3 and recent_last3f[0] < recent_last3f[1] < recent_last3f[2]:
            horse.closing_score += 3
            horse.reasons.append("上がり時計良化 +3")

        horse.score += horse.time_score + horse.closing_score

        # 持ち時計0点かつ上がり評価4点以下は、時計材料不足として軽く減点
        if horse.time_score == 0 and horse.closing_score <= 4:
            horse.score -= 3
            horse.reasons.append("時計評価不足 -3")

    return surface, distance

def evaluate_upper_class_record(horse: Horse):
    """
    馬柱9走のraw文字列から上級クラス・重賞実績を評価。
    同じレースで複数条件が重複しないよう、各走で最上位の評価だけを採用する。
    """
    score = 0
    reasons = []
    graded_good = 0
    open_good = 0
    upper_local_good = 0
    central_upper_good = 0

    for r in horse.races[:9]:
        text = (r.raw or "").upper()
        finish = r.finish

        race_score = 0
        race_reason = ""

        # G1 / Jpn1
        if any(k in text for k in ["G1", "GⅠ", "JPN1", "JPNⅠ"]):
            if finish <= 3:
                race_score = 20
                race_reason = "G1・Jpn1好走"
                graded_good += 1
            elif finish <= 5:
                race_score = 12
                race_reason = "G1・Jpn1掲示板"
            else:
                race_score = 6
                race_reason = "G1・Jpn1出走歴"

        # G2 / Jpn2
        elif any(k in text for k in ["G2", "GⅡ", "JPN2", "JPNⅡ"]):
            if finish <= 3:
                race_score = 16
                race_reason = "G2・Jpn2好走"
                graded_good += 1
            elif finish <= 5:
                race_score = 10
                race_reason = "G2・Jpn2掲示板"
            else:
                race_score = 5
                race_reason = "G2・Jpn2出走歴"

        # G3 / Jpn3
        elif any(k in text for k in ["G3", "GⅢ", "JPN3", "JPNⅢ"]):
            if finish <= 3:
                race_score = 14
                race_reason = "G3・Jpn3好走"
                graded_good += 1
            elif finish <= 5:
                race_score = 8
                race_reason = "G3・Jpn3掲示板"
            else:
                race_score = 4
                race_reason = "G3・Jpn3出走歴"

        # オープン・リステッド
        elif any(k in text for k in ["オープン", "OPEN", "リステッド", "LISTED", " OP ", " L "]):
            if finish <= 3:
                race_score = 10
                race_reason = "オープン・L好走"
                open_good += 1
            elif finish <= 5:
                race_score = 6
                race_reason = "オープン・L掲示板"
            else:
                race_score = 3
                race_reason = "オープン・L出走歴"

        # 地方A級・S級
        elif any(k in text for k in ["A1", "A2", "Ｓ１", "Ｓ２", "S1", "S2"]):
            if finish <= 3:
                race_score = 12
                race_reason = "地方上級クラス好走"
                upper_local_good += 1
            elif finish <= 5:
                race_score = 7
                race_reason = "地方上級クラス掲示板"
            else:
                race_score = 3
                race_reason = "地方上級クラス出走歴"

        # 中央3勝・2勝・1勝クラス
        elif any(k in text for k in ["3勝クラス", "３勝クラス", "1600万"]):
            if finish <= 5:
                race_score = 10
                race_reason = "中央3勝クラス実績"
                central_upper_good += 1
            else:
                race_score = 4
                race_reason = "中央3勝クラス出走歴"

        elif any(k in text for k in ["2勝クラス", "２勝クラス", "1000万"]):
            if finish <= 5:
                race_score = 8
                race_reason = "中央2勝クラス実績"
                central_upper_good += 1
            else:
                race_score = 3
                race_reason = "中央2勝クラス出走歴"

        elif any(k in text for k in ["1勝クラス", "１勝クラス", "500万"]):
            if finish <= 5:
                race_score = 6
                race_reason = "中央1勝クラス実績"
                central_upper_good += 1
            else:
                race_score = 2
                race_reason = "中央1勝クラス出走歴"

        score += race_score
        if race_reason and race_reason not in reasons:
            reasons.append(race_reason)

    # 実績の厚みを追加評価
    if graded_good >= 2:
        score += 10
        reasons.append("重賞好走実績複数")
    elif graded_good == 1:
        score += 5
        reasons.append("重賞実績")

    if open_good >= 2:
        score += 5
        reasons.append("オープン実績複数")

    if upper_local_good >= 2:
        score += 6
        reasons.append("地方上級実績複数")

    if central_upper_good >= 2:
        score += 5
        reasons.append("中央上級条件実績複数")

    # 上級実績だけで暴走しすぎないよう上限
    return min(score, 45), reasons

def evaluate_horse(horse: Horse, good_frames: list[int], good_track_horses: list[int], condition: str):
    score = 0
    reasons = []
    cautions = []
    races = horse.races[:9]
    recent3 = races[:3]
    recent5 = races[:5]

    # 近走評価
    recent_score = 0
    for r in recent3:
        if r.finish == 1:
            recent_score += 12
        elif r.finish == 2:
            recent_score += 9
        elif r.finish == 3:
            recent_score += 7
        elif r.finish <= 5:
            recent_score += 4
        elif r.finish <= 8:
            recent_score += 2
    score += recent_score
    if recent_score >= 22:
        reasons.append("近3走内容◎")
    elif recent_score >= 12:
        reasons.append("近3走安定")

    # 9走安定
    in3 = sum(1 for r in races if r.finish <= 3)
    in5 = sum(1 for r in races if r.finish <= 5)
    if in3 >= 4:
        score += 10
        reasons.append("複勝圏実績多い")
    elif in3 >= 2:
        score += 5
    if in5 >= 6:
        score += 15
        reasons.append("掲示板安定◎")
    elif in5 >= 4:
        score += 8
        reasons.append("掲示板安定")

    # 着差
    margin_score = 0
    for r in recent5:
        if r.margin <= 0.2:
            margin_score += 5
        elif r.margin <= 0.5:
            margin_score += 3
        elif r.margin <= 1.0:
            margin_score += 1
    score += margin_score
    if margin_score >= 10:
        reasons.append("着差優秀")
    elif margin_score >= 5:
        reasons.append("大きく負けていない")

    # 脚質・位置取り
    style = running_style_from_races(horse)
    horse.style = style
    front_count = 0
    for r in recent5:
        nums = re.findall(r"\d+", r.passing or "")
        if nums and int(nums[0]) <= 3:
            front_count += 1
    if front_count >= 3:
        score += 10
        reasons.append("先行力◎")
    elif front_count >= 2:
        score += 6
        reasons.append("前目で運べる")

    # 枠・馬場適性
    frame_bonus = horse.frame in good_frames
    track_bonus = horse.number in good_track_horses

    if frame_bonus:
        score += 5
        reasons.append("有利枠")

    if track_bonus:
        score += 8
        reasons.append("手入力:馬場適性")

    if frame_bonus and track_bonus:
        score += 8
        reasons.append("有利枠×馬場適性")

    same_cond = [r for r in races if r.condition == condition]
    same_cond_good = sum(1 for r in same_cond if r.finish <= 3)

    if len(same_cond) >= 2 and same_cond_good >= 1:
        score += 5
        reasons.append(f"{condition}馬場実績")

    if condition in ["重", "不良"]:
        if style == "逃げ":
            score += 7
            reasons.append(f"{condition}馬場×逃げ")
        elif style == "先行":
            score += 5
            reasons.append(f"{condition}馬場×先行")

    # 上級クラス・重賞実績
    upper_score, upper_reasons = evaluate_upper_class_record(horse)
    score += upper_score
    reasons.extend(upper_reasons)

    # 人気妙味
    if 4 <= horse.popularity <= 6:
        score += 4
        reasons.append("相手妙味")
    elif 7 <= horse.popularity <= 9:
        score += 6
        reasons.append("穴妙味")

    # 人気以上好走歴
    upset = 0
    for r in races:
        if r.popularity >= 6 and r.finish <= 3:
            upset += 1
    if upset >= 2:
        score += 8
        reasons.append("人気以上の好走歴")
    elif upset == 1:
        score += 4

    # 注意
    if len(recent3) >= 2 and all(r.finish >= 10 for r in recent3[:2]):
        cautions.append("近2走二桁")
    if not races:
        cautions.append("馬柱読み取り不足")

    horse.score = score
    horse.reasons = reasons
    horse.cautions = cautions
    return horse


def run_scoring(horses: list[Horse], good_frames: list[int], good_track_horses: list[int], condition: str):
    for h in horses:
        evaluate_horse(h, good_frames, good_track_horses, condition)
    return horses


def select_marks(horses: list[Horse]):
    # 10番人気以下は基本消し
    usable = [h for h in horses if h.popularity <= 9]
    top3 = [h for h in usable if h.popularity <= 3]

    marks = {}
    if top3:
        axis = sorted(top3, key=lambda h: h.score, reverse=True)[0]
    elif usable:
        axis = sorted(usable, key=lambda h: h.score, reverse=True)[0]
    else:
        return marks, [], horses

    marks["◎"] = axis

    remain = [h for h in usable if h.number != axis.number]
    remain = sorted(remain, key=lambda h: h.score, reverse=True)

    for mark, horse in zip(["〇", "▲", "△", "☆", "注"], remain[:5]):
        marks[mark] = horse

    cut = [h for h in horses if h.popularity >= 10]
    return marks, remain, cut


def make_bets(marks: dict):
    bets = {"馬連": [], "ワイド": [], "3連単": []}

    if "◎" not in marks:
        return bets

    a = marks["◎"].number

    for m in ["〇", "▲", "△"]:
        if m in marks:
            bets["馬連"].append(f"{a}-{marks[m].number}")

    for m in ["▲", "△"]:
        if m in marks:
            bets["ワイド"].append(f"{a}-{marks[m].number}")
    if "▲" in marks and "△" in marks:
        bets["ワイド"].append(f"{marks['▲'].number}-{marks['△'].number}")

    if "〇" in marks and "▲" in marks:
        b = marks["〇"].number
        c = marks["▲"].number
        bets["3連単"].extend([f"{a}→{b}→{c}", f"{a}→{c}→{b}", f"{b}→{a}→{c}", f"{c}→{a}→{b}"])

    if "△" in marks and "〇" in marks and "▲" in marks:
        b = marks["〇"].number
        c = marks["▲"].number
        d = marks["△"].number
        bets["3連単"].extend([f"{a}→{b}→{d}", f"{a}→{c}→{d}", f"{a}→{d}→{b}", f"{a}→{d}→{c}"])

    return bets


def grade(score: int) -> str:
    if score >= 55:
        return "S"
    if score >= 42:
        return "A"
    if score >= 30:
        return "B"
    if score >= 18:
        return "C"
    return "D"


def comment(horse: Horse) -> str:
    if not horse.reasons:
        return "強調材料は少なめ。"
    return " / ".join(horse.reasons)


def race_type(horses: list[Horse]) -> str:
    ranked = sorted(horses, key=lambda h: h.score, reverse=True)
    if len(ranked) < 3:
        return "判定不可"
    diff = ranked[0].score - ranked[2].score
    if diff >= 20:
        return "本命寄り"
    if diff >= 10:
        return "やや荒れ"
    return "混戦・荒れ注意"


if st.button("AI予想開始"):
    horses = parse_racecard(racecard_text)

    if not horses:
        st.error("出走表を読み取れませんでした。コピー範囲を広めにして再度貼ってください。")
        st.stop()

    horses = parse_past_performances(past_text, horses)

    good_frames = parse_manual_numbers(good_frame_text)
    good_track_horses = parse_manual_numbers(good_track_text)

    horses = run_scoring(horses, good_frames, good_track_horses, track_condition)

    current_surface, current_distance = parse_current_race_conditions(racecard_text)
    clock_surface, clock_distance = calculate_clock_profiles(
        horses, current_surface, current_distance
    )

    marks, ranking, cut = select_marks(horses)
    bets = make_bets(marks)
    ability = sorted(horses, key=lambda h: h.score, reverse=True)
    holes = [h for h in ability if 4 <= h.popularity <= 9]

    st.success(f"{len(horses)}頭を読み取りました。")
    st.info(f"レース判定：{race_type(horses)}")
    if clock_surface and clock_distance:
        st.caption(f"時計比較条件：{clock_surface}{clock_distance}m前後（±100m）")

    with st.expander("読み取り確認（馬番・馬名・人気・オッズ）"):
        for h in horses:
            pop_text = "未取得" if h.popularity == 99 else f"{h.popularity}人気"
            odds_text = "-" if h.odds is None else str(h.odds)
            time_text = f"{h.best_time_sec:.1f}秒" if h.best_time_sec > 0 else "未取得"
            last3f_text = f"{h.best_last3f:.1f}" if h.best_last3f > 0 else "未取得"
            st.write(f"{h.number} {h.name}｜{pop_text}｜オッズ {odds_text}｜持ち時計 {time_text}｜上がり {last3f_text}")

    st.header("AI印")

    for m in ["◎", "〇", "▲", "△", "☆", "注"]:
        if m not in marks:
            continue
        h = marks[m]
        st.markdown(f"### {m} {h.number} {h.name}｜{h.popularity}番人気｜評価{grade(h.score)}｜{h.score}点")
        st.write(comment(h))
        if h.cautions:
            st.warning(" / ".join(h.cautions))

    st.divider()

    st.header("能力ランキング")
    for i, h in enumerate(ability, 1):
        st.write(f"{i}位　{h.number} {h.name}｜{h.popularity}番人気｜総合{h.score}点｜時計{h.time_score}点｜上がり{h.closing_score}点｜脚質:{h.style}")
        with st.expander(f"{h.number} {h.name} の評価理由"):
            st.write(comment(h))
            if h.cautions:
                st.warning(" / ".join(h.cautions))
            st.write(f"読み取った過去走：{len(h.races)}走")
            clock_rows = []
            for r in h.races:
                if r.race_time_sec <= 0 and r.last3f <= 0:
                    continue
                clock_rows.append(
                    f"{r.date} {r.place} {r.surface}{r.distance}m {r.condition}"
                    f"｜走破 {r.race_time or '-'}"
                    f"｜上がり {r.last3f if r.last3f > 0 else '-'}"
                )
            if clock_rows:
                st.caption("時計読み取り")
                for row in clock_rows:
                    st.write(row)

    st.divider()

    st.header("穴候補（4〜9番人気）")
    for h in holes[:5]:
        st.write(f"{h.number} {h.name}｜{h.popularity}番人気｜{h.score}点｜{comment(h)}")

    st.divider()

    st.header("消し馬（10番人気以下）")
    if cut:
        for h in cut:
            st.write(f"{h.number} {h.name}｜{h.popularity}番人気")
    else:
        st.write("なし")

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        st.subheader("馬連")
        for b in bets["馬連"]:
            st.code(b)

    with c2:
        st.subheader("ワイド")
        for b in bets["ワイド"]:
            st.code(b)

    with c3:
        st.subheader("3連単")
        for b in bets["3連単"]:
            st.code(b)
