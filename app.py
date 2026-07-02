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

        features[horse_no] = {
            "近走着順": [r["finish"] for r in races if r["finish"] is not None][:5],
            "前走4角3番手以内": front_last,
            "前走0.5秒差以内": close_last,
            "近3走馬券内2回以上": in_money_count >= 2,
            "半年以上休養": long_rest,
            "前走1秒以上負け": big_loss_last,
            "近3走二桁着順2回以上": double_digit_count >= 2,
        }

    return features

def get_section_items(text):
    sections = {}
    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line in POINTS or line in ["このコースで有利な枠順", "このコースで有利な脚質"]:
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

    # 中央の多頭数想定：15頭以上なら10番人気まで穴馬扱い
    if len(horses) >= 15:
        hole_max_popularity = 10
    else:
        hole_max_popularity = 9

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

def has_reason(horse, keyword):
    return any(keyword in reason for reason in horse["加点理由"])

def calc_axis_score(horse):
    """
    3連複の人気軸2頭を選ぶための軸スコア。
    強い馬ではなく「3着以内に残りやすい馬」を重視する。
    """
    style_bonus = {
        "逃げ": 10,
        "先行": 7,
        "差し": -3,
        "追込": -5
    }.get(horse["脚質"], 0)

    base_score = (
        horse["点数"] * 0.35 +
        horse["複勝点"] * 0.30 +
        horse["安定指数"] * 0.20 +
        horse["期待値指数"] * 0.10 +
        horse["展開指数"] * 0.05 +
        style_bonus
    )

    return base_score


def calc_stability_score(feature):
    """
    過去走から安定指数を作る。
    減点過多で好走馬を消さないよう、マイナスは最大-15までに制限。
    """
    score = 0

    finishes = feature.get("近走着順", [])
    if not finishes:
        return 0

    total = len(finishes)
    in_3 = sum(1 for r in finishes if r is not None and r <= 3)
    in_5 = sum(1 for r in finishes if r is not None and r <= 5)
    out_10 = sum(1 for r in finishes if r is not None and r >= 10)

    fukusho_rate = in_3 / total
    board_rate = in_5 / total
    bad_rate = out_10 / total

    if fukusho_rate >= 0.6:
        score += 20
    elif fukusho_rate >= 0.4:
        score += 10

    if board_rate >= 0.8:
        score += 15
    elif board_rate >= 0.6:
        score += 8

    # 大敗率の減点は軽め
    if bad_rate >= 0.4:
        score -= 10
    elif bad_rate >= 0.2:
        score -= 5

    latest = finishes[0]
    if latest is not None:
        if latest <= 3:
            score += 10
        elif latest <= 5:
            score += 5
        elif latest >= 10:
            score -= 5

    if feature.get("前走0.5秒差以内"):
        score += 5

    if feature.get("前走1秒以上負け"):
        score -= 3

    if feature.get("半年以上休養"):
        score -= 3

    # 最終的に減点過多を防ぐ
    if score < -15:
        score = -15

    return score


def calc_value_score(total_rank, popularity_rank):
    """
    期待値指数。
    総合評価順位より人気が低い馬は妙味あり、人気先行馬は軽く減点。
    ※減点過多で好走馬を消さないよう、マイナス側は最大-10に抑える。
    """
    if popularity_rank is None:
        return 0

    gap = popularity_rank - total_rank

    if gap >= 5:
        return 25
    elif gap >= 3:
        return 15
    elif gap >= 1:
        return 8
    elif gap <= -5:
        return -10
    elif gap <= -3:
        return -5
    elif gap <= -1:
        return -3
    return 0


