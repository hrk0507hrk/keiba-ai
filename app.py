import streamlit as st
import re
from itertools import product, combinations

st.title("競馬予想AI")
st.write("出走表・データ分析・脚質・過去走データから、軸・2巡目・3巡目・買い目を自動作成します。")

if "clear_count" not in st.session_state:
    st.session_state.clear_count = 0

if st.button("🗑️ 入力内容をクリア"):
    st.session_state.clear_count += 1

POINTS = {
    "データ上位馬3頭": 0,
    "このコースが得意な馬": 15,
    "この距離が得意な馬": 12,
    "この競馬場が得意な馬": 12,
    "今回の馬場状態が得意な馬": 10,
    "今回のレース間隔で実績がある馬": 10,
    "このコースが得意な騎手": 8,
    "このコースが得意な調教師": 8,
    "このコースに実績がある種牡馬": 5,
    "好調枠順": 5,
    "有利脚質": 8,
}

IGNORE_WORDS = [
    "馬メモ", "レース別馬メモ", "全角100文字以内で入力してください",
    "削除保存", "閉じる", "編集", "次走買い", "次走消し",
    "不利", "馬場向かず", "ペース合わず", "ハイレベル戦", "好ラップ",
    "全グラフを表示"
]

race_table = st.text_area(
    "netkeibaの出走表を丸ごと貼ってください",
    height=430,
    key=f"race_{st.session_state.clear_count}"
)

analysis = st.text_area(
    "netkeibaのデータ分析を貼ってください",
    height=330,
    key=f"analysis_{st.session_state.clear_count}"
)

st.write("### 脚質入力")
st.caption("例：7 先行 のように1行ずつ入力してください。空欄でもOK。")

running_style_text = st.text_area(
    "各馬の脚質",
    height=160,
    placeholder="""例
1 先行
2 差し
3 逃げ""",
    key=f"style_{st.session_state.clear_count}"
)

style_graph_text = st.text_area(
    "脚質グラフを貼り付け（任意）",
    height=220,
    placeholder="""例
1
--
差 600 694 733 5341 7368 8% 17% 27% 58% 63% ブラックアピス
2
--
先 100 120 130 800 1000 10% 22% 35% 60% 70% サンプル""",
    key=f"graph_{st.session_state.clear_count}"
)

pace_text = st.text_area(
    "過去走データを貼り付け（任意）",
    height=330,
    placeholder="netkeibaの過去5走データをそのまま貼り付け",
    key=f"pace_{st.session_state.clear_count}"
)

track_condition = st.selectbox(
    "馬場状態",
    ["良", "稍重", "重", "不良"],
    index=0
)

def clean_lines(text):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(word in line for word in IGNORE_WORDS):
            continue
        if re.match(r"^\d+/100$", line):
            continue
        if re.match(r"^\d+/500$", line):
            continue
        lines.append(line)
    return lines

def make_horse(frame_no, horse_no, horse_name, popularity=None, odds=None, jockey="", trainer=""):
    return {
        "枠番": frame_no,
        "馬番": horse_no,
        "馬名": horse_name.strip(),
        "人気": popularity,
        "オッズ": odds,
        "騎手": jockey.strip(),
        "調教師": trainer.strip(),
        "脚質": "",
        "脚質勝率": None,
        "脚質複勝率": None,
        "カテゴリ": "",
        "点数": 0,
        "複勝点": 0,
        "安定指数": 0,
        "期待値指数": 0,
        "展開指数": 0,
        "危険人気補正": 0,
        "軸スコア": 0,
        "最終軸スコア": 0,
        "穴スコア": 0,
        "馬柱評価": [],
        "加点理由": []
    }

def extract_odds_popularity(text):
    odds = None
    popularity = None

    pop_match = re.search(r"(\d+)\s*人気", text)
    if pop_match:
        popularity = int(pop_match.group(1))

    odds_match = re.search(r"(\d+\.\d+)", text)
    if odds_match:
        odds = float(odds_match.group(1))

    if popularity is None:
        nums = re.findall(r"\b\d+\b", text)
        decimals = re.findall(r"\d+\.\d+", text)

        if decimals and nums:
            try:
                last_num = int(nums[-1])
                if 1 <= last_num <= 30:
                    popularity = last_num
            except:
                pass

    return odds, popularity

def parse_info_line(info):
    jockey = ""
    trainer = ""
    parts = info.split()

    if len(parts) >= 4 and re.match(r"^[牡牝セ]\d+", parts[0]):
        jockey = parts[2]
        trainer = parts[3]

    return jockey, trainer

