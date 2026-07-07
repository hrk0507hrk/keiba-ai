import streamlit as st
import re
from dataclasses import dataclass, field

st.set_page_config(page_title="競馬AI2.0", layout="wide")

st.title("競馬AI2.0")

col1, col2 = st.columns(2)

with col1:
    racecard_text = st.text_area(
        "① 出走表（PC・スマホ対応）",
        height=420
    )

with col2:
    past_text = st.text_area(
        "② 馬柱（9走）",
        height=420
    )

col3, col4 = st.columns(2)

with col3:
    good_frame_text = st.text_input(
        "③ 有利枠（例：1,3,8）"
    )

with col4:
    good_track_text = st.text_input(
        "④ 今回の馬場状態が得意な馬（例：2,7,11）"
    )

track_condition = st.selectbox(
    "馬場状態",
    ["良","稍重","重","不良"]
)

start = st.button("予想開始")

# -------------------------------
# データクラス
# -------------------------------

@dataclass
class PastRace:

    date:str=""
    place:str=""
    distance:int=0
    surface:str=""
    condition:str=""
    finish:int=99
    popularity:int=99
    margin:float=99
    passing:str=""
    jockey:str=""
    weight:float=0
    bodyweight:int=0


@dataclass
class Horse:

    frame:int=0
    number:int=0
    name:str=""
    popularity:int=99
    jockey:str=""
    weight:float=0
    bodyweight:int=0

    races:list=field(default_factory=list)

    score:int=0

    reason:list=field(default_factory=list)


# -------------------------------
# 出走表解析
# -------------------------------

def parse_racecard(text):

    horses=[]

    lines=[x.strip() for x in text.splitlines() if x.strip()]

    i=0

    while i<len(lines)-5:

        m=re.match(r"^(\d+)\s+(\d+)$",lines[i])

        if m:

            frame=int(m.group(1))
            number=int(m.group(2))

            name=lines[i+2]

            pop=99

            for j in range(i,min(i+8,len(lines))):

                p=re.search(r"(\d+)人気",lines[j])

                if p:
                    pop=int(p.group(1))
                    break

            jockey=""

            for j in range(i,min(i+12,len(lines))):

                if re.match(r"^[ァ-ヴ一-龥]{2,}",lines[j]):

                    jockey=lines[j]
                    break

            horses.append(
                Horse(
                    frame=frame,
                    number=number,
                    name=name,
                    popularity=pop,
                    jockey=jockey
                )
            )

        i+=1

    return horses

# -------------------------------
# 馬柱解析
# -------------------------------

def parse_past_performances(text, horses):

    horse_map = {h.name: h for h in horses}

    lines = [x.strip() for x in text.splitlines() if x.strip()]

    current = None

    for line in lines:

        # 馬名取得
        for h in horses:
            if h.name == line:
                current = h
                break

        if current is None:
            continue

        # レース日
        if re.match(r"^\d{4}\.\d{2}\.\d{2}", line):

            r = PastRace()

            cols = line.split()

            try:
                r.date = cols[0]
            except:
                pass

            try:
                r.place = cols[1]
            except:
                pass

            dist = re.search(r"(芝|ダ)(\d+)", line)

            if dist:
                r.surface = dist.group(1)
                r.distance = int(dist.group(2))

            if "良" in line:
                r.condition = "良"

            elif "稍" in line:
                r.condition = "稍重"

            elif "重" in line:
                r.condition = "重"

            elif "不" in line:
                r.condition = "不良"

            finish = re.search(r"^\d+", line)

            if finish:
                pass

            current.races.append(r)

            continue

        if len(current.races) == 0:
            continue

        race = current.races[-1]

        # 着順

        finish = re.search(r"^\d+$", line)

        if finish:

            if race.finish == 99:

                race.finish = int(finish.group())

                continue

        # 人気

        pop = re.search(r"(\d+)人気", line)

        if pop:

            race.popularity = int(pop.group(1))

        # 着差

        margin = re.search(r"\(([-]?\d+\.\d+)\)", line)

        if margin:

            try:
                race.margin = float(margin.group(1))
            except:
                pass

        # 通過順位

        passing = re.search(r"(\d+-\d+.*)", line)

        if passing:

            race.passing = passing.group(1)

        # 騎手

        if race.jockey == "":

            if re.match(r"^[ァ-ヴ一-龥]{2,}", line):

                race.jockey = line

    return horses