def add_axis_extra_scores(horses, form_features):
    """
    安定指数・期待値指数・危険人気補正・最終軸スコアをまとめて計算。
    """
    for h in horses:
        feature = form_features.get(h["馬番"], {})
        h["安定指数"] = calc_stability_score(feature)

        if h["安定指数"] > 0:
            h["加点理由"].append(f"安定指数 +{h['安定指数']}")
        elif h["安定指数"] < 0:
            h["加点理由"].append(f"安定指数 {h['安定指数']}")

    # 総合点の順位を作る。点数が高いほど上位。
    sorted_by_total = sorted(horses, key=lambda x: x["点数"], reverse=True)
    total_rank_map = {}
    prev_score = None
    current_rank = 0

    for idx, h in enumerate(sorted_by_total, start=1):
        if h["点数"] != prev_score:
            current_rank = idx
            prev_score = h["点数"]
        total_rank_map[h["馬番"]] = current_rank

    for h in horses:
        total_rank = total_rank_map.get(h["馬番"], 99)
        h["期待値指数"] = calc_value_score(total_rank, h["人気"])

        if h["期待値指数"] > 0:
            h["加点理由"].append(f"期待値指数 +{h['期待値指数']}")
        elif h["期待値指数"] < 0:
            h["加点理由"].append(f"期待値指数 {h['期待値指数']}")

        danger = 0

        # 危険人気補正は軽めにする。
        # 以前のように-25以上沈めると、好走できる人気馬まで消えやすい。
        if h["人気"] is not None and h["人気"] <= 3:
            if h["複勝点"] < 10:
                danger -= 15
            elif h["複勝点"] < 15:
                danger -= 10
            elif h["複勝点"] < 20:
                danger -= 5

        if h["人気"] == 1 and h["複勝点"] < 10:
            danger -= 5

        if h["期待値指数"] <= -10:
            danger -= 5

        # 最大減点は-15まで
        if danger < -15:
            danger = -15

        h["危険人気補正"] = danger

        if danger < 0:
            h["加点理由"].append(f"危険人気補正 {danger}")

        h["軸スコア"] = calc_axis_score(h)
        h["最終軸スコア"] = h["軸スコア"] + h["危険人気補正"]

    return horses