def parse_pc_style(lines):
    horses = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not re.match(r"^\d+\s+\d+$", line):
            i += 1
            continue

        nums = line.split()
        frame_no = int(nums[0])
        horse_no = int(nums[1])

        j = i + 1

        while j < len(lines) and lines[j] == "--":
            j += 1

        if j >= len(lines):
            i += 1
            continue

        horse_name = lines[j].strip()

        if (
            not horse_name
            or horse_name == "--"
            or horse_name == "編集"
            or re.fullmatch(r"\d+", horse_name)
            or "人気" in horse_name
            or re.search(r"\d+\.\d+", horse_name)
        ):
            i += 1
            continue

        block = []
        k = j + 1

        while k < len(lines):
            if re.match(r"^\d+\s+\d+$", lines[k]):
                break
            block.append(lines[k])
            k += 1

        block_text = " ".join(block)

        odds, popularity = extract_odds_popularity(block_text)

        jockey = ""
        trainer = ""

        for row in block:
            row_jockey, row_trainer = parse_info_line(row)
            if row_jockey:
                jockey = row_jockey
            if row_trainer:
                trainer = row_trainer

        horses.append(
            make_horse(
                frame_no,
                horse_no,
                horse_name,
                popularity,
                odds,
                jockey,
                trainer
            )
        )

        i = k

    return horses

def parse_smartphone_style(lines):
    horses = []
    i = 0

    while i < len(lines):
        if not re.fullmatch(r"\d+", lines[i]):
            i += 1
            continue

        horse_no = int(lines[i])

        found_db = False

        for j in range(i + 1, min(i + 12, len(lines))):
            if "のデータベース" in lines[j]:
                horse_name = lines[j - 1].replace("  ", "").strip()
                info_line = lines[j]
                found_db = True
                break

        if not found_db:
            i += 1
            continue

        if not horse_name or horse_name == "編集" or re.fullmatch(r"\d+", horse_name):
            i += 1
            continue

        search_block = " ".join(lines[i:min(i + 30, len(lines))])
        odds, popularity = extract_odds_popularity(search_block)

        db_removed = info_line.replace(f"{horse_name}のデータベース", "").strip()
        db_removed = re.sub(r"^[牡牝セ]\d+\s+", "", db_removed)
        db_removed = re.sub(r"\d+\.\d+$", "", db_removed).strip()

        jockey = db_removed.split()[0] if db_removed else ""
        trainer = ""
        frame_no = (horse_no + 1) // 2

        horses.append(
            make_horse(
                frame_no,
                horse_no,
                horse_name,
                popularity,
                odds,
                jockey,
                trainer
            )
        )

        i += 1

    return horses

def parse_race_table(text):
    lines = clean_lines(text)

    candidates = []

    try:
        if any("のデータベース" in line for line in lines):
            candidates.append(parse_smartphone_style(lines))
    except:
        pass

    try:
        candidates.append(parse_pc_style(lines))
    except:
        pass

    best = []

    for c in candidates:
        if not c:
            continue

        valid_name_count = sum(
            1 for h in c
            if h["馬名"]
            and h["馬名"] != "--"
            and h["馬名"] != "編集"
            and not re.fullmatch(r"\d+", h["馬名"])
        )

        pop_count = sum(1 for h in c if h["人気"] is not None)
        score = valid_name_count * 10 + pop_count

        best_score = -1
        if best:
            best_score = (
                sum(1 for h in best if h["馬名"]) * 10
                + sum(1 for h in best if h["人気"] is not None)
            )

        if score > best_score:
            best = c

    unique = {}
    for h in best:
        if h.get("馬番") is not None and h.get("馬名"):
            unique[h["馬番"]] = h

    return sorted(list(unique.values()), key=lambda x: x["馬番"])

def normalize_style(style):
    convert = {
        "逃": "逃げ",
        "先": "先行",
        "差": "差し",
        "追": "追込",
        "逃げ": "逃げ",
        "先行": "先行",
        "差し": "差し",
        "追込": "追込",
    }
    return convert.get(style, style)

def parse_running_style(text):
    styles = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            styles[int(match.group(1))] = {
                "style": normalize_style(match.group(2).strip()),
                "win_rate": None,
                "place_rate": None
            }

    return styles

def style_score(win_rate, place_rate):
    score = 0

    if place_rate is not None:
        if place_rate >= 50:
            score += 15
        elif place_rate >= 40:
            score += 10
        elif place_rate >= 30:
            score += 5

    if win_rate is not None:
        if win_rate >= 20:
            score += 5
        elif win_rate >= 10:
            score += 3

    return score

def parse_style_graph(text):
    styles = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    i = 0

    while i < len(lines):
        line = lines[i]

        if re.match(r"^\d+$", line) and i + 2 < len(lines) and lines[i + 1] == "--":
            horse_no = int(line)
            data_line = lines[i + 2]

            match = re.match(r"^(逃|先|差|追)\s+(.+)", data_line)
            if match:
                style = normalize_style(match.group(1))
                percents = [int(x) for x in re.findall(r"(\d+)%", data_line)]
                win_rate = percents[0] if len(percents) >= 1 else None
                place_rate = percents[2] if len(percents) >= 3 else None

                styles[horse_no] = {
                    "style": style,
                    "win_rate": win_rate,
                    "place_rate": place_rate
                }

                i += 3
                continue

        if re.match(r"^\d+$", line) and i + 1 < len(lines):
            horse_no = int(line)
            data_line = lines[i + 1]

            match = re.match(r"^(逃|先|差|追)\s+(.+)", data_line)
            if match:
                style = normalize_style(match.group(1))
                percents = [int(x) for x in re.findall(r"(\d+)%", data_line)]
                win_rate = percents[0] if len(percents) >= 1 else None
                place_rate = percents[2] if len(percents) >= 3 else None

                styles[horse_no] = {
                    "style": style,
                    "win_rate": win_rate,
                    "place_rate": place_rate
                }

                i += 2
                continue

        match = re.match(r"^(\d+)\s+(逃|先|差|追)\s+(.+)", line)
        if match:
            horse_no = int(match.group(1))
            style = normalize_style(match.group(2))
            percents = [int(x) for x in re.findall(r"(\d+)%", line)]
            win_rate = percents[0] if len(percents) >= 1 else None
            place_rate = percents[2] if len(percents) >= 3 else None

            styles[horse_no] = {
                "style": style,
                "win_rate": win_rate,
                "place_rate": place_rate
            }

        i += 1

    return styles

