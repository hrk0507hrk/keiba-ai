import streamlit as st
import re
from itertools import product

st.title("競馬予想AI")
st.write("出走表とnetkeibaデータ分析を貼ると、軸・2巡目・3巡目・買い目を自動作成します。")

POINTS = {
    "データ上位馬3頭": 30,
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
    "不利", "馬場向かず", "ペース合わず", "ハイレベル戦", "好ラップ"
]

race_table = st.text_area("netkeibaの出走表を丸ごと貼ってください", height=430)
analysis = st.text_area("netkeibaのデータ分析を貼ってください", height=330)

st.write("### 脚質入力")
st.caption("例：7 先行 のように1行ずつ入力してください。空欄でもOK。")

running_style_text = st.text_area(
    "各馬の脚質",
    height=180,
    placeholder="""例
1 先行
2 差し
3 逃げ
4 先行
5 追込"""
)

def clean_lines(text):
    lines = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line in IGNORE_WORDS:
            continue

        if re.match(r"^\d+/100$", line):
            continue

        lines.append(line)

    return lines

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

        horse_name = lines[i + 2]
        info_line = lines[i + 3]

        popularity = None
        if i + 4 < len(lines):
            pop_match = re.search(r"(\d+)", lines[i + 4])
            if pop_match:
                popularity = int(pop_match.group(1))

        odds = None
        odds_match = re.search(r"(\d+\.\d+)", info_line)
        if odds_match:
            odds = float(odds_match.group(1))

        parts = re.split(r"\t+|\s{2,}", info_line)
        jockey = ""
        trainer = ""

        if len(parts) >= 3:
            jockey = parts[2].strip()

        if len(parts) >= 4:
            trainer = parts[3].strip()

        horses.append({
            "枠番": frame_no,
            "馬番": horse_no,
            "馬名": horse_name,
            "人気": popularity,
            "オッズ": odds,
            "騎手": jockey,
            "調教師": trainer,
            "脚質": "",
            "点数": 0,
            "加点理由": []
        })

        i += 5

    return horses

def parse_smartphone_style(lines):
    horses = []

    for i in range(len(lines)):
        # スマホ版でよくある形：
        # 1
        # シャマル
        # 牡8 57.0 川須栄彦 栗東 松下武士 501(+1) 10.8
        # 5人気
        if not lines[i].isdigit():
            continue

        horse_no = int(lines[i])

        if i + 3 >= len(lines):
            continue

        horse_name = lines[i + 1]
        info_line = lines[i + 2]
        pop_line = lines[i + 3]

        if not re.search(r"[牡牝セ]\d+", info_line):
            continue

        popularity = None
        pop_match = re.search(r"(\d+)\s*人気?", pop_line)
        if pop_match:
            popularity = int(pop_match.group(1))
        elif pop_line.isdigit():
            popularity = int(pop_line)

        odds = None
        odds_match = re.search(r"(\d+\.\d+)", info_line)
        if odds_match:
            odds = float(odds_match.group(1))

        jockey = ""
        trainer = ""

        tokens = re.split(r"\s+|\t+", info_line)

        # 例: 牡8 57.0 川須栄彦 栗東 松下武士 501(+1) 10.8
        if len(tokens) >= 3:
            jockey = tokens[2]

        if len(tokens) >= 5:
            trainer = tokens[3] + " " + tokens[4]

        frame_no = (horse_no + 1) // 2

        horses.append({
            "枠番": frame_no,
            "馬番": horse_no,
            "馬名": horse_name,
            "人気": popularity,
            "オッズ": odds,
            "騎手": jockey,
            "調教師": trainer,
            "脚質": "",
            "点数": 0,
            "加点理由": []
        })

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

def parse_running_style(text):
    styles = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = re.match(r"^(\d+)\s+(.+)$", line)
        if match:
            styles[int(match.group(1))] = match.group(2).strip()

    return styles

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

def add_points(horses, analysis_text, running_style_text):
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
    for h in horses:
        if h["馬番"] in styles:
            h["脚質"] = styles[h["馬番"]]

    good_style_text = " ".join(sections.get("このコースで有利な脚質", []))

    for h in horses:
        if h["脚質"] and h["脚質"] in good_style_text:
            point = POINTS["有利脚質"]
            h["点数"] += point
            h["加点理由"].append(f"有利脚質({h['脚質']}) +{point}")

    return list(horse_map.values())