def add_points(horses, analysis_text, running_style_text, style_graph_text, pace_text, track_condition):
    set_category(horses)

    horse_map = {h["馬番"]: h for h in horses}
    sections = get_section_items(analysis_text)

    for section, lines in sections.items():
        if section not in POINTS:
            continue

        for line in lines:
            match = re.match(r"^(\d+)", line)
            if match:
                horse_no = int(match.group(1))
                if horse_no in horse_map:
                    point = POINTS[section]
                    if point != 0:
                        horse_map[horse_no]["点数"] += point
                        horse_map[horse_no]["加点理由"].append(f"{section} +{point}")

    good_frames = []
    for line in sections.get("このコースで有利な枠順", []) + sections.get("好調枠順", []):
        nums = re.findall(r"\d+", line)
        for n in nums:
            good_frames.append(int(n))

    for h in horses:
        if h["枠番"] in good_frames:
            point = POINTS["好調枠順"]
            h["点数"] += point
            h["加点理由"].append(f"有利枠順({h['枠番']}枠) +{point}")

    good_jockey_text = " ".join(sections.get("このコースが得意な騎手", []))

    for h in horses:
        if h["騎手"] and h["騎手"] in good_jockey_text:
            point = POINTS["このコースが得意な騎手"]
            h["点数"] += point
            h["加点理由"].append(f"得意騎手({h['騎手']}) +{point}")

    good_trainer_text = " ".join(sections.get("このコースが得意な調教師", []))

    for h in horses:
        trainer_name = h["調教師"]
        for area in ["栗東", "美浦", "大井", "浦和", "北海道", "兵庫", "船橋", "川崎", "笠松"]:
            trainer_name = trainer_name.replace(area, "")

        if trainer_name and trainer_name in good_trainer_text:
            point = POINTS["このコースが得意な調教師"]
            h["点数"] += point
            h["加点理由"].append(f"得意調教師({h['調教師']}) +{point}")

    styles = parse_running_style(running_style_text)
    graph_styles = parse_style_graph(style_graph_text)

    for horse_no, data in graph_styles.items():
        styles[horse_no] = data

    for h in horses:
        if h["馬番"] in styles:
            data = styles[h["馬番"]]
            h["脚質"] = data["style"]
            h["脚質勝率"] = data.get("win_rate")
            h["脚質複勝率"] = data.get("place_rate")

            score = style_score(h["脚質勝率"], h["脚質複勝率"])
            if score > 0:
                h["点数"] += score
                h["加点理由"].append(
                    f"脚質成績({h['脚質']} 勝率{h['脚質勝率']}% 複勝率{h['脚質複勝率']}%) +{score}"
                )

    good_style_text = " ".join(sections.get("このコースで有利な脚質", []))

    for h in horses:
        if h["脚質"] and h["脚質"] in good_style_text:
            point = POINTS["有利脚質"]
            h["点数"] += point
            h["加点理由"].append(f"有利脚質({h['脚質']}) +{point}")

    pace_data = parse_pace(pace_text)
    escape_candidates = []

    for horse_no, runs in pace_data.items():
        if not runs:
            continue

        avg_first = sum(r[0] for r in runs) / len(runs)
        front_count = sum(1 for r in runs if r[0] <= 2)

        if avg_first <= 2.5 or front_count >= 2:
            escape_candidates.append(horse_no)

    candidate_count = len(escape_candidates)

    for h in horses:
        if candidate_count == 1:
            if h["馬番"] in escape_candidates:
                h["点数"] += 15
                h["展開指数"] += 15
                h["加点理由"].append("展開有利(単騎逃げ) +15")

        elif candidate_count == 2:
            if h["馬番"] in escape_candidates:
                h["点数"] += 8
                h["展開指数"] += 8
                h["加点理由"].append("展開有利(逃げ候補) +8")
            elif h["脚質"] == "先行":
                h["点数"] += 5
                h["展開指数"] += 5
                h["加点理由"].append("展開有利(先行) +5")

        elif candidate_count >= 3:
            if h["脚質"] == "差し":
                h["点数"] += 8
                h["展開指数"] += 8
                h["加点理由"].append("展開有利(差し) +8")
            elif h["脚質"] == "追込":
                h["点数"] += 5
                h["展開指数"] += 5
                h["加点理由"].append("展開有利(追込) +5")

    for h in horses:
        fuku_score = 0

        if has_reason(h, "この距離が得意な馬"):
            fuku_score += 12

        if has_reason(h, "この競馬場が得意な馬"):
            fuku_score += 12

        if has_reason(h, "今回の馬場状態が得意な馬"):
            fuku_score += 10

        if has_reason(h, "今回のレース間隔で実績がある馬"):
            fuku_score += 10

        if h["脚質複勝率"] is not None:
            if h["脚質複勝率"] >= 50:
                fuku_score += 15
            elif h["脚質複勝率"] >= 40:
                fuku_score += 10
            elif h["脚質複勝率"] >= 30:
                fuku_score += 5

        if h["カテゴリ"] == "穴馬":
            fuku_score += 5

        h["複勝点"] = fuku_score

    for h in horses:
        if h["人気"] == 1:
            h["点数"] += 8
            h["加点理由"].append("人気補正(1番人気) +8")
        elif h["人気"] == 2:
            h["点数"] += 6
            h["加点理由"].append("人気補正(2番人気) +6")
        elif h["人気"] == 3:
            h["点数"] += 4
            h["加点理由"].append("人気補正(3番人気) +4")
        elif h["人気"] is not None and 4 <= h["人気"] <= 6:
            h["点数"] += 2
            h["加点理由"].append("人気補正(4〜6番人気) +2")

        if h["カテゴリ"] == "穴馬" and h["複勝点"] >= 20:
            h["点数"] += 5
            h["加点理由"].append("妙味補正(穴馬×複勝点20以上) +5")

        if h["カテゴリ"] == "人気馬":
            if h["複勝点"] < 10:
                h["点数"] -= 10
                h["加点理由"].append("危険人気馬減点(複勝点10未満) -10")
            elif h["複勝点"] < 15:
                h["点数"] -= 5
                h["加点理由"].append("危険人気馬減点(複勝点15未満) -5")

        if h["脚質"] in ["差し", "追込"] and h["複勝点"] < 20:
            h["点数"] -= 5
            h["加点理由"].append("後方脚質減点(複勝点20未満) -5")

    # 馬場状態による脚質補正
    # 良・稍重は基本ロジックそのまま。
    # 重は逃げ先行を軽く強化。不良は人気縛り解除モードに合わせて前残りを強く見る。
    for h in horses:
        if track_condition == "不良":
            if h["脚質"] == "逃げ":
                h["点数"] += 10
                h["展開指数"] += 10
                h["加点理由"].append("不良馬場補正(逃げ) +10")
            elif h["脚質"] == "先行":
                h["点数"] += 7
                h["展開指数"] += 7
                h["加点理由"].append("不良馬場補正(先行) +7")
            elif h["脚質"] == "差し":
                h["点数"] -= 3
                h["加点理由"].append("不良馬場補正(差し) -3")
            elif h["脚質"] == "追込":
                h["点数"] -= 8
                h["加点理由"].append("不良馬場補正(追込) -8")

        elif track_condition == "重":
            if h["脚質"] == "逃げ":
                h["点数"] += 6
                h["展開指数"] += 6
                h["加点理由"].append("重馬場補正(逃げ) +6")
            elif h["脚質"] == "先行":
                h["点数"] += 4
                h["展開指数"] += 4
                h["加点理由"].append("重馬場補正(先行) +4")

    form_features = parse_form_features(pace_text)

    # 安定指数・期待値指数・危険人気補正・最終軸スコアを追加
    horses = add_axis_extra_scores(horses, form_features)

    for h in horses:
        hole_score = h["複勝点"]
        hole_reasons = []

        if h["カテゴリ"] == "穴馬":

            # 逃げ・先行は3着内に残りやすい
            if h["脚質"] in ["逃げ", "先行"]:
                hole_score += 8
                hole_reasons.append("逃げ/先行穴 +8")

            # 展開有利がある穴馬を強化
            if has_reason(h, "展開有利"):
                hole_score += 6
                hole_reasons.append("展開有利 +6")

            # 7〜9番人気は妙味あり
            if h["人気"] is not None and 7 <= h["人気"] <= 9:
                hole_score += 3
                hole_reasons.append("7〜9番人気 +3")

            # 複勝点が高い穴馬をさらに評価
            if h["複勝点"] >= 25:
                hole_score += 5
                hole_reasons.append("複勝点25以上 +5")

            feature = form_features.get(h["馬番"], {})

            if feature.get("前走4角3番手以内"):
                hole_score += 5
                hole_reasons.append("前走4角3番手以内 +5")

            if feature.get("前走0.5秒差以内"):
                hole_score += 5
                hole_reasons.append("前走0.5秒差以内 +5")

            if feature.get("近3走馬券内2回以上"):
                hole_score += 5
                hole_reasons.append("近3走馬券内2回以上 +5")

            # 追込は届かないリスクを減点
            if h["脚質"] == "追込":
                hole_score -= 5
                hole_reasons.append("追込 -5")

            # 複勝点が低い穴馬は基本的に危険
            if h["複勝点"] < 15:
                hole_score -= 10
                hole_reasons.append("複勝点15未満 -10")

            if feature.get("半年以上休養"):
                hole_score -= 5
                hole_reasons.append("半年以上休養 -5")

            if feature.get("前走1秒以上負け"):
                hole_score -= 5
                hole_reasons.append("前走1秒以上負け -5")

            if feature.get("近3走二桁着順2回以上"):
                hole_score -= 5
                hole_reasons.append("近3走二桁着順2回以上 -5")

        h["穴スコア"] = hole_score
        h["馬柱評価"] = hole_reasons

    return list(horse_map.values())