def parse_pace(text):
    pace = {}
    current_horse = None
    wait_after_mae = False
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        if re.fullmatch(r"\d+", line):
            current_horse = int(line)
            pace.setdefault(current_horse, [])
            wait_after_mae = False
            continue

        if current_horse is None:
            continue

        if line == "前":
            wait_after_mae = True
            continue

        if line == "----":
            continue

        m1 = re.search(r"-\s*(\d+)\s+(\d+)\s+(\d+)", line)
        if m1:
            pace[current_horse].append((int(m1.group(1)), int(m1.group(2)), int(m1.group(3))))
            wait_after_mae = False
            continue

        if wait_after_mae:
            nums = re.findall(r"\d+", line)

            if len(nums) >= 4:
                pace[current_horse].append((int(nums[-3]), int(nums[-2]), int(nums[-1])))
                wait_after_mae = False
                continue

            if len(nums) == 3:
                pace[current_horse].append((int(nums[0]), int(nums[1]), int(nums[2])))
                wait_after_mae = False
                continue

        m2 = re.search(r"-(\d{3,})$", line)
        if m2:
            nums = m2.group(1)

            try:
                if len(nums) == 3:
                    pos = (int(nums[0]), int(nums[1]), int(nums[2]))
                elif len(nums) == 4:
                    pos = (int(nums[0]), int(nums[1]), int(nums[2:]))
                elif len(nums) == 5:
                    pos = (int(nums[0]), int(nums[1:3]), int(nums[3:]))
                elif len(nums) == 6:
                    pos = (int(nums[:2]), int(nums[2:4]), int(nums[4:]))
                else:
                    continue

                pace[current_horse].append(pos)
            except:
                pass

    return pace

