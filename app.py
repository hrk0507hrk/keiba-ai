import streamlit as st
import re
from datetime import date, datetime
from dataclasses import dataclass, field
from itertools import permutations

st.set_page_config(page_title="競馬AI Ver.4.0 馬柱×指数融合版", layout="wide")
st.title("競馬AI｜Ver.4.0 馬柱×指数融合版")
st.caption("馬柱70％＋netkeiba指数30％。馬柱で競馬を読み、指数で能力・近況・適性・展開を裏付けます。")

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

time_index_text = st.text_area(
    "③ netkeibaタイム指数を貼ってください",
    height=240,
    key=f"time_index_{st.session_state.clear_count}",
    help="最高・5走平均・距離・コース・スタート・追走・上がり・近3走指数を読み取ります。未や－はデータなし扱いで減点しません。",
)

col3, col4 = st.columns(2)

with col3:
    good_frame_text = st.text_input(
        "④ 有利枠（例：1,3,8）",
        key=f"frames_{st.session_state.clear_count}",
    )

with col4:
    good_track_text = st.text_input(
        "⑤ 今回の馬場状態が得意な馬番（例：2,7,11）",
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
class TimeIndexData:
    highest: int | None = None
    avg5: int | None = None
    distance: int | None = None
    course: int | None = None
    start: int | None = None
    chase: int | None = None
    closing: int | None = None
    three_ago: int | None = None
    two_ago: int | None = None
    last: int | None = None


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
    best_time_index: int | None = None
    time_index: TimeIndexData = field(default_factory=TimeIndexData)
    index_ability_score: int = 0
    index_stability_score: int = 0
    index_suitability_score: int = 0
    index_pace_score: int = 0
    index_total_score: int = 0
    index_trend: str = "データなし"
    index_labels: list[str] = field(default_factory=list)
    time_index_pass: bool = True
    time_index_reason: str = ""
    score: int = 0
    total: int = 0

    # Ver.3.2 評価内訳
    ability_score: int = 0
    stability_score: int = 0
    suitability_score: int = 0
    pace_score: int = 0
    support_score: int = 0

    # 能力45点の内訳
    class_ability_score: int = 0
    margin_ability_score: int = 0
    winning_ability_score: int = 0
    content_ability_score: int = 0
    ability_penalty: int = 0
    layoff_days: int = 0
    overvaluation_warning: bool = False
    penalty_reasons: list[str] = field(default_factory=list)

    style: str = ""
    interpretation: str = ""
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
    """
    PC版の中央・地方両対応。

    対応例:
    地方:
    1 1
    --
    馬名
    牝4 54.0 騎手 ... 490(-3) 37.8
    9

    中央:
    1
    1
    --
    馬名
    牡4 57.0 騎手 ...
    31.4
    9
    """
    horses = []
    i = 0

    while i < len(lines):
        frame = None
        number = None
        header_end = None

        # 地方など「枠 馬番」が同じ行
        m_same = re.fullmatch(r"(\d+)\s+(\d+)", lines[i])
        if m_same:
            frame = int(m_same.group(1))
            number = int(m_same.group(2))
            header_end = i + 1

        # 中央など「枠」「馬番」が別行
        elif (
            re.fullmatch(r"\d+", lines[i])
            and i + 1 < len(lines)
            and re.fullmatch(r"\d+", lines[i + 1])
        ):
            frame = int(lines[i])
            number = int(lines[i + 1])
            header_end = i + 2

        else:
            i += 1
            continue

        # 次の馬のヘッダーまでを1頭分ブロックにする
        j = header_end
        block = []

        while j < len(lines):
            # 次の地方形式
            if j > header_end and re.fullmatch(r"\d+\s+\d+", lines[j]):
                break

            # 次の中央形式
            if (
                j > header_end
                and re.fullmatch(r"\d+", lines[j])
                and j + 1 < len(lines)
                and re.fullmatch(r"\d+", lines[j + 1])
            ):
                break

            block.append(lines[j])
            j += 1

        # 「--」の次を馬名とする
        name = ""
        for idx, row in enumerate(block):
            if row == "--" and idx + 1 < len(block):
                name = block[idx + 1].strip()
                break

        # 保険：最初の文字列らしい行
        if not name:
            for row in block:
                if (
                    row not in {"--", "編集"}
                    and not re.fullmatch(r"\d+(?:\.\d+)?", row)
                    and not re.fullmatch(r"\d+", row)
                    and "人気" not in row
                ):
                    name = row.strip()
                    break

        if not name:
            i = j
            continue

        block_text = " ".join(block)

        odds = None
        pop = 99
        jockey = ""
        weight = 0.0
        bodyweight = 0

        # 性齢行を探す
        info_line = ""
        for row in block:
            if re.search(r"[牡牝セ騸]\d+", row):
                info_line = row
                break

        info_parts = info_line.split()

        # 斤量と騎手
        for idx, token in enumerate(info_parts):
            try:
                value = float(token)
            except ValueError:
                continue

            if 45.0 <= value <= 65.0:
                weight = value
                if idx + 1 < len(info_parts):
                    jockey = info_parts[idx + 1]
                break

        # 馬体重
        bw = re.search(r"\b(\d{3})(?:kg|\([+-]?\d+\))", block_text)
        if bw:
            bodyweight = int(bw.group(1))

        # 「31.4 (9人気)」形式
        pair = re.search(r"(\d+\.\d+)\s*\((\d+)\s*人気\)", block_text)
        if pair:
            odds = float(pair.group(1))
            pop = int(pair.group(2))

        # 「9人気」表記
        if pop == 99:
            mp = re.search(r"(\d+)\s*人気", block_text)
            if mp:
                pop = int(mp.group(1))

        # オッズ候補：斤量を除外し、最後の妥当な小数を優先
        if odds is None:
            decimal_candidates = []
            for row_idx, row in enumerate(block):
                for token in re.findall(r"\b(\d+\.\d+)\b", row):
                    try:
                        value = float(token)
                    except ValueError:
                        continue

                    if 45.0 <= value <= 65.0:
                        continue

                    # 走破時計や上がりが混ざらない出走表ブロックを想定
                    if 1.0 <= value <= 999.9:
                        decimal_candidates.append((row_idx, value))

            if decimal_candidates:
                odds_row_idx, odds = decimal_candidates[-1]
            else:
                odds_row_idx = None
        else:
            odds_row_idx = None
            for idx, row in enumerate(block):
                if str(odds) in row:
                    odds_row_idx = idx
                    break

        # 人気が数字だけの行の場合
        if pop == 99:
            # まずオッズ行より後の単独数字を探す
            if odds_row_idx is not None:
                for row in block[odds_row_idx + 1:odds_row_idx + 6]:
                    if re.fullmatch(r"\d+", row):
                        value = int(row)
                        if 1 <= value <= 30:
                            pop = value
                            break

            # 同じ行に「31.4 9」のように並ぶ場合
            if pop == 99 and odds is not None:
                same_line = re.search(
                    rf"{re.escape(str(odds))}\s+(\d+)(?:\s|$)",
                    block_text,
                )
                if same_line:
                    value = int(same_line.group(1))
                    if 1 <= value <= 30:
                        pop = value

            # 最後の保険：「編集」の直前、またはブロック末尾の単独数字
            if pop == 99:
                for idx, row in enumerate(block):
                    if (
                        row == "編集"
                        and idx > 0
                        and re.fullmatch(r"\d+", block[idx - 1])
                    ):
                        value = int(block[idx - 1])
                        if 1 <= value <= 30:
                            pop = value
                            break

            if pop == 99:
                for row in reversed(block):
                    if re.fullmatch(r"\d+", row):
                        value = int(row)
                        if 1 <= value <= 30:
                            pop = value
                            break

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

        i = j

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



def _to_index_value(token: str) -> int | None:
    token = (token or "").replace("*", "").strip()
    if token in {"", "-", "--", "―", "未"}:
        return None
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", token):
        return None
    return max(int(float(token)), 0)


def parse_time_index_table(text: str) -> dict[int, TimeIndexData]:
    """netkeibaプレミアムの指数表を全項目読み取る。中央・地方の枠/馬番表記に対応。"""
    result: dict[int, TimeIndexData] = {}
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    i = 0
    while i < len(lines):
        horse_no = None
        j = i + 1
        same = re.fullmatch(r"(\d+)\s+(\d+)", lines[i])
        if same:
            horse_no = int(same.group(2))
        elif i + 1 < len(lines) and re.fullmatch(r"\d+", lines[i]) and re.fullmatch(r"\d+", lines[i+1]):
            horse_no = int(lines[i+1]); j = i + 2
        else:
            i += 1; continue

        block = lines[i:j]
        while j < len(lines):
            if re.fullmatch(r"\d+\s+\d+", lines[j]): break
            if j + 1 < len(lines) and re.fullmatch(r"\d+", lines[j]) and re.fullmatch(r"\d+", lines[j+1]): break
            block.append(lines[j]); j += 1

        parts = [p for p in re.split(r"\s+", " ".join(block)) if p]
        sex_i = next((k for k,p in enumerate(parts) if re.fullmatch(r"[牡牝セ騸]\d+", p)), None)
        data = TimeIndexData()
        if sex_i is not None:
            # 性齢,斤量,騎手の次から順番に11指数。オッズ・人気は対象外。
            vals = parts[sex_i+3:sex_i+13]
            vals += [""] * (10-len(vals))
            parsed = [_to_index_value(v) for v in vals[:10]]
            (data.highest, data.start, data.chase, data.closing, data.avg5,
             data.distance, data.course, data.three_ago,
             data.two_ago, data.last) = parsed
        result[horse_no] = data
        i = j
    return result


def _relative_points(value: int | None, values: list[int], max_points: int) -> int:
    if value is None or not values or max_points <= 0:
        return 0
    lo, hi = min(values), max(values)
    if hi == lo:
        return round(max_points * 0.6)
    ratio = (value - lo) / (hi - lo)
    return max(0, min(max_points, round(ratio * max_points)))


def _trend_label(data: TimeIndexData) -> tuple[str, int]:
    vals = [data.three_ago, data.two_ago, data.last]
    if any(v is None for v in vals):
        return "データ不足", 0
    a,b,c = vals
    if a < b < c and c-a >= 8: return "↗ 強い上昇", 3
    if a <= b <= c and c-a >= 3: return "↗ 上昇", 2
    if a > b > c and a-c >= 8: return "↘ 強い下降", -2
    if a >= b >= c and a-c >= 3: return "↘ 下降", -1
    return "→ 横ばい", 0


def apply_time_index_scoring(horses: list[Horse], index_map: dict[int, TimeIndexData]):
    """馬柱70％＋指数30％に再配分し、100点満点へ統合する。データなしは減点しない。"""
    fields = ["highest","avg5","distance","course","start","chase","closing"]
    pools = {f:[getattr(d,f) for d in index_map.values() if getattr(d,f) is not None] for f in fields}

    for h in horses:
        d = index_map.get(h.number, TimeIndexData())
        h.time_index = d
        h.best_time_index = d.highest
        h.index_labels = []

        # 既存の馬柱点を正式配分へ圧縮：能力30・安定12・適性8・展開4
        card_ability = round(h.ability_score / 45 * 30)
        card_stability = round(h.stability_score / 20 * 12)
        card_suitability = round(h.suitability_score / 20 * 8)
        card_pace = round(h.pace_score / 10 * 4)

        # 指数配点：能力15（追走6・5走平均5・最高4）
        ia = (_relative_points(d.chase,pools["chase"],6)
              + _relative_points(d.avg5,pools["avg5"],5)
              + _relative_points(d.highest,pools["highest"],4))

        # 安定8（5走平均5・近3走推移3）
        trend, trend_bonus = _trend_label(d)
        h.index_trend = trend
        base_stab = _relative_points(d.avg5,pools["avg5"],5)
        if trend_bonus >= 0:
            ist = min(8, base_stab + trend_bonus)
        else:
            ist = max(0, base_stab + trend_bonus)

        # 適性12（距離6・コース6）
        isu = (_relative_points(d.distance,pools["distance"],6)
               + _relative_points(d.course,pools["course"],6))

        # 展開6（スタート3・上がり3）＋脚質との相性
        start_p = _relative_points(d.start,pools["start"],3)
        close_p = _relative_points(d.closing,pools["closing"],3)
        if h.style in {"逃げ","先行"}:
            ip = min(6, start_p + round(close_p*0.35))
        elif h.style in {"差し","追込"}:
            ip = min(6, close_p + round(start_p*0.35))
        else:
            ip = min(6, start_p + close_p)

        h.index_ability_score = ia
        h.index_stability_score = ist
        h.index_suitability_score = isu
        h.index_pace_score = ip

        # 指数総合点：馬柱とは完全に独立し、指数だけで100点換算。
        # 欠損項目は0点にせず、取得できた項目の配点だけで再按分する。
        index_components = [
            (d.highest,  _relative_points(d.highest,  pools["highest"], 10), 10),
            (d.avg5,     _relative_points(d.avg5,     pools["avg5"], 20), 20),
            (d.distance, _relative_points(d.distance, pools["distance"], 15), 15),
            (d.course,   _relative_points(d.course,   pools["course"], 15), 15),
            (d.start,    _relative_points(d.start,    pools["start"], 5), 5),
            (d.chase,    _relative_points(d.chase,    pools["chase"], 25), 25),
            (d.closing,  _relative_points(d.closing,  pools["closing"], 5), 5),
        ]
        earned = sum(points for value, points, weight in index_components if value is not None)
        available_max = sum(weight for value, points, weight in index_components if value is not None)

        trend_values = [d.three_ago, d.two_ago, d.last]
        if all(v is not None for v in trend_values):
            trend_points = {
                "↗ 強い上昇": 5,
                "↗ 上昇": 4,
                "→ 横ばい": 3,
                "↘ 下降": 1,
                "↘ 強い下降": 0,
            }.get(trend, 3)
            earned += trend_points
            available_max += 5

        h.index_total_score = round(earned / available_max * 100) if available_max else 0

        h.ability_score = min(45, card_ability + ia)
        h.stability_score = min(20, card_stability + ist)
        h.suitability_score = min(20, card_suitability + isu)
        h.pace_score = min(10, card_pace + ip)
        h.support_score = min(h.support_score, 5)

        if d.chase is not None and pools["chase"] and d.chase >= max(pools["chase"])-1:
            h.index_labels.append("追走力S")
        if d.start is not None and pools["start"] and d.start >= max(pools["start"])-1:
            h.index_labels.append("先行力S")
        if d.closing is not None and pools["closing"] and d.closing >= max(pools["closing"])-1:
            h.index_labels.append("切れ味S")
        if d.distance is not None and d.course is not None:
            if _relative_points(d.distance,pools["distance"],6) >= 5 and _relative_points(d.course,pools["course"],6) >= 5:
                h.index_labels.append("条件替わりプラス")
        if "上昇" in trend:
            h.index_labels.append("上昇馬")
        elif "下降" in trend:
            h.index_labels.append("下降馬")

        available = sum(v is not None for v in vars(d).values())
        h.time_index_reason = f"指数{available}/10項目取得｜能力+{ia} 安定+{ist} 適性+{isu} 展開+{ip}｜近況{trend}"
        if available:
            h.reasons.append(h.time_index_reason)
        else:
            h.time_index_reason = "指数データなし（減点なし）"

        h.score = h.ability_score+h.stability_score+h.suitability_score+h.pace_score+h.support_score
        h.interpretation = build_interpretation(h)

    valid_high = [d.highest for d in index_map.values() if d.highest is not None]
    return (max(valid_high), min(valid_high)) if valid_high else (None,None)

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
    """
    馬柱内の持ち時計・上がりを比較する。
    Ver.3では時計を主役にせず、補助評価の上限内で小さく加点する。
    """
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
        horse.best_last3f = min(
            (r.last3f for r in relevant if r.last3f > 0),
            default=0.0,
        )

        if horse.best_time_sec > 0:
            time_profiles.append((horse.number, horse.best_time_sec))
        if horse.best_last3f > 0:
            closing_profiles.append((horse.number, horse.best_last3f))

    time_profiles.sort(key=lambda x: x[1])
    closing_profiles.sort(key=lambda x: x[1])

    time_rank = {no: (i + 1, value) for i, (no, value) in enumerate(time_profiles)}
    closing_rank = {no: (i + 1, value) for i, (no, value) in enumerate(closing_profiles)}

    for horse in horses:
        horse.time_score = 0
        horse.closing_score = 0

        if horse.number in time_rank:
            rank, value = time_rank[horse.number]
            if rank == 1:
                horse.time_score = 2
            elif rank <= max(2, len(time_profiles) // 4):
                horse.time_score = 1

            if horse.time_score:
                horse.support_score += horse.time_score
                horse.reasons.append(
                    f"同条件の持ち時計上位({value:.1f}秒) +{horse.time_score}"
                )

        if horse.number in closing_rank:
            rank, value = closing_rank[horse.number]
            if rank == 1:
                horse.closing_score = 2
            elif rank <= max(2, len(closing_profiles) // 4):
                horse.closing_score = 1

            if horse.closing_score:
                horse.support_score += horse.closing_score
                horse.reasons.append(
                    f"同条件の上がり上位({value:.1f}) +{horse.closing_score}"
                )

        # 補助材料が総合評価を支配しないよう上限5点
        horse.support_score = min(horse.support_score, 5)

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

    # Ver.3では能力評価の一部として使用し、上級実績だけの暴走を防ぐ
    return min(score, 20), reasons


def safe_rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def race_level_text(raw: str) -> str:
    text = (raw or "").upper()
    if any(k in text for k in ["G1", "GⅠ", "JPN1", "JPNⅠ"]):
        return "G1"
    if any(k in text for k in ["G2", "GⅡ", "JPN2", "JPNⅡ"]):
        return "G2"
    if any(k in text for k in ["G3", "GⅢ", "JPN3", "JPNⅢ"]):
        return "G3"
    if any(k in text for k in ["オープン", "OPEN", "リステッド", "LISTED"]):
        return "OP"
    if any(k in text for k in ["3勝クラス", "３勝クラス", "1600万"]):
        return "3勝"
    if any(k in text for k in ["2勝クラス", "２勝クラス", "1000万"]):
        return "2勝"
    if any(k in text for k in ["1勝クラス", "１勝クラス", "500万"]):
        return "1勝"
    if any(k in text for k in ["A1", "A2", "Ｓ１", "Ｓ２", "S1", "S2"]):
        return "地方上級"
    return ""


def build_interpretation(horse: Horse) -> str:
    races = horse.races[:9]
    if not races:
        return "馬柱の読み取り量が不足しているため、評価の信頼度は低め。"

    recent3 = races[:3]
    close_recent = sum(1 for r in recent3 if r.margin <= 0.5)
    top5_recent = sum(1 for r in recent3 if r.finish <= 5)
    top3_all = sum(1 for r in races if r.finish <= 3)

    parts = []

    if top5_recent >= 3:
        parts.append("近3走すべて掲示板内で、現在の状態は安定")
    elif top5_recent >= 2:
        parts.append("近走で勝ち負けに加われる内容を維持")
    elif all(r.finish >= 9 for r in recent3[:2]) and len(recent3) >= 2:
        parts.append("近走着順は低調で、巻き返しには条件好転が必要")

    if close_recent >= 2:
        parts.append("着順以上に勝ち馬との着差が小さく、能力は落ちていない")

    if top3_all >= 4:
        parts.append("過去9走の複勝圏率が高く、馬券内候補として信頼しやすい")

    levels = [race_level_text(r.raw) for r in races]
    levels = [x for x in levels if x]
    if levels:
        parts.append(f"{levels[0]}を含む上位条件の経験が能力の裏付け")

    if horse.suitability_score >= 15:
        parts.append("今回条件への適性が高い")
    elif horse.suitability_score <= 5:
        parts.append("今回条件への明確な適性材料は少ない")

    if horse.pace_score >= 7:
        parts.append("想定展開と脚質の相性も良い")

    return "。".join(parts[:4]) + ("。" if parts else "強い強調材料は少なめ。")



def margin_band_points(margin: float) -> int:
    """着差の1走評価。上位馬が簡単に満点へ張り付かない6段階。"""
    if margin >= 90:
        return 0
    if margin <= 0.2:
        return 5
    if margin <= 0.5:
        return 4
    if margin <= 0.8:
        return 3
    if margin <= 1.2:
        return 2
    if margin <= 1.5:
        return 1
    return 0


def finish_support_points(finish: int) -> int:
    """着順は内容評価の補助。着差より弱く扱う。"""
    if finish == 1:
        return 3
    if finish == 2:
        return 2
    if finish == 3:
        return 1
    if finish <= 5:
        return 1
    return 0


def race_class_base_score(raw: str) -> int:
    """レース格の基礎点。肩書だけで満点にならないよう最大12点。"""
    level = race_level_text(raw)
    return {
        "G1": 12,
        "G2": 11,
        "G3": 10,
        "OP": 9,
        "3勝": 8,
        "2勝": 7,
        "地方上級": 7,
        "1勝": 6,
    }.get(level, 4)


def class_performance_score(race: RaceRecord) -> int:
    """クラス名と、そのクラスで実際に通用したかを一体評価する。"""
    score = race_class_base_score(race.raw)

    if race.margin < 90:
        if race.margin <= 0.3:
            adjustment = 0
        elif race.margin <= 0.7:
            adjustment = -1
        elif race.margin <= 1.0:
            adjustment = -2
        elif race.margin <= 1.5:
            adjustment = -4
        else:
            adjustment = -6
        score += adjustment
    elif race.finish > 5:
        score -= 3

    if race.finish == 1:
        score += 1
    elif race.finish <= 3:
        score += 0
    elif race.finish >= 10:
        score -= 1

    return max(0, min(score, 12))


def passing_gain(race: RaceRecord) -> int:
    """道中位置から着順まで何頭分押し上げたか。"""
    nums = [int(x) for x in re.findall(r"\d+", race.passing or "")]
    if not nums or race.finish >= 90:
        return 0
    start_pos = nums[0]
    return max(start_pos - race.finish, 0)


def parse_record_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None

    for fmt in ("%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass

    # 地方のMM/DD形式。現在日より大きく未来になる場合は前年扱い。
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", value)
    if m:
        today = date.today()
        month, day = int(m.group(1)), int(m.group(2))
        try:
            candidate = date(today.year, month, day)
            if candidate > today:
                candidate = date(today.year - 1, month, day)
            return candidate
        except ValueError:
            return None
    return None


def calculate_layoff_days(horse: Horse) -> int:
    dates = [parse_record_date(r.date) for r in horse.races]
    dates = [d for d in dates if d is not None]
    if not dates:
        return 0
    latest = max(dates)
    return max((date.today() - latest).days, 0)


def same_class_close_form(races: list[RaceRecord]) -> tuple[int, int, str]:
    """直近の基準クラスで0.5秒以内・1.0秒以内の回数を返す。"""
    levels = [race_level_text(r.raw) for r in races]
    base_level = next((x for x in levels if x), "")
    target = [r for r in races if not base_level or race_level_text(r.raw) == base_level]
    close05 = sum(1 for r in target if r.margin <= 0.5)
    close10 = sum(1 for r in target if r.margin <= 1.0)
    return close05, close10, base_level


def evaluate_horse(
    horse: Horse,
    good_frames: list[int],
    good_track_horses: list[int],
    condition: str,
    current_surface: str,
    current_distance: int,
    pace_counts: dict[str, int],
):
    """
    Ver.4.0 馬柱側の基礎評価
    能力45・安定20・適性20・展開10・補助5 = 100点

    能力は「着差＞着順」。
    高得点でも勝利・僅差実績が乏しい馬は過大評価フィルターで減点する。
    """
    horse.reasons = []
    horse.cautions = []
    horse.penalty_reasons = []
    horse.overvaluation_warning = False
    horse.ability_score = 0
    horse.stability_score = 0
    horse.suitability_score = 0
    horse.pace_score = 0
    horse.support_score = 0
    horse.class_ability_score = 0
    horse.margin_ability_score = 0
    horse.winning_ability_score = 0
    horse.content_ability_score = 0
    horse.ability_penalty = 0
    horse.layoff_days = 0

    races = horse.races[:9]
    recent3 = races[:3]
    recent5 = races[:5]
    horse.style = running_style_from_races(horse)

    if not races:
        horse.cautions.append("馬柱読み取り不足")
        horse.score = 0
        horse.interpretation = build_interpretation(horse)
        return horse

    # ─────────────────────────
    # 1. 能力評価（最大45）
    # クラス12・着差18・勝負7・内容8－減点
    # ─────────────────────────

    # ① クラス能力（最大12）
    # レース格だけでなく、そのクラスでどこまで通用したかを評価。
    class_performances = sorted(
        (class_performance_score(r) for r in races),
        reverse=True,
    )
    if class_performances:
        weights = [0.55, 0.30, 0.15]
        selected = class_performances[:3]
        used_weights = weights[:len(selected)]
        weight_sum = sum(used_weights)
        class_score = sum(s * w for s, w in zip(selected, used_weights)) / weight_sum
        horse.class_ability_score = max(0, min(round(class_score), 12))

    best_level = max((race_class_base_score(r.raw) for r in races), default=0)
    class_close = sum(
        1 for r in races
        if race_class_base_score(r.raw) >= max(best_level - 1, 4)
        and r.margin <= 0.7
    )
    if class_close >= 3:
        horse.class_ability_score = min(horse.class_ability_score + 1, 12)
        horse.reasons.append("上位クラス帯で僅差内容を継続 +1")

    if horse.class_ability_score >= 10:
        horse.reasons.append("上位条件で通用した実績")
    elif horse.class_ability_score <= 5:
        horse.cautions.append("クラス実績の裏付けは弱め")

    # ② 着差能力（最大18）
    # 近5走の平均内容を基準にし、一部の好走だけで満点にならないよう調整。
    margin_weights = [1.00, 0.90, 0.78, 0.66, 0.55]
    weighted_points = 0.0
    used_weight = 0.0
    valid_margin_count = 0

    for idx, r in enumerate(recent5):
        if r.margin >= 90:
            continue
        w = margin_weights[idx]
        weighted_points += margin_band_points(r.margin) * w
        used_weight += w
        valid_margin_count += 1

    if used_weight > 0:
        margin_average = weighted_points / used_weight  # 0～5
        horse.margin_ability_score = round(margin_average / 5 * 16)
    else:
        horse.margin_ability_score = 0

    close05, close10, base_level = same_class_close_form(races[:5])
    if close05 >= 3:
        horse.margin_ability_score += 2
        horse.reasons.append(f"同クラス{base_level or '近走'}0.5秒以内を複数 +2")
    elif close10 >= 4:
        horse.margin_ability_score += 1
        horse.reasons.append(f"同クラス{base_level or '近走'}1.0秒以内を継続 +1")

    horse.margin_ability_score = max(0, min(horse.margin_ability_score, 18))
    if horse.margin_ability_score >= 14:
        horse.reasons.append("近走の着差内容が高水準")
    elif valid_margin_count == 0:
        horse.cautions.append("着差データ不足")

    # ③ 勝負能力（最大7）
    wins = sum(1 for r in races if r.finish == 1)
    seconds = sum(1 for r in races if r.finish == 2)
    thirds = sum(1 for r in races if r.finish == 3)
    top3 = wins + seconds + thirds

    winning = min(wins * 2, 4)
    winning += min(seconds, 2)
    if top3 >= 5:
        winning += 1
    horse.winning_ability_score = min(winning, 7)

    if wins >= 2:
        horse.reasons.append("勝ち切り実績複数")
    elif wins == 1:
        horse.reasons.append("勝利実績あり")

    # ④ 内容評価（最大8）
    # 着順の良さより、負け方・位置取り・継続性を重視。
    content = 0

    bad_but_close = sum(
        1 for r in recent5
        if r.finish >= 6 and r.margin <= 1.0
    )
    if bad_but_close >= 2:
        content += 3
        horse.reasons.append("着順以上に内容のある敗戦を複数 +3")
    elif bad_but_close == 1:
        content += 2
        horse.reasons.append("着順以上に内容のある敗戦 +2")

    strong_closing_runs = sum(
        1 for r in recent5
        if passing_gain(r) >= 4 and r.margin <= 1.2
    )
    if strong_closing_runs >= 2:
        content += 2
        horse.reasons.append("道中位置から大きく押し上げた走りを複数 +2")
    elif strong_closing_runs == 1:
        content += 1
        horse.reasons.append("道中位置から押し上げる内容 +1")

    recent_close = sum(1 for r in recent3 if r.margin <= 0.7)
    if recent_close >= 2:
        content += 2
        horse.reasons.append("近3走で僅差内容を維持 +2")
    elif recent_close == 1:
        content += 1

    finish_support = sum(
        finish_support_points(r.finish) * w
        for r, w in zip(recent5, [1.0, 0.85, 0.70, 0.55, 0.40])
    )
    content += min(round(finish_support / 3), 2)
    horse.content_ability_score = min(content, 8)

    # ⑤ 能力減点・過大評価防止
    penalty = 0

    horse.layoff_days = calculate_layoff_days(horse)
    if horse.layoff_days >= 120:
        penalty += 2
        horse.penalty_reasons.append(f"長期休養{horse.layoff_days}日 -2")
    elif horse.layoff_days >= 90:
        penalty += 1
        horse.penalty_reasons.append(f"休養明け{horse.layoff_days}日 -1")

    same_class_races = races[:5]
    if base_level:
        same_class_races = [r for r in races[:5] if race_level_text(r.raw) == base_level]
    same_wins = sum(1 for r in same_class_races if r.finish == 1)
    same_top3 = sum(1 for r in same_class_races if r.finish <= 3)
    same_close = sum(1 for r in same_class_races if r.margin <= 0.7)

    # 僅差内容があれば「勝ち切れず」の減点を弱める。
    if len(same_class_races) >= 4 and same_wins == 0:
        if same_top3 == 0 and same_close == 0:
            penalty += 3
            horse.penalty_reasons.append("同クラスで好走・僅差実績なし -3")
        elif same_top3 <= 1 and same_close <= 1:
            penalty += 1
            horse.penalty_reasons.append("同クラスで勝ち切れず -1")

    pre_penalty = (
        horse.class_ability_score
        + horse.margin_ability_score
        + horse.winning_ability_score
        + horse.content_ability_score
    )
    close_all = sum(1 for r in races if r.margin <= 0.7)
    heavy_losses = sum(1 for r in recent5 if 1.5 < r.margin < 90)

    if pre_penalty >= 31 and wins == 0 and close_all <= 1:
        penalty += 4
        horse.overvaluation_warning = True
        horse.penalty_reasons.append("高評価に対して勝利・僅差実績不足 -4")
    elif pre_penalty >= 28 and wins == 0 and top3 <= 1 and heavy_losses >= 2:
        penalty += 2
        horse.overvaluation_warning = True
        horse.penalty_reasons.append("高評価に対して大敗が多い -2")

    horse.ability_penalty = min(penalty, 8)
    horse.ability_score = max(
        0,
        min(
            horse.class_ability_score
            + horse.margin_ability_score
            + horse.winning_ability_score
            + horse.content_ability_score
            - horse.ability_penalty,
            45,
        ),
    )

    if horse.penalty_reasons:
        horse.cautions.extend(horse.penalty_reasons)
    if horse.overvaluation_warning:
        horse.cautions.append("⚠ 過大評価注意")
    if horse.ability_score >= 36:
        horse.reasons.append("馬柱能力評価A")
    elif horse.ability_score >= 28:
        horse.reasons.append("馬柱能力評価B+")

    # ─────────────────────────
    # 2. 安定感（最大20）
    # ─────────────────────────
    stability = 0
    in3 = sum(1 for r in races if r.finish <= 3)
    in5 = sum(1 for r in races if r.finish <= 5)
    within_one = sum(1 for r in races if r.margin <= 1.0)
    heavy_losses = sum(1 for r in races if r.margin > 1.5 and r.margin < 90)

    stability += round(safe_rate(in3, len(races)) * 8)
    stability += round(safe_rate(in5, len(races)) * 5)
    stability += round(safe_rate(within_one, len(races)) * 7)
    stability -= round(safe_rate(heavy_losses, len(races)) * 4)

    if len(recent3) >= 3:
        finishes = [r.finish for r in recent3]
        if finishes[0] <= finishes[1] <= finishes[2]:
            stability += 2
            horse.reasons.append("近走上昇・維持傾向 +2")
        if all(r.finish >= 10 for r in recent3[:2]):
            stability -= 4
            horse.cautions.append("近2走二桁着順")

    horse.stability_score = max(0, min(round(stability), 20))
    if horse.stability_score >= 15:
        horse.reasons.append("安定感が高い")

    # ─────────────────────────
    # 3. 今回条件への適性（最大20）
    # ─────────────────────────
    suitability = 0

    same_surface = [r for r in races if current_surface and r.surface == current_surface]
    near_distance = [
        r for r in races
        if current_distance and abs(r.distance - current_distance) <= 200
        and (not current_surface or r.surface == current_surface)
    ]
    exactish_distance = [
        r for r in races
        if current_distance and abs(r.distance - current_distance) <= 100
        and (not current_surface or r.surface == current_surface)
    ]
    same_condition = [r for r in races if r.condition == condition]

    if same_surface:
        good = sum(1 for r in same_surface if r.finish <= 5 or r.margin <= 1.0)
        suitability += min(4, round(safe_rate(good, len(same_surface)) * 4))

    if near_distance:
        good = sum(1 for r in near_distance if r.finish <= 5 or r.margin <= 1.0)
        suitability += min(5, round(safe_rate(good, len(near_distance)) * 5))

    if exactish_distance:
        top3_exact = sum(1 for r in exactish_distance if r.finish <= 3)
        close_exact = sum(1 for r in exactish_distance if r.margin <= 0.7)
        if top3_exact >= 2 or close_exact >= 3:
            suitability += 4
            horse.reasons.append("同距離帯の好内容複数 +4")
        elif top3_exact == 1 or close_exact >= 1:
            suitability += 2
            horse.reasons.append("同距離帯の好内容 +2")

    if same_condition:
        good = sum(1 for r in same_condition if r.finish <= 3 or r.margin <= 0.7)
        if good >= 2:
            suitability += 4
            horse.reasons.append(f"{condition}馬場実績複数 +4")
        elif good == 1:
            suitability += 2
            horse.reasons.append(f"{condition}馬場実績 +2")

    frame_bonus = horse.frame in good_frames
    track_bonus = horse.number in good_track_horses

    if frame_bonus:
        suitability += 3
        horse.reasons.append("手入力・有利枠 +3")
    if track_bonus:
        suitability += 5
        horse.reasons.append("手入力・馬場適性 +5")
    if frame_bonus and track_bonus:
        suitability += 3
        horse.reasons.append("有利枠×馬場適性 +3")

    horse.suitability_score = min(round(suitability), 20)

    # ─────────────────────────
    # 4. 展開・脚質（最大10）
    # ─────────────────────────
    pace = 3
    front_total = pace_counts.get("逃げ", 0) + pace_counts.get("先行", 0)
    runners = max(sum(pace_counts.values()), 1)
    crowded_front = front_total >= max(5, runners // 2)

    if horse.style == "逃げ":
        if pace_counts.get("逃げ", 0) <= 1:
            pace += 5
            horse.reasons.append("単騎逃げ期待 +5")
        elif crowded_front:
            pace -= 2
            horse.cautions.append("逃げ・先行多数で展開減点 -2")
    elif horse.style == "先行":
        if front_total <= max(4, runners // 3):
            pace += 4
            horse.reasons.append("先行力を生かしやすい構成 +4")
        elif crowded_front:
            pace -= 1
            horse.cautions.append("前が多く先行争い減点 -1")
        else:
            pace += 1
    elif horse.style == "差し":
        if crowded_front:
            pace += 5
            horse.reasons.append("前が多く差し展開期待 +5")
        else:
            pace += 2
    elif horse.style == "追込":
        if front_total >= max(6, runners // 2):
            pace += 4
            horse.reasons.append("ハイペースなら追込浮上 +4")
        else:
            horse.cautions.append("展開待ち")

    if condition in ["重", "不良"] and horse.style in ["逃げ", "先行"]:
        pace += 2
        horse.reasons.append(f"{condition}馬場で前残り期待 +2")

    horse.pace_score = max(0, min(round(pace), 10))

    horse.score = (
        horse.ability_score
        + horse.stability_score
        + horse.suitability_score
        + horse.pace_score
        + horse.support_score
    )
    horse.interpretation = build_interpretation(horse)
    return horse


def run_scoring(
    horses: list[Horse],
    good_frames: list[int],
    good_track_horses: list[int],
    condition: str,
    current_surface: str,
    current_distance: int,
):
    # 全頭の脚質構成を先に確認し、今回の展開評価に使用
    pace_counts = {"逃げ": 0, "先行": 0, "差し": 0, "追込": 0, "不明": 0}
    for h in horses:
        h.style = running_style_from_races(h)
        pace_counts[h.style] = pace_counts.get(h.style, 0) + 1

    for h in horses:
        evaluate_horse(
            h,
            good_frames,
            good_track_horses,
            condition,
            current_surface,
            current_distance,
            pace_counts,
        )

    return horses, pace_counts


def select_marks(horses: list[Horse]):
    """
    好調時ロジック復元版。

    ・1〜3番人気を「人気馬グループ」として必ず残す
    ・4〜9番人気を「穴馬グループ」として評価
    ・人気馬上位3頭 → 穴馬上位3頭の順で、◎〇▲△☆注を付ける
    ・各グループ内は総合点、安定、能力、適性、展開、馬番で比較
    ・10番人気以下は完全消し

    これにより、今回の例では
    ◎コスモストーム
    〇ワイドクリーガー
    ▲タガノヘラクレス
    △タマモジャスミン
    ☆ホウショウマリス
    注タマモナポリ
    の並びに戻る。
    """
    def rank_key(h: Horse):
        return (
            h.score,
            h.stability_score,
            h.ability_score,
            h.suitability_score,
            h.pace_score,
            -h.number,
        )

    popular = sorted(
        [h for h in horses if 1 <= h.popularity <= 3],
        key=rank_key,
        reverse=True,
    )
    holes = sorted(
        [h for h in horses if 4 <= h.popularity <= 9],
        key=rank_key,
        reverse=True,
    )

    selected = popular[:3] + holes[:3]

    # 人気取得に失敗した馬が多い場合の保険。
    # 空き印だけを総合順位上位から補充する。
    if len(selected) < 6:
        already = {h.number for h in selected}
        fallback = sorted(
            [h for h in horses if h.popularity <= 9 and h.number not in already],
            key=rank_key,
            reverse=True,
        )
        selected.extend(fallback[: 6 - len(selected)])

    marks = {}
    for mark, horse in zip(["◎", "〇", "▲", "△", "☆", "注"], selected[:6]):
        marks[mark] = horse

    selected_numbers = {h.number for h in selected[:6]}
    remain = sorted(
        [h for h in horses if h.popularity <= 9 and h.number not in selected_numbers],
        key=rank_key,
        reverse=True,
    )
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
    if score >= 78:
        return "S"
    if score >= 66:
        return "A"
    if score >= 54:
        return "B"
    if score >= 42:
        return "C"
    return "D"



def comment(horse: Horse) -> str:
    reasons = " / ".join(horse.reasons) if horse.reasons else "強調材料は少なめ。"
    return f"{horse.interpretation}\n\n評価材料：{reasons}"


def race_type(horses: list[Horse]) -> str:
    ranked = sorted(horses, key=lambda h: h.score, reverse=True)
    if len(ranked) < 3:
        return "判定不可"
    diff = ranked[0].score - ranked[2].score
    if diff >= 14:
        return "本命寄り"
    if diff >= 7:
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

    time_index_map = parse_time_index_table(time_index_text)

    current_surface, current_distance = parse_current_race_conditions(racecard_text)

    horses, pace_counts = run_scoring(
        horses,
        good_frames,
        good_track_horses,
        track_condition,
        current_surface,
        current_distance,
    )

    # Ver.4.0：馬柱70％＋指数30％へ正式統合
    time_index_highest, time_index_lowest = apply_time_index_scoring(horses, time_index_map)
    clock_surface, clock_distance = calculate_clock_profiles(
        horses,
        current_surface,
        current_distance,
    )


    marks, ranking, cut = select_marks(horses)
    bets = make_bets(marks)
    ability = sorted(
        horses,
        key=lambda h: (
            h.score,
            h.stability_score,
            h.ability_score,
            h.suitability_score,
            h.pace_score,
            -h.number,
        ),
        reverse=True,
    )
    holes = [
        h for h in ability
        if 4 <= h.popularity <= 9
    ]

    st.success(f"{len(horses)}頭を読み取りました。")
    st.info(f"レース判定：{race_type(ability)}")

    if time_index_highest is None:
        st.info("指数は未取得です。未取得でも減点せず、馬柱評価だけで予想します。")
    else:
        st.info(
            f"Ver.4.0指数統合：最高{time_index_highest}／最低{time_index_lowest}"
            "（馬柱70％＋指数30％・データなしは減点なし）"
        )

    st.caption(
        "脚質構成："
        + " / ".join(f"{k}{v}頭" for k, v in pace_counts.items() if v)
    )

    with st.expander("指数11項目の読み取り確認"):
        if time_index_map:
            for no in sorted(time_index_map):
                d = time_index_map[no]
                fmt = lambda v: "未" if v is None else str(v)
                st.write(
                    f"{no}番｜最高{fmt(d.highest)}｜5走平均{fmt(d.avg5)}｜距離{fmt(d.distance)}｜コース{fmt(d.course)}"
                    f"｜スタート{fmt(d.start)}｜追走{fmt(d.chase)}｜上がり{fmt(d.closing)}"
                    f"｜3走前{fmt(d.three_ago)}｜2走前{fmt(d.two_ago)}｜前走{fmt(d.last)}"
                )
        else:
            st.write("読み取り結果なし")
    if clock_surface and clock_distance:
        st.caption(f"時計比較条件：{clock_surface}{clock_distance}m前後（±100m）")

    with st.expander("読み取り確認（馬番・馬名・人気・オッズ）"):
        for h in horses:
            pop_text = "未取得" if h.popularity == 99 else f"{h.popularity}人気"
            odds_text = "-" if h.odds is None else str(h.odds)
            time_text = f"{h.best_time_sec:.1f}秒" if h.best_time_sec > 0 else "未取得"
            last3f_text = f"{h.best_last3f:.1f}" if h.best_last3f > 0 else "未取得"
            index_text = (
                str(h.best_time_index)
                if h.best_time_index is not None
                else "データなし"
            )
            d = h.time_index
            fmt = lambda v: "未" if v is None else str(v)
            st.write(
                f"{h.number} {h.name}｜{pop_text}｜オッズ {odds_text}"
                f"｜最高{fmt(d.highest)} 5走平均{fmt(d.avg5)} 距離{fmt(d.distance)} コース{fmt(d.course)}"
                f"｜スタート{fmt(d.start)} 追走{fmt(d.chase)} 上がり{fmt(d.closing)}"
                f"｜近3走 {fmt(d.three_ago)}→{fmt(d.two_ago)}→{fmt(d.last)}"
            )

    st.header("指数比較")
    comparison_rows = []
    for h in sorted(horses, key=lambda x: x.index_total_score, reverse=True):
        d = h.time_index
        comparison_rows.append({
            "馬番": h.number, "馬名": h.name,
            "最高": d.highest, "5走平均": d.avg5, "距離": d.distance, "コース": d.course,
            "スタート": d.start, "追走": d.chase, "上がり": d.closing,
            "近3走推移": h.index_trend, "指数タイプ": " / ".join(h.index_labels) or "-",
            "指数総合点": h.index_total_score,
        })
    st.dataframe(comparison_rows, use_container_width=True, hide_index=True)

    st.header("AI印")

    for m in ["◎", "〇", "▲", "△", "☆", "注"]:
        if m not in marks:
            continue
        h = marks[m]
        index_text = (
            str(h.best_time_index)
            if h.best_time_index is not None
            else "データなし"
        )
        st.markdown(
            f"### {m} {h.number} {h.name}｜{h.popularity}番人気"
            f"｜評価{grade(h.score)}｜総合{h.score}点"
        )
        st.write(
            f"能力 {h.ability_score}/45｜安定 {h.stability_score}/20"
            f"｜適性 {h.suitability_score}/20｜展開 {h.pace_score}/10"
            f"｜補助 {h.support_score}/5"
        )
        st.caption(
            f"馬柱元評価：クラス{h.class_ability_score}/12"
            f"｜着差{h.margin_ability_score}/18"
            f"｜勝負{h.winning_ability_score}/7"
            f"｜内容{h.content_ability_score}/8"
            f"｜減点-{h.ability_penalty}"
        )
        st.caption(
            f"指数加点：能力+{h.index_ability_score}/15｜安定+{h.index_stability_score}/8"
            f"｜適性+{h.index_suitability_score}/12｜展開+{h.index_pace_score}/6｜近況 {h.index_trend}"
        )
        if h.index_labels:
            st.success(" / ".join(h.index_labels))
        st.write(h.interpretation)
        with st.expander("詳しい評価材料"):
            st.write(" / ".join(h.reasons) if h.reasons else "強調材料は少なめ。")
            st.caption(f"タイム指数：{h.time_index_reason}")
        if h.cautions:
            st.warning(" / ".join(h.cautions))

    st.divider()

    st.header("能力ランキング")
    for i, h in enumerate(ability, 1):
        st.write(
            f"{i}位　{h.number} {h.name}｜{h.popularity}番人気｜総合{h.score}点"
            f"｜能力{h.ability_score}｜安定{h.stability_score}"
            f"｜適性{h.suitability_score}｜展開{h.pace_score}"
            f"｜補助{h.support_score}｜脚質:{h.style}"
        )
        with st.expander(f"{h.number} {h.name} の評価理由"):
            st.write(h.interpretation)
            st.caption(
                f"能力内訳：クラス{h.class_ability_score}/12"
                f"｜着差{h.margin_ability_score}/18"
                f"｜勝負{h.winning_ability_score}/7"
                f"｜内容{h.content_ability_score}/8"
                f"｜減点-{h.ability_penalty}"
            )
            if h.layoff_days:
                st.caption(f"最終出走からの推定間隔：{h.layoff_days}日")
            st.caption("評価材料")
            st.write(" / ".join(h.reasons) if h.reasons else "強調材料は少なめ。")
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

    st.header("完全消し馬")
    if cut:
        for h in cut:
            reasons = []
            if h.popularity >= 10:
                reasons.append("10番人気以下")
            st.write(
                f"{h.number} {h.name}｜{h.popularity}番人気"
                f"｜{' / '.join(reasons)}"
            )
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