def make_prediction(horses):
    popular, hole, big_hole = set_category(horses)

    axis_mode = "normal"

    popular_candidates = [
        h for h in popular
        if h["複勝点"] >= 20
    ]

    hole_recommendations = []

    if popular_candidates:
        axis_candidates = popular_candidates
    else:
        hole_recommendations = [
            h for h in hole
            if h["複勝点"] >= 20
        ]

        if hole_recommendations:
            axis_candidates = hole_recommendations
            axis_mode = "hole"
        else:
            axis_candidates = popular
            axis_mode = "weak"

    axis_candidates_sorted = sorted(
        axis_candidates,
        key=lambda x: x.get("最終軸スコア", x["軸スコア"]),
        reverse=True
    )

    axis = axis_candidates_sorted[0] if axis_candidates_sorted else None
    axis_no = axis["馬番"] if axis else None

    popular_sorted = sorted(popular, key=lambda x: x["点数"], reverse=True)

    remain_popular = [
        h for h in popular_sorted
        if h["馬番"] != axis_no
    ]

    usable = [
        h for h in horses
        if h["カテゴリ"] != "大穴馬"
        and h["馬番"] != axis_no
    ]

    fuku_sorted = sorted(usable, key=lambda x: x["複勝点"], reverse=True)

    second_round = []

    if remain_popular:
        second_round.append(remain_popular[0])

    for h in fuku_sorted:
        if h not in second_round:
            second_round.append(h)

        if len(second_round) >= 3:
            break

    third_round = second_round.copy()

    if len(remain_popular) >= 2:
        last_popular = remain_popular[1]
        if last_popular not in third_round:
            third_round.append(last_popular)

    for h in fuku_sorted:
        if h not in third_round:
            third_round.append(h)

        if len(third_round) >= 6:
            break

    cut_horses = [
        h for h in horses
        if h != axis
        and h not in third_round
    ]

    return axis, second_round, third_round, cut_horses, axis_mode, hole_recommendations