def parse_form_features(text):
    features = {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    horse_blocks = {}
    current_horse = None

    def is_pc_horse_start(idx):
        return bool(re.match(r"^\d+\s+\d+\s*$", lines[idx]))

    def is_smartphone_horse_start(idx):
        if not re.fullmatch(r"\d+", lines[idx]):
            return False

        # スマホ版は「馬番 → 馬名 → -- → 馬名のデータベース」になりやすい
        lookahead = lines[idx + 1:idx + 8]
        return any("のデータベース" in x for x in lookahead)

    for i, line in enumerate(lines):
        pc_match = re.match(r"^\d+\s+(\d+)\s*$", line)

        if pc_match:
            horse_no = int(pc_match.group(1))
            current_horse = horse_no
            horse_blocks[current_horse] = []
            continue

        if is_smartphone_horse_start(i):
            horse_no = int(line)
            current_horse = horse_no
            horse_blocks[current_horse] = []
            continue

        if current_horse is not None:
            horse_blocks[current_horse].append(line)

    for horse_no, block in horse_blocks.items():
        races = []
        block_text = " ".join(block)

        long_rest = False
        if "半年休養" in block_text or "6ヵ月休養" in block_text or "6ヶ月休養" in block_text:
            long_rest = True

        rest_match = re.search(r"(\d+)ヵ月", block_text)
        if rest_match and int(rest_match.group(1)) >= 6:
            long_rest = True

        for i, line in enumerate(block):
            # 地方スマホ例：
            # 06/02  船橋 1R
            # 次の数行後に着順だけの行が来る
            local_date = re.match(r"^\d{2}/\d{2}\s+", line)

            # 中央PC例：
            # 2026.06.07 東京5
            jra_date = re.match(r"^\d{4}\.\d{2}\.\d{2}\s+.+?(\d+|中)$", line)

            if not local_date and not jra_date:
                continue

            race_lines = block[i:i + 16]
            race_text = " ".join(race_lines)

            finish = None

            if jra_date:
                finish_raw = jra_date.group(1)
                if finish_raw.isdigit():
                    finish = int(finish_raw)

            if local_date:
                # 日付行の後、最初に出てくる単独数字を着順扱い
                for r in race_lines[1:8]:
                    if re.fullmatch(r"\d+", r):
                        finish = int(r)
                        break

            position_nums = []

            for r in race_lines:
                # 地方例：- 1 1 1
                m_local = re.search(r"-\s*(\d+)\s+(\d+)\s+(\d+)", r)
                if m_local:
                    position_nums = [
                        int(m_local.group(1)),
                        int(m_local.group(2)),
                        int(m_local.group(3)),
                    ]
                    break

                # 中央例：4-5 (39.0)、3-3-4-3 (39.0)
                m_jra = re.search(r"(\d+(?:-\d+)+)\s+\(", r)
                if m_jra:
                    position_nums = [int(x) for x in m_jra.group(1).split("-")]
                    break

                # 中央芝1000など：1 (34.2)
                m_single = re.search(r"^\s*(\d+)\s+\(", r)
                if m_single:
                    position_nums = [int(m_single.group(1))]
                    break

            margin = None

            for r in race_lines:
                # 相手名(0.3) のような着差
                if "kg" in r or "頭" in r:
                    continue

                margin_match = re.search(r"\((\d+\.\d+)\)\s*$", r)
                if margin_match:
                    margin = float(margin_match.group(1))

            races.append({
                "finish": finish,
                "positions": position_nums,
                "margin": margin
            })

        recent3 = races[:3]
        first_race = races[0] if races else None

        front_last = False
        close_last = False
        big_loss_last = False

        if first_race:
            if first_race["positions"]:
                if first_race["positions"][-1] <= 3:
                    front_last = True

            if first_race["margin"] is not None:
                if first_race["margin"] <= 0.5:
                    close_last = True
                if first_race["margin"] >= 1.0:
                    big_loss_last = True

        in_money_count = sum(
            1 for r in recent3
            if r["finish"] is not None and r["finish"] <= 3
        )

        double_digit_count = sum(
            1 for r in recent3
            if r["finish"] is not None and r["finish"] >= 10
        )

        front_count_5 = sum(
            1 for r in races[:5]
            if r["positions"] and r["positions"][-1] <= 3
        )

        features[horse_no] = {
            "近走着順": [r["finish"] for r in races if r["finish"] is not None][:5],
            "前走4角3番手以内": front_last,
            "前走0.5秒差以内": close_last,
            "近3走馬券内2回以上": in_money_count >= 2,
            "半年以上休養": long_rest,
            "前走1秒以上負け": big_loss_last,
            "近3走二桁着順2回以上": double_digit_count >= 2,
            "近5走4角3番手以内2回以上": front_count_5 >= 2,
        }

    return features


# ==============================
# Ver.4 採点システム
# ==============================

AXIS_SECTION_POINTS = {
    "データ上位馬3頭": 5,
    "このコースが得意な馬": 15,
    "この距離が得意な馬": 12,
    "この競馬場が得意な馬": 10,
    "今回の馬場状態が得意な馬": 10,
    "今回のレース間隔で実績がある馬": 8,
    "今回の調教評価で実績がある馬": 8,
    "今回の厩舎コメント評価で実績がある馬": 5,
    "このコースが得意な騎手": 5,
    "このコースが得意な調教師": 5,
    "このコースに実績がある種牡馬": 4,
    "このコースに実績がある母父": 3,
}

HOLE_SECTION_POINTS = {
    "このコースが得意な馬": 10,
    "この距離が得意な馬": 10,
    "この競馬場が得意な馬": 8,
    "今回の馬場状態が得意な馬": 8,
}

SPECIAL_SECTIONS = [
    "このコースで有利な枠順",
    "このコースで有利な脚質",
    "好調枠順",
]

SECTION_NAMES = set(AXIS_SECTION_POINTS) | set(HOLE_SECTION_POINTS) | set(SPECIAL_SECTIONS)


def get_section_items(text):
    sections = {}
    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line in SECTION_NAMES:
            current_section = line
            sections[current_section] = []
            continue

        if current_section:
            sections[current_section].append(line)

    return sections


def set_category(horses):
    popular = []
    hole = []
    big_hole = []

    hole_max_popularity = 10 if len(horses) >= 15 else 9

    for h in horses:
        if h["人気"] is None:
            h["カテゴリ"] = "人気不明"
            big_hole.append(h)
        elif h["人気"] <= 3:
            h["カテゴリ"] = "人気馬"
            popular.append(h)
        elif h["人気"] <= hole_max_popularity:
            h["カテゴリ"] = "穴馬"
            hole.append(h)
        else:
            h["カテゴリ"] = "大穴馬"
            big_hole.append(h)

    return popular, hole, big_hole


def add_reason(horse, key, text):
    horse.setdefault(key, [])
    horse[key].append(text)


def has_reason(horse, keyword):
    return any(keyword in reason for reason in horse.get("加点理由", []))


def apply_section_scores(horses, sections):
    horse_map = {h["馬番"]: h for h in horses}

    for section, lines in sections.items():
        axis_point = AXIS_SECTION_POINTS.get(section, 0)
        hole_point = HOLE_SECTION_POINTS.get(section, 0)

        if axis_point == 0 and hole_point == 0:
            continue

        for line in lines:
            m = re.match(r"^(\d+)", line)
            if not m:
                continue

            horse_no = int(m.group(1))
            h = horse_map.get(horse_no)
            if not h:
                continue

            if axis_point:
                h["軸スコア"] += axis_point
                h["点数"] += axis_point
                h["加点理由"].append(f"軸:{section} +{axis_point}")

            if hole_point:
                h["穴スコア"] += hole_point
                h["馬柱評価"].append(f"穴:{section} +{hole_point}")


def apply_jockey_trainer_frame_style_scores(horses, sections):
    good_frames = []
    for line in sections.get("このコースで有利な枠順", []) + sections.get("好調枠順", []):
        for n in re.findall(r"\d+", line):
            good_frames.append(int(n))

    good_style_text = " ".join(sections.get("このコースで有利な脚質", []))
    good_jockey_text = " ".join(sections.get("このコースが得意な騎手", []))
    good_trainer_text = " ".join(sections.get("このコースが得意な調教師", []))

    for h in horses:
        if h["枠番"] in good_frames:
            h["軸スコア"] += 4
            h["点数"] += 4
            h["加点理由"].append(f"軸:有利枠順({h['枠番']}枠) +4")

        if h.get("脚質") and h["脚質"] in good_style_text:
            h["軸スコア"] += 5
            h["点数"] += 5
            h["加点理由"].append(f"軸:有利脚質({h['脚質']}) +5")

        if h.get("騎手") and h["騎手"] in good_jockey_text:
            h["軸スコア"] += 5
            h["点数"] += 5
            h["加点理由"].append(f"軸:得意騎手({h['騎手']}) +5")

        trainer_name = h.get("調教師", "")
        for area in ["栗東", "美浦", "大井", "浦和", "北海道", "兵庫", "船橋", "川崎", "笠松"]:
            trainer_name = trainer_name.replace(area, "")

        if trainer_name and trainer_name in good_trainer_text:
            h["軸スコア"] += 5
            h["点数"] += 5
            h["加点理由"].append(f"軸:得意調教師({h['調教師']}) +5")


def apply_running_style(horses, running_style_text, style_graph_text):
    styles = parse_running_style(running_style_text)
    graph_styles = parse_style_graph(style_graph_text)
    for horse_no, data in graph_styles.items():
        styles[horse_no] = data

    for h in horses:
        data = styles.get(h["馬番"])
        if not data:
            continue

        h["脚質"] = data["style"]
        h["脚質勝率"] = data.get("win_rate")
        h["脚質複勝率"] = data.get("place_rate")

        # 脚質成績は軸の補助。減点はしない。
        score = style_score(h["脚質勝率"], h["脚質複勝率"])
        if score > 0:
            h["軸スコア"] += score
            h["点数"] += score
            h["加点理由"].append(
                f"軸:脚質成績({h['脚質']} 勝率{h['脚質勝率']}% 複勝率{h['脚質複勝率']}%) +{score}"
            )

        # 穴馬は逃げ・先行を明確に評価
        if h["脚質"] == "逃げ":
            h["穴スコア"] += 8
            h["馬柱評価"].append("穴:逃げ脚質 +8")
        elif h["脚質"] == "先行":
            h["穴スコア"] += 6
            h["馬柱評価"].append("穴:先行脚質 +6")


def apply_form_scores(horses, form_features):
    for h in horses:
        f = form_features.get(h["馬番"], {})

        # 軸向け
        if f.get("前走0.5秒差以内"):
            h["軸スコア"] += 5
            h["点数"] += 5
            h["加点理由"].append("軸:前走0.5秒差以内 +5")

        if f.get("前走4角3番手以内"):
            h["軸スコア"] += 8
            h["点数"] += 8
            h["加点理由"].append("軸:前走4角3番手以内 +8")

        # 穴向け
        if f.get("前走0.5秒差以内"):
            h["穴スコア"] += 8
            h["馬柱評価"].append("穴:前走0.5秒差以内 +8")

        if f.get("前走4角3番手以内"):
            h["穴スコア"] += 15
            h["馬柱評価"].append("穴:前走4角3番手以内 +15")

        if f.get("近5走4角3番手以内2回以上"):
            h["穴スコア"] += 12
            h["馬柱評価"].append("穴:近5走4角3番手以内2回以上 +12")

        if f.get("近3走馬券内2回以上"):
            h["穴スコア"] += 12
            h["馬柱評価"].append("穴:近3走馬券内2回以上 +12")

        # 悪材料は減点せず注意表示だけ
        cautions = []
        if f.get("前走1秒以上負け"):
            cautions.append("注意:前走1秒以上負け")
        if f.get("半年以上休養"):
            cautions.append("注意:半年以上休養")
        if f.get("近3走二桁着順2回以上"):
            cautions.append("注意:近3走二桁着順2回以上")
        if cautions:
            h["馬柱評価"].extend(cautions)


def apply_popularity_scores(horses, track_condition):
    for h in horses:
        pop = h.get("人気")
        if pop is None:
            continue

        # 軸は上位人気を一律評価。1〜3番人気の差をつけすぎない。
        if 1 <= pop <= 3:
            h["軸スコア"] += 5
            h["点数"] += 5
            h["加点理由"].append(f"軸:人気補正({pop}番人気) +5")

        # 穴は人気以上に走りそうなゾーンを評価
        if 4 <= pop <= 6:
            h["穴スコア"] += 10
            h["馬柱評価"].append("穴:4〜6番人気 +10")
        elif 7 <= pop <= 9:
            h["穴スコア"] += 8
            h["馬柱評価"].append("穴:7〜9番人気 +8")
        elif 10 <= pop <= 12:
            h["穴スコア"] += 5
            h["馬柱評価"].append("穴:10〜12番人気 +5")


def apply_track_condition_scores(horses, track_condition, form_features):
    for h in horses:
        f = form_features.get(h["馬番"], {})

        if track_condition == "稍重":
            if h["脚質"] == "逃げ":
                h["穴スコア"] += 3
                h["馬柱評価"].append("馬場:稍重逃げ +3")
            elif h["脚質"] == "先行":
                h["穴スコア"] += 2
                h["馬柱評価"].append("馬場:稍重先行 +2")

        elif track_condition == "重":
            if h["脚質"] == "逃げ":
                h["軸スコア"] += 4
                h["穴スコア"] += 6
                h["点数"] += 4
                h["加点理由"].append("馬場:重逃げ +4")
                h["馬柱評価"].append("馬場:重逃げ +6")
            elif h["脚質"] == "先行":
                h["軸スコア"] += 3
                h["穴スコア"] += 4
                h["点数"] += 3
                h["加点理由"].append("馬場:重先行 +3")
                h["馬柱評価"].append("馬場:重先行 +4")

        elif track_condition == "不良":
            if h["脚質"] == "逃げ":
                h["軸スコア"] += 8
                h["穴スコア"] += 15
                h["点数"] += 8
                h["加点理由"].append("馬場:不良逃げ +8")
                h["馬柱評価"].append("馬場:不良逃げ +15")
            elif h["脚質"] == "先行":
                h["軸スコア"] += 6
                h["穴スコア"] += 10
                h["点数"] += 6
                h["加点理由"].append("馬場:不良先行 +6")
                h["馬柱評価"].append("馬場:不良先行 +10")

            if f.get("前走4角3番手以内"):
                h["穴スコア"] += 10
                h["馬柱評価"].append("馬場:不良前走4角3番手以内 +10")

            if f.get("近5走4角3番手以内2回以上"):
                h["穴スコア"] += 8
                h["馬柱評価"].append("馬場:不良近5走前目2回以上 +8")


def add_points(horses, analysis_text, running_style_text, style_graph_text, pace_text, track_condition):
    # Ver.4では複勝点・安定指数・期待値指数は使わず、軸スコアと穴スコアに集約。
    set_category(horses)
    sections = get_section_items(analysis_text)
    form_features = parse_form_features(pace_text)

    apply_running_style(horses, running_style_text, style_graph_text)
    apply_section_scores(horses, sections)
    apply_jockey_trainer_frame_style_scores(horses, sections)
    apply_form_scores(horses, form_features)
    apply_popularity_scores(horses, track_condition)
    apply_track_condition_scores(horses, track_condition, form_features)

    for h in horses:
        # 画面表示互換用。複勝点は軸スコアの簡易版として残す。
        h["複勝点"] = h["軸スコア"]
        h["安定指数"] = 0
        h["期待値指数"] = 0
        h["危険人気補正"] = 0
        h["最終軸スコア"] = h["軸スコア"]
        h["点数"] = h["軸スコア"] + h["穴スコア"]

    return horses


def axis_candidates_by_track(horses, track_condition):
    if track_condition == "不良":
        return [h for h in horses if h["人気"] is not None and h["人気"] <= 5]
    return [h for h in horses if h["人気"] is not None and h["人気"] <= 3]


def hole_candidates_by_track(horses, track_condition, axes=None):
    axes = axes or []
    axis_numbers = {h["馬番"] for h in axes}

    if track_condition == "不良":
        candidates = [
            h for h in horses
            if h["人気"] is not None
            and 4 <= h["人気"] <= 12
            and h["馬番"] not in axis_numbers
        ]
    else:
        max_pop = 10 if len(horses) >= 15 else 9
        candidates = [
            h for h in horses
            if h["人気"] is not None
            and 4 <= h["人気"] <= max_pop
            and h["馬番"] not in axis_numbers
        ]

    return candidates


def make_prediction(horses):
    axes = sorted(horses, key=lambda x: x["軸スコア"], reverse=True)[:1]
    axis = axes[0] if axes else None
    axis_no = axis["馬番"] if axis else None

    second_round = sorted(
        [h for h in horses if h["馬番"] != axis_no],
        key=lambda x: (x["軸スコア"] * 0.65 + x["穴スコア"] * 0.35),
        reverse=True
    )[:3]

    third_round = sorted(
        [h for h in horses if h["馬番"] != axis_no],
        key=lambda x: (x["軸スコア"] * 0.45 + x["穴スコア"] * 0.55),
        reverse=True
    )[:6]

    cut_horses = [h for h in horses if h != axis and h not in third_round]
    return axis, second_round, third_round, cut_horses, "normal", []


def make_tickets(axis, second_round, third_round):
    tickets = []
    if axis is None:
        return tickets

    for second, third in product(second_round, third_round):
        if axis["馬番"] != second["馬番"] and axis["馬番"] != third["馬番"] and second["馬番"] != third["馬番"]:
            tickets.append((axis, second, third))

    return tickets


def make_wide_tickets(second_round):
    return list(combinations(second_round, 2)) if len(second_round) >= 2 else []


def ticket_score(ticket, main_axis, sub_axis, selected_holes):
    nums = set(ticket)
    hole_nums = [h["馬番"] for h in selected_holes]
    h1 = hole_nums[0] if len(hole_nums) >= 1 else None
    h2 = hole_nums[1] if len(hole_nums) >= 2 else None

    horse_map = {h["馬番"]: h for h in [main_axis, sub_axis] + selected_holes}
    score = 0
    for n in nums:
        h = horse_map.get(n)
        if not h:
            continue
        score += h["軸スコア"] * 0.55 + h["穴スコア"] * 0.45

    # 組み合わせシナリオ補正
    if main_axis["馬番"] in nums and sub_axis["馬番"] in nums:
        score += 15  # 安定型

    if main_axis["馬番"] in nums and h1 in nums and h2 in nums:
        score += 12  # 配当型

    if sub_axis["馬番"] in nums and h1 in nums and h2 in nums:
        score += 10  # 荒れ型

    if h1 in nums:
        score += 5

    return score


def make_sanrenpuku_16_tickets(horses, track_condition):
    axis_candidates = axis_candidates_by_track(horses, track_condition)
    axis_sorted = sorted(axis_candidates, key=lambda x: x["軸スコア"], reverse=True)

    if len(axis_sorted) < 2:
        return [], None

    main_axis = axis_sorted[0]
    sub_axis = axis_sorted[1]

    hole_candidates = hole_candidates_by_track(horses, track_condition, [main_axis, sub_axis])
    hole_sorted = sorted(hole_candidates, key=lambda x: x["穴スコア"], reverse=True)

    hole_count = 5 if len(horses) >= 16 else 4

    if len(hole_sorted) < hole_count:
        # 足りない時は人気不明や大穴も、穴スコア順で補充する
        extra = [h for h in horses if h["馬番"] not in {main_axis["馬番"], sub_axis["馬番"]} and h not in hole_sorted]
        hole_sorted += sorted(extra, key=lambda x: x["穴スコア"], reverse=True)

    if len(hole_sorted) < hole_count:
        return [], None

    selected_holes = hole_sorted[:hole_count]

    tickets = []
    group1 = [sub_axis] + selected_holes

    for a, b in combinations(group1, 2):
        tickets.append(tuple(sorted([main_axis["馬番"], a["馬番"], b["馬番"]])))

    for a, b in combinations(selected_holes, 2):
        tickets.append(tuple(sorted([sub_axis["馬番"], a["馬番"], b["馬番"]])))

    tickets = list(dict.fromkeys(tickets))

    scored = sorted(
        [(t, ticket_score(t, main_axis, sub_axis, selected_holes)) for t in tickets],
        key=lambda x: x[1],
        reverse=True
    )

    info = {
        "main_axis": main_axis,
        "sub_axis": sub_axis,
        "selected_holes": selected_holes,
        "ticket_scores": scored,
    }

    return tickets, info


def make_sanrenpuku_select_tickets(sanrenpuku16_info):
    if not sanrenpuku16_info:
        return [], []

    scored = sanrenpuku16_info.get("ticket_scores", [])
    select3 = [t for t, s in scored[:3]]
    select5 = [t for t, s in scored[:5]]
    return select3, select5


def judge_confidence(horses, axis, second_round, axis_mode):
    if axis is None:
        return "★☆☆☆☆", "見送り"

    sorted_axes = sorted(horses, key=lambda x: x["軸スコア"], reverse=True)
    top = sorted_axes[0]["軸スコア"] if sorted_axes else 0
    second = sorted_axes[1]["軸スコア"] if len(sorted_axes) >= 2 else 0
    gap = top - second

    if top >= 70 and gap >= 15:
        return "★★★★★", "勝負"
    elif top >= 55:
        return "★★★★☆", "通常"
    elif top >= 40:
        return "★★★☆☆", "通常"
    elif top >= 25:
        return "★★☆☆☆", "見送り寄り"
    else:
        return "★☆☆☆☆", "見送り"


if st.button("予想開始"):
    horses = parse_race_table(race_table)

    if not horses:
        st.error("出走表を読み取れませんでした。PC版・スマホ版どちらでも、出走表部分を少し広めにコピーして貼ってください。")
    else:
        horses = add_points(horses, analysis, running_style_text, style_graph_text, pace_text, track_condition)

        axis, second_round, third_round, cut_horses, axis_mode, hole_recommendations = make_prediction(horses)

        tickets = make_tickets(axis, second_round, third_round)
        wide_tickets = make_wide_tickets(second_round)
        sanrenpuku16_tickets, sanrenpuku16_info = make_sanrenpuku_16_tickets(horses, track_condition)
        select3_tickets, select5_tickets = make_sanrenpuku_select_tickets(sanrenpuku16_info)
        confidence, recommendation = judge_confidence(horses, axis, second_round, axis_mode)

        st.success(f"{len(horses)}頭を読み取りました。")
        st.write(f"馬場状態：{track_condition}")
        st.caption("Ver.4：軸スコア・穴スコア・買い目相性スコアの3本設計。減点ではなく加点中心。")

        st.subheader("馬ごとの評価点")

        for h in sorted(horses, key=lambda x: x["軸スコア"], reverse=True):
            odds_text = f"｜オッズ {h['オッズ']}" if h["オッズ"] is not None else ""
            style_text = f"｜脚質 {h['脚質']}" if h["脚質"] else ""

            st.write(
                f"{h['馬番']} {h['馬名']}｜"
                f"{h['人気']}番人気｜"
                f"{h['カテゴリ']}｜"
                f"軸{h['軸スコア']}点｜"
                f"穴{h['穴スコア']}点｜"
                f"総合{h['点数']}点"
                f"{odds_text}{style_text}"
            )

            if h.get("加点理由"):
                st.caption("軸理由: " + " / ".join(h["加点理由"]))

            if h.get("馬柱評価"):
                st.caption("穴理由: " + " / ".join(h["馬柱評価"]))

        st.subheader("予想結果")

        st.info(
            f"信頼度：{confidence}\n\n"
            f"判定：{recommendation}"
        )

        if axis:
            st.success(
                f"◎ 軸馬：{axis['馬番']} {axis['馬名']}｜"
                f"軸{axis['軸スコア']}点｜穴{axis['穴スコア']}点"
            )

        st.write("### 2巡目")
        for h in second_round:
            st.write(f"{h['馬番']} {h['馬名']}｜軸{h['軸スコア']}点｜穴{h['穴スコア']}点")

        st.write("### 3巡目")
        for h in third_round:
            st.write(f"{h['馬番']} {h['馬名']}｜軸{h['軸スコア']}点｜穴{h['穴スコア']}点")

        st.write("### 消し馬")
        for h in cut_horses:
            st.write(
                f"{h['馬番']} {h['馬名']}｜"
                f"{h['人気']}番人気｜"
                f"軸{h['軸スコア']}点｜穴{h['穴スコア']}点"
            )

        st.subheader("3連複標準ルール")

        if sanrenpuku16_info:
            main_axis = sanrenpuku16_info["main_axis"]
            sub_axis = sanrenpuku16_info["sub_axis"]
            selected_holes = sanrenpuku16_info["selected_holes"]

            st.write(
                f"人気軸A：{main_axis['馬番']} {main_axis['馬名']}｜"
                f"軸{main_axis['軸スコア']}点｜穴{main_axis['穴スコア']}点"
            )

            st.write(
                f"人気軸B：{sub_axis['馬番']} {sub_axis['馬名']}｜"
                f"軸{sub_axis['軸スコア']}点｜穴{sub_axis['穴スコア']}点"
            )

            st.write("穴馬採用4頭")
            st.write(
                " / ".join(
                    f"{h['馬番']} {h['馬名']} (穴{h['穴スコア']})" for h in selected_holes
                )
            )

            st.code(
                " / ".join(
                    f"{a}-{b}-{c}" for a, b, c in sanrenpuku16_tickets
                )
            )

            st.write(f"3連複点数：{len(sanrenpuku16_tickets)}点")

            with st.expander("買い目スコア詳細"):
                for t, s in sanrenpuku16_info.get("ticket_scores", []):
                    st.write(f"{t[0]}-{t[1]}-{t[2]}｜買い目スコア {round(s, 1)}")

            st.subheader("3連複 厳選3点・5点")

            if select3_tickets:
                st.write("### 厳選3点")
                st.code(" / ".join(f"{a}-{b}-{c}" for a, b, c in select3_tickets))
                st.write(f"厳選3点：{len(select3_tickets)}点")

            if select5_tickets:
                st.write("### 厳選5点")
                st.code(" / ".join(f"{a}-{b}-{c}" for a, b, c in select5_tickets))
                st.write(f"厳選5点：{len(select5_tickets)}点")
        else:
            st.warning("3連複16点ルールを作成できませんでした。軸候補または穴候補が不足しています。")

        st.subheader("3連単フォーメーション")

        if axis:
            second_nums = ",".join(str(h["馬番"]) for h in second_round)
            third_nums = ",".join(str(h["馬番"]) for h in third_round)
            st.code(f"{axis['馬番']} → {second_nums} → {third_nums}")

        st.write(f"3連単点数：{len(tickets)}点")

        st.subheader("ワイド（2巡目BOX）")

        if wide_tickets:
            wide_text = [f"{t[0]['馬番']}-{t[1]['馬番']}" for t in wide_tickets]
            st.code(" / ".join(wide_text))
            st.write(f"ワイド点数：{len(wide_tickets)}点")

        with st.expander("3連単買い目一覧"):
            for t in tickets:
                st.write(f"{t[0]['馬番']} → {t[1]['馬番']} → {t[2]['馬番']}")
