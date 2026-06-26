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
        "軸スコア": 0,
        "加点理由": []
    }

def parse_pc_style(lines):
    horses = []
    i = 0

    while i < len(lines) - 4:
        match = re.match(r"^(\d+)\s+(\d+)$", lines[i])
        if not match:
            i += 1
            continue

        frame_no = int(match.group(1))
        horse_no = int(match.group(2))

        if lines[i + 1] != "--":
            i += 1
            continue

        horse_name = lines[i + 2].replace("  ", "").strip()
        info_line = lines[i + 3]

        popularity = None
        pop_match = re.search(r"(\d+)", lines[i + 4])
        if pop_match:
            popularity = int(pop_match.group(1))

        parts = re.split(r"\t+|\s{2,}", info_line)

        odds = None
        for p in reversed(parts):
            p = p.strip()
            if re.fullmatch(r"\d+\.\d+", p):
                odds = float(p)
                break

        jockey = parts[2].strip() if len(parts) >= 3 else ""
        trainer = parts[3].strip() if len(parts) >= 4 else ""

        horses.append(make_horse(frame_no, horse_no, horse_name, popularity, odds, jockey, trainer))
        i += 5

    return horses

def parse_smartphone_style(lines):
    horses = []
    i = 0

    while i < len(lines) - 4:
        line = lines[i]

        if not re.match(r"^\d+$", line):
            i += 1
            continue

        horse_no = int(line)
        horse_name = lines[i + 1].replace("  ", "").strip()
        info_line = lines[i + 2]

        if "のデータベース" not in info_line:
            i += 1
            continue

        odds = None
        odds_match = re.search(r"(\d+\.\d+)", lines[i + 3])
        if odds_match:
            odds = float(odds_match.group(1))

        popularity = None
        pop_match = re.search(r"(\d+)\s*人気", lines[i + 4])
        if pop_match:
            popularity = int(pop_match.group(1))

        db_removed = re.sub(r"^[牡牝セ]\d+\s+", "", info_line)
        db_removed = db_removed.replace(f"{horse_name}のデータベース", "").strip()
        db_removed = re.sub(r"\d+\.\d+$", "", db_removed).strip()

        jockey = db_removed.split()[0] if db_removed else ""
        trainer = ""
        frame_no = (horse_no + 1) // 2

        horses.append(make_horse(frame_no, horse_no, horse_name, popularity, odds, jockey, trainer))
        i += 5

    return horses

def parse_race_table(text):
    lines = clean_lines(text)
    horses = parse_pc_style(lines)

    if not horses:
        horses = parse_smartphone_style(lines)

    unique = {}
    for h in horses:
        unique[h["馬番"]] = h

    return list(unique.values())

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

    for h in horses:
        if h["人気"] is None:
            h["カテゴリ"] = "人気不明"
            big_hole.append(h)
        elif h["人気"] <= 3:
            h["カテゴリ"] = "人気馬"
            popular.append(h)
        elif h["人気"] <= 9:
            h["カテゴリ"] = "穴馬"
            hole.append(h)
        else:
            h["カテゴリ"] = "大穴馬"
            big_hole.append(h)

    return popular, hole, big_hole

def has_reason(horse, keyword):
    return any(keyword in reason for reason in horse["加点理由"])

def calc_axis_score(horse):
    style_bonus = {
        "逃げ": 10,
        "先行": 7,
        "差し": -3,
        "追込": -5
    }.get(horse["脚質"], 0)

    return horse["点数"] * 0.5 + horse["複勝点"] * 0.7 + style_bonus

def add_points(horses, analysis_text, running_style_text, style_graph_text, pace_text):
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
        for area in ["栗東 ", "美浦 ", "大井 ", "浦和 ", "北海道 ", "兵庫 ", "船橋 ", "川崎 "]:
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
                h["加点理由"].append("展開有利(単騎逃げ) +15")

        elif candidate_count == 2:
            if h["馬番"] in escape_candidates:
                h["点数"] += 8
                h["加点理由"].append("展開有利(逃げ候補) +8")
            elif h["脚質"] == "先行":
                h["点数"] += 5
                h["加点理由"].append("展開有利(先行) +5")

        elif candidate_count >= 3:
            if h["脚質"] == "差し":
                h["点数"] += 8
                h["加点理由"].append("展開有利(差し) +8")
            elif h["脚質"] == "追込":
                h["点数"] += 5
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
        h["軸スコア"] = calc_axis_score(h)

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
        key=lambda x: x["軸スコア"],
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
        confidence, recommendation = judge_confidence(horses, axis, second_round, axis_mode)

        st.success(f"{len(horses)}頭を読み取りました。")

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
                f"軸{round(h['軸スコア'], 1)}点"
                f"{odds_text}{style_text}"
            )

            if h["加点理由"]:
                st.caption(" / ".join(h["加点理由"]))

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
                    f"軸{round(h['軸スコア'], 1)}点"
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
                f"軸{round(axis['軸スコア'], 1)}点"
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