def make_tickets(axis, second_round, third_round):
    tickets = []

    if axis is None:
        return tickets

    for second, third in product(second_round, third_round):
        if axis["馬番"] != second["馬番"] and axis["馬番"] != third["馬番"] and second["馬番"] != third["馬番"]:
            tickets.append((axis, second, third))

    return tickets

def make_wide_tickets(second_round):
    wide_tickets = []

    if len(second_round) < 2:
        return wide_tickets

    for a, b in combinations(second_round, 2):
        wide_tickets.append((a, b))

    return wide_tickets

def make_sanrenpuku_16_tickets(horses, track_condition):
    # 通常馬場：従来どおり「人気馬1〜3番人気」＋「穴馬」
    # 不良馬場：人気縛りを外し、最終軸スコア上位＋穴スコア上位から選ぶ
    if track_condition == "不良":
        popular = sorted(
            horses,
            key=lambda x: x.get("最終軸スコア", x["軸スコア"]),
            reverse=True
        )[:6]

        holes = sorted(
            horses,
            key=lambda x: x["穴スコア"],
            reverse=True
        )
    else:
        popular = [
            h for h in horses
            if h["カテゴリ"] == "人気馬"
        ]

        holes = [
            h for h in horses
            if h["カテゴリ"] == "穴馬"
        ]

    # 人気軸2頭は、総合点だけでなく安定指数・期待値指数・危険人気補正込みの最終軸スコアで選ぶ
    popular_sorted = sorted(
        popular,
        key=lambda x: x.get("最終軸スコア", x["軸スコア"]),
        reverse=True
    )

    hole_sorted = sorted(
        holes,
        key=lambda x: x["穴スコア"],
        reverse=True
    )

    if len(popular_sorted) < 2 or len(hole_sorted) < 4:
        return [], None

    remain_popular = popular_sorted[:2]
    selected_holes = [
        h for h in hole_sorted
        if h not in remain_popular
    ][:4]

    main_axis = remain_popular[0]
    sub_axis = remain_popular[1]

    tickets = []

    group1 = [sub_axis] + selected_holes

    for a, b in combinations(group1, 2):
        ticket = tuple(sorted(
            [main_axis["馬番"], a["馬番"], b["馬番"]]
        ))
        tickets.append(ticket)

    for a, b in combinations(selected_holes, 2):
        ticket = tuple(sorted(
            [sub_axis["馬番"], a["馬番"], b["馬番"]]
        ))
        tickets.append(ticket)

    tickets = list(dict.fromkeys(tickets))

    info = {
        "main_axis": main_axis,
        "sub_axis": sub_axis,
        "selected_holes": selected_holes,
        "cut_popular": popular_sorted[2:],
        "cut_holes": hole_sorted[4:]
    }

    return tickets, info


def make_sanrenpuku_select_tickets(sanrenpuku16_info):
    """
    16点ルールの人気軸A・人気軸B・穴馬4頭を使って、
    別枠で厳選3点・厳選5点を作る。
    16点ルールはそのまま残す。
    """
    if not sanrenpuku16_info:
        return [], []

    main_axis = sanrenpuku16_info["main_axis"]
    sub_axis = sanrenpuku16_info["sub_axis"]
    holes = sanrenpuku16_info["selected_holes"]

    if len(holes) < 3:
        return [], []

    h1 = holes[0]
    h2 = holes[1]
    h3 = holes[2]

    select3 = [
        tuple(sorted([main_axis["馬番"], sub_axis["馬番"], h1["馬番"]])),
        tuple(sorted([main_axis["馬番"], sub_axis["馬番"], h2["馬番"]])),
        tuple(sorted([main_axis["馬番"], h1["馬番"], h2["馬番"]])),
    ]

    select5 = select3 + [
        tuple(sorted([sub_axis["馬番"], h1["馬番"], h2["馬番"]])),
        tuple(sorted([main_axis["馬番"], h1["馬番"], h3["馬番"]])),
    ]

    select3 = list(dict.fromkeys(select3))
    select5 = list(dict.fromkeys(select5))

    return select3, select5