# -------------------------------
# 人気グループ
# -------------------------------

def split_popularity(horses):

    top = []

    middle = []

    cut = []

    for h in horses:

        if h.popularity <= 3:

            top.append(h)

        elif h.popularity <= 9:

            middle.append(h)

        else:

            cut.append(h)

    return top, middle, cut


# -------------------------------
# 馬柱評価
# -------------------------------

def evaluate_horse(horse):

    score = 0

    reason = []

    recent = horse.races[:3]

    # 着順

    finish_point = 0

    for r in recent:

        if r.finish == 1:

            finish_point += 10

        elif r.finish == 2:

            finish_point += 8

        elif r.finish == 3:

            finish_point += 6

        elif r.finish <= 5:

            finish_point += 4

        elif r.finish <= 8:

            finish_point += 2

    score += finish_point

    if finish_point >= 20:

        reason.append("近3走内容◎")

    elif finish_point >= 10:

        reason.append("近3走安定")

    # 着差

    margin_point = 0

    for r in recent:

        if r.margin <= 0.2:

            margin_point += 4

        elif r.margin <= 0.5:

            margin_point += 2

    score += margin_point

    if margin_point:

        reason.append("着差優秀")

    # 先行力

    front = 0

    for r in recent:

        if r.passing:

            first = re.findall(r"\d+", r.passing)

            if first:

                if int(first[0]) <= 3:

                    front += 1

    if front >= 2:

        score += 8

        reason.append("先行力あり")

    # 馬場適性

    if horse.number in good_track:

        score += 8

        reason.append("馬場適性")

    # 枠

    if horse.frame in good_frames:

        score += 5

        reason.append("有利枠")

    horse.score = score

    horse.reason = reason

    return horse

# -------------------------------
# 採点実行
# -------------------------------

good_frames = []
good_track = []

if good_frame_text.strip():

    good_frames = [
        int(x)
        for x in re.findall(r"\d+", good_frame_text)
    ]

if good_track_text.strip():

    good_track = [
        int(x)
        for x in re.findall(r"\d+", good_track_text)
    ]

# -------------------------------
# ランキング作成
# -------------------------------

def make_ranking(horses):

    top, middle, cut = split_popularity(horses)

    # 評価

    for h in top:
        evaluate_horse(h)

    for h in middle:
        evaluate_horse(h)

    # 軸

    top.sort(
        key=lambda x: x.score,
        reverse=True
    )

    axis = None

    if len(top):

        axis = top[0]

    remain = top[1:] + middle

    remain.sort(
        key=lambda x: x.score,
        reverse=True
    )

    marks = {}

    if axis:

        marks["◎"] = axis

    if len(remain) >= 1:

        marks["〇"] = remain[0]

    if len(remain) >= 2:

        marks["▲"] = remain[1]

    if len(remain) >= 3:

        marks["△"] = remain[2]

    if len(remain) >= 4:

        marks["☆"] = remain[3]

    return marks, remain, cut


# -------------------------------
# 買い目
# -------------------------------

def make_bets(marks):

    bets = {
        "馬連": [],
        "ワイド": [],
        "3連単": []
    }

    if "◎" not in marks:

        return bets

    m = marks["◎"].number

    if "〇" in marks:

        o = marks["〇"].number

        bets["馬連"].append(f"{m}-{o}")

    if "▲" in marks:

        a = marks["▲"].number

        bets["馬連"].append(f"{m}-{a}")

    if "△" in marks:

        d = marks["△"].number

        bets["馬連"].append(f"{m}-{d}")

    if "▲" in marks:

        bets["ワイド"].append(
            f"{m}-{marks['▲'].number}"
        )

    if "△" in marks:

        bets["ワイド"].append(
            f"{m}-{marks['△'].number}"
        )

    if "▲" in marks and "△" in marks:

        bets["ワイド"].append(
            f"{marks['▲'].number}-{marks['△'].number}"
        )

    if "〇" in marks and "▲" in marks:

        bets["3連単"].append(
            f"{m}→{marks['〇'].number}→{marks['▲'].number}"
        )

        bets["3連単"].append(
            f"{m}→{marks['▲'].number}→{marks['〇'].number}"
        )

    if "△" in marks:

        bets["3連単"].append(
            f"{m}→{marks['〇'].number}→{marks['△'].number}"
        )

        bets["3連単"].append(
            f"{m}→{marks['▲'].number}→{marks['△'].number}"
        )

        bets["3連単"].append(
            f"{marks['〇'].number}→{m}→{marks['▲'].number}"
        )

        bets["3連単"].append(
            f"{marks['▲'].number}→{m}→{marks['〇'].number}"
        )

    return bets


