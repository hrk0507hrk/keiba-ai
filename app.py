"""
競馬AI Next v1.0 (Foundation)
Author: ChatGPT

※土台版
"""

import streamlit as st
from dataclasses import dataclass, field
from typing import List


# ==========================
# Models
# ==========================

@dataclass
class PastResult:
    finish: int = 0
    margin: float = 0.0
    distance: int = 0
    course: str = ""
    track: str = ""


@dataclass
class Horse:
    number: int = 0
    name: str = ""
    jockey: str = ""
    odds: float = 0.0
    popularity: int = 0
    past_results: List[PastResult] = field(default_factory=list)
    ability: float = 0.0


@dataclass
class Race:
    horses: List[Horse] = field(default_factory=list)


# ==========================
# Parser
# ==========================

class Parser:

    def detect(self, text: str):
        if "性齢" in text or "斤量" in text:
            return "PC"
        return "SP"

    def parse(self, text: str):

        race = Race()

        for line in text.splitlines():

            line = line.strip()

            if not line:
                continue

            horse = Horse()
            horse.name = line
            race.horses.append(horse)

        return race


# ==========================
# Ability Engine
# ==========================

class AbilityEngine:

    def analyze(self, race: Race):

        for h in race.horses:
            h.ability = 50.0

        race.horses.sort(
            key=lambda x: x.ability,
            reverse=True
        )

        return race


# ==========================
# UI
# ==========================

st.set_page_config(layout="wide")

st.title("競馬AI Next v1.0")

txt = st.text_area(
    "netkeiba馬柱貼り付け",
    height=350
)

if st.button("解析開始"):

    parser = Parser()

    fmt = parser.detect(txt)

    race = parser.parse(txt)

    race = AbilityEngine().analyze(race)

    st.success(f"解析形式 : {fmt}")

    marks = ["◎","○","▲","△","☆"]

    st.subheader("能力ランキング")

    for i,h in enumerate(race.horses[:5]):

        st.write(
            f"{marks[i]} {h.name}　能力指数 {h.ability:.1f}"
        )

with st.expander("Debug"):

    st.write("現在は土台版です。")
    st.code(txt[:3000])