def judge_confidence(horses, axis, second_round, axis_mode):
    if axis is None:
        return "★☆☆☆☆", "見送り"

    if axis_mode == "hole":
        return "★★★☆☆", "穴馬推奨"

    if axis_mode == "weak":
        return "★☆☆☆☆", "軸不安・見送り寄り"

    sorted_horses = sorted(horses, key=lambda x: x["点数"], reverse=True)

    top_score = sorted_horses[0]["点数"]
    second_score = sorted_horses[1]["点数"] if len(sorted_horses) >= 2 else top_score
    gap = top_score - second_score

    hole_count = sum(1 for h in second_round if h["カテゴリ"] == "穴馬")

    if gap >= 20:
        return "★★★★★", "勝負"
    elif gap >= 12 and hole_count >= 1:
        return "★★★★☆", "勝負"
    elif gap >= 8:
        return "★★★☆☆", "通常"
    elif gap >= 4:
        return "★★☆☆☆", "見送り寄り"
    else:
        return "★☆☆☆☆", "見送り"

if st.button("予想開始"):
    horses = parse_race_table(race_table)

    if not horses:
        st.error("出走表を読み取れませんでした。PC版・スマホ版どちらでも、出走表部分を少し広めにコピーして貼ってください。")
    else:
        horses = add_points(horses, analysis, running_style_text, style_graph_text, pace_text)

        axis, second_round, third_round, cut_horses, axis_mode, hole_recommendations = make_prediction(horses)

        tickets = make_tickets(axis, second_round, third_round)
        wide_tickets = make_wide_tickets(second_round)
        sanrenpuku16_tickets, sanrenpuku16_info = make_sanrenpuku_16_tickets(
            horses,
            track_condition
        )
        select3_tickets, select5_tickets = make_sanrenpuku_select_tickets(sanrenpuku16_info)
        confidence, recommendation = judge_confidence(horses, axis, second_round, axis_mode)

        st.success(f"{len(horses)}頭を読み取りました。")
        st.info(f"馬場状態：{track_condition}")

        st.subheader("馬ごとの評価点")

        for h in sorted(horses, key=lambda x: x["点数"], reverse=True):
            odds_text = f"｜オッズ {h['オッズ']}" if h["オッズ"] is not None else ""
            style_text = f"｜脚質 {h['脚質']}" if h["脚質"] else ""

            st.write(
                f"{h['馬番']} {h['馬名']}｜"
                f"{h['人気']}番人気｜"
                f"{h['カテゴリ']}｜"
                f"総合{h['点数']}点｜"
                f"複勝{h['複勝点']}点｜"
                f"穴{h['穴スコア']}点｜"
                f"安定{h['安定指数']}点｜"
                f"期待値{h['期待値指数']}点｜"
                f"軸{round(h['軸スコア'], 1)}点｜"
                f"最終軸{round(h['最終軸スコア'], 1)}点"
                f"{odds_text}{style_text}"
            )

            if h["加点理由"]:
                st.caption(" / ".join(h["加点理由"]))

            if h.get("馬柱評価"):
                st.caption("穴評価: " + " / ".join(h["馬柱評価"]))

        st.subheader("予想結果")

        st.info(
            f"信頼度：{confidence}\n\n"
            f"判定：{recommendation}"
        )

        if axis_mode == "hole":
            st.warning(
                "⚠️ 軸不在レース\n\n"
                "人気1〜3番人気の複勝点が全て20点未満です。\n"
                "穴馬中心の3連複・ワイド向きです。"
            )

            st.write("### 穴推奨馬")
            for h in sorted(hole_recommendations, key=lambda x: x["複勝点"], reverse=True):
                st.write(
                    f"{h['馬番']} {h['馬名']}｜"
                    f"{h['人気']}番人気｜"
                    f"総合{h['点数']}点｜"
                    f"複勝{h['複勝点']}点｜"
                    f"穴{h['穴スコア']}点｜"
                    f"安定{h['安定指数']}点｜"
                    f"期待値{h['期待値指数']}点｜"
                    f"最終軸{round(h['最終軸スコア'], 1)}点"
                )

        elif axis_mode == "weak":
            st.warning(
                "⚠️ 軸不安レース\n\n"
                "人気馬にも穴馬にも複勝点20以上の馬がいません。\n"
                "見送り寄りです。"
            )

        if axis:
            axis_label = "◎ 軸馬"
            if axis_mode == "hole":
                axis_label = "◎ 穴推奨軸"
            elif axis_mode == "weak":
                axis_label = "◎ 暫定軸"

            st.success(
                f"{axis_label}：{axis['馬番']} {axis['馬名']}｜"
                f"総合{axis['点数']}点｜"
                f"複勝{axis['複勝点']}点｜"
                f"安定{axis['安定指数']}点｜"
                f"期待値{axis['期待値指数']}点｜"
                f"最終軸{round(axis['最終軸スコア'], 1)}点"
            )

        st.write("### 2巡目")
        for h in second_round:
            st.write(f"{h['馬番']} {h['馬名']}｜総合{h['点数']}点｜複勝{h['複勝点']}点")

        st.write("### 3巡目")
        for h in third_round:
            st.write(f"{h['馬番']} {h['馬名']}｜総合{h['点数']}点｜複勝{h['複勝点']}点")

        st.write("### 消し馬")
        for h in cut_horses:
            st.write(
                f"{h['馬番']} {h['馬名']}｜"
                f"{h['人気']}番人気｜"
                f"{h['カテゴリ']}｜"
                f"総合{h['点数']}点｜"
                f"複勝{h['複勝点']}点"
            )

        st.subheader("3連複16点ルール")

        if track_condition == "不良":
            st.warning("不良馬場モード：人気縛り解除で、最終軸スコア・穴スコア重視で選出しています。")

        if sanrenpuku16_info:
            main_axis = sanrenpuku16_info["main_axis"]
            sub_axis = sanrenpuku16_info["sub_axis"]
            selected_holes = sanrenpuku16_info["selected_holes"]

            st.write(
                f"人気軸A：{main_axis['馬番']} {main_axis['馬名']}｜"
                f"総合{main_axis['点数']}点｜複勝{main_axis['複勝点']}点｜最終軸{round(main_axis['最終軸スコア'], 1)}点"
            )

            st.write(
                f"人気軸B：{sub_axis['馬番']} {sub_axis['馬名']}｜"
                f"総合{sub_axis['点数']}点｜複勝{sub_axis['複勝点']}点｜最終軸{round(sub_axis['最終軸スコア'], 1)}点"
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

            st.subheader("3連複 厳選3点・5点")

            if select3_tickets:
                st.write("### 厳選3点")
                st.code(
                    " / ".join(
                        f"{a}-{b}-{c}" for a, b, c in select3_tickets
                    )
                )
                st.write(f"厳選3点：{len(select3_tickets)}点")

            if select5_tickets:
                st.write("### 厳選5点")
                st.code(
                    " / ".join(
                        f"{a}-{b}-{c}" for a, b, c in select5_tickets
                    )
                )
                st.write(f"厳選5点：{len(select5_tickets)}点")
        else:
            st.warning("3連複16点ルールを作成できませんでした。人気馬または穴馬の数が不足しています。")

        st.subheader("3連単フォーメーション")

        if axis:
            second_nums = ",".join(str(h["馬番"]) for h in second_round)
            third_nums = ",".join(str(h["馬番"]) for h in third_round)
            st.code(f"{axis['馬番']} → {second_nums} → {third_nums}")

        st.write(f"3連単点数：{len(tickets)}点")

        st.subheader("ワイド（2巡目BOX）")

        if wide_tickets:
            wide_text = []

            for t in wide_tickets:
                wide_text.append(f"{t[0]['馬番']}-{t[1]['馬番']}")

            st.code(" / ".join(wide_text))
            st.write(f"ワイド点数：{len(wide_tickets)}点")

        with st.expander("3連単買い目一覧"):
            for t in tickets:
                st.write(f"{t[0]['馬番']} → {t[1]['馬番']} → {t[2]['馬番']}")