def set_category(horses):
    popular = []
    hole = []
    big_hole = []

    for h in horses:
        if h["人気"] is None:
            h["カテゴリ"] = "人気不明"
            big_hole.append(h)
        elif h["人気"] <= 4:
            h["カテゴリ"] = "人気馬"
            popular.append(h)
        elif h["人気"] <= 9:
            h["カテゴリ"] = "穴馬"
            hole.append(h)
        else:
            h["カテゴリ"] = "大穴馬"
            big_hole.append(h)

    return popular, hole, big_hole

def make_prediction(horses):
    popular, hole, big_hole = set_category(horses)

    popular_sorted = sorted(popular, key=lambda x: x["点数"], reverse=True)
    hole_sorted = sorted(hole, key=lambda x: x["点数"], reverse=True)

    remaining_popular = popular_sorted[:2]
    cut_popular = popular_sorted[2:]

    axis = remaining_popular[0] if len(remaining_popular) >= 1 else None
    second_popular = remaining_popular[1] if len(remaining_popular) >= 2 else None

    hole_top2 = hole_sorted[:2]
    hole_middle2 = hole_sorted[2:4]
    cut_hole = hole_sorted[4:]

    second_round = []
    if second_popular:
        second_round.append(second_popular)

    second_round += hole_top2
    third_round = second_round + hole_middle2

    cut_horses = cut_popular + cut_hole + big_hole

    return axis, second_round, third_round, cut_horses

def make_tickets(axis, second_round, third_round):
    tickets = []

    if axis is None:
        return tickets

    for second, third in product(second_round, third_round):
        if axis["馬番"] != second["馬番"] and axis["馬番"] != third["馬番"] and second["馬番"] != third["馬番"]:
            tickets.append((axis, second, third))

    return tickets

if st.button("予想開始"):
    horses = parse_race_table(race_table)

    if not horses:
        st.error("出走表を読み取れませんでした。PC版・スマホ版どちらでも、出走表部分を少し広めにコピーして貼ってください。")
    else:
        horses = add_points(horses, analysis, running_style_text)
        axis, second_round, third_round, cut_horses = make_prediction(horses)
        tickets = make_tickets(axis, second_round, third_round)

        st.success(f"{len(horses)}頭を読み取りました。")

        st.subheader("馬ごとの評価点")

        for h in sorted(horses, key=lambda x: x["点数"], reverse=True):
            odds_text = f"｜オッズ {h['オッズ']}" if h["オッズ"] is not None else ""
            style_text = f"｜脚質 {h['脚質']}" if h["脚質"] else ""
            st.write(f"{h['馬番']} {h['馬名']}｜{h['人気']}番人気｜{h['カテゴリ']}｜{h['点数']}点{odds_text}{style_text}")
            if h["加点理由"]:
                st.caption(" / ".join(h["加点理由"]))

        st.subheader("予想結果")

        if axis:
            st.success(f"◎ 軸馬：{axis['馬番']} {axis['馬名']}｜{axis['点数']}点")

        st.write("### 2巡目")
        for h in second_round:
            st.write(f"{h['馬番']} {h['馬名']}｜{h['点数']}点")

        st.write("### 3巡目")
        for h in third_round:
            st.write(f"{h['馬番']} {h['馬名']}｜{h['点数']}点")

        st.write("### 消し馬")
        for h in cut_horses:
            st.write(f"{h['馬番']} {h['馬名']}｜{h['人気']}番人気｜{h['点数']}点")

        st.subheader("3連単フォーメーション")

        if axis:
            second_nums = ",".join(str(h["馬番"]) for h in second_round)
            third_nums = ",".join(str(h["馬番"]) for h in third_round)
            st.code(f"{axis['馬番']} → {second_nums} → {third_nums}")

        st.write(f"点数：{len(tickets)}点")

        with st.expander("買い目一覧"):
            for t in tickets:
                st.write(f"{t[0]['馬番']} → {t[1]['馬番']} → {t[2]['馬番']}")