# -------------------------------
# 実行
# -------------------------------

if start:

    horses = parse_racecard(racecard_text)

    horses = parse_past_performances(
        past_text,
        horses
    )

    marks, ranking, cut = make_ranking(horses)

    bets = make_bets(marks)

    st.divider()

    st.subheader("印")

    for mark in ["◎", "〇", "▲", "△", "☆"]:

        if mark in marks:

            h = marks[mark]

            st.success(
                f"{mark} {h.number} {h.name}"
            )

            st.caption(
                "・" + "\n・".join(h.reason)
            )

    st.divider()

    st.subheader("ランキング")

    for i, h in enumerate(ranking, start=1):

        st.write(
            f"{i}位  {h.number} {h.name}  ({h.score}点)"
        )

    st.divider()

    st.subheader("消し馬")

    for h in cut:

        st.write(
            f"{h.number} {h.name}"
        )

    st.divider()

    st.subheader("馬連")

    for x in bets["馬連"]:

        st.code(x)

    st.subheader("ワイド")

    for x in bets["ワイド"]:

        st.code(x)

    st.subheader("3連単")

    for x in bets["3連単"]:

        st.code(x)

# -------------------------------
# AIコメント生成
# -------------------------------

def create_comment(horse):

    comments = []

    score = horse.score

    if score >= 45:
        comments.append("馬柱評価は非常に高い。")

    elif score >= 35:
        comments.append("馬柱内容は上位評価。")

    elif score >= 25:
        comments.append("相手候補として十分。")

    else:
        comments.append("押さえ評価。")

    if "近3走内容◎" in horse.reason:
        comments.append("近走内容が安定。")

    if "先行力あり" in horse.reason:
        comments.append("展開利が見込める。")

    if "有利枠" in horse.reason:
        comments.append("有利枠を引けた。")

    if "馬場適性" in horse.reason:
        comments.append(f"{track_condition}馬場はプラス。")

    return " ".join(comments)


# -------------------------------
# 危険人気馬
# -------------------------------

def danger_horses(horses):

    danger = []

    for h in horses:

        if h.popularity <= 3:

            if h.score < 20:

                danger.append(h)

    return danger


# -------------------------------
# 相手候補
# -------------------------------

def opponent_candidates(ranking):

    return ranking[:6]


# -------------------------------
# 穴候補
# -------------------------------

def hole_candidates(ranking):

    holes = []

    for h in ranking:

        if 4 <= h.popularity <= 9:

            holes.append(h)

    return holes[:3]


# -------------------------------
# 最終表示
# -------------------------------

if start:

    horses = parse_racecard(racecard_text)

    horses = parse_past_performances(
        past_text,
        horses
    )

    marks, ranking, cut = make_ranking(horses)

    bets = make_bets(marks)

    dangers = danger_horses(horses)

    st.divider()

    st.header("AI予想")

    for mark in ["◎","〇","▲","△","☆"]:

        if mark in marks:

            h = marks[mark]

            st.markdown(f"## {mark} {h.number} {h.name}")

            st.write(create_comment(h))

            st.caption("評価項目")

            for r in h.reason:

                st.write("✅", r)

    st.divider()

    st.header("相手ランキング")

    for i,h in enumerate(opponent_candidates(ranking),1):

        st.write(
            f"{i}位　{h.number} {h.name}　({h.score}点)"
        )

    st.divider()

    st.header("穴候補")

    for h in hole_candidates(ranking):

        st.write(
            f"{h.number} {h.name}"
        )

    st.divider()

    st.header("危険人気馬")

    if dangers:

        for h in dangers:

            st.error(
                f"{h.number} {h.name}"
            )

    else:

        st.success("危険人気馬なし")

    st.divider()

    c1,c2,c3 = st.columns(3)

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

    st.divider()

    st.header("全頭評価")

    horses.sort(
        key=lambda x:x.score,
        reverse=True
    )

    for h in horses:

        st.expander(
            f"{h.number} {h.name}　{h.score}点"
        ).write(
            create_comment(h)
        )
