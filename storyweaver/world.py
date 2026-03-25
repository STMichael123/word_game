from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Encounter:
    title: str
    kind: str  # "combat" | "npc" | "loot" | "mystery" | "rest"
    weight: int


LOCATIONS: dict[str, dict[str, object]] = {
    "青石镇": {
        "desc": "青石镇表面仍是寻常市井，归去来客栈、韩记棺材铺与镇西渡口却各自压着一层说不出口的阴影。人情、流言与灭口痕迹都在这里交错。",
        "encounters": [
            Encounter("归去来客栈耳语", "npc", 4),
            Encounter("顾长风死讯流言", "mystery", 4),
            Encounter("药铺旧债", "npc", 3),
            Encounter("黑松探子灭口", "combat", 3),
            Encounter("街角遗落的密札", "loot", 2),
        ],
        "travel_to": ["雁回山道", "青竹林", "断桥渡口"],
    },
    "雁回山道": {
        "desc": "雁回山道如今不只是险路，更像一条专门截断密信、镖队与旧部联系的绞索。风声越急，越像有人在林间等你犯错。",
        "encounters": [
            Encounter("黑松伏弩手", "combat", 5),
            Encounter("失散镖师", "npc", 3),
            Encounter("被截断的密信痕迹", "mystery", 2),
            Encounter("断崖避风处", "rest", 1),
        ],
        "travel_to": ["青石镇", "黑松岭", "古寺残钟"],
    },
    "青竹林": {
        "desc": "青竹林仍像旧日缓冲地带，许多不愿公开露面的线人、采药人和暂避风头的江湖客都可能在这里留下痕迹。",
        "encounters": [
            Encounter("竹林迷踪", "mystery", 4),
            Encounter("埋伏的刀手", "combat", 3),
            Encounter("采药人求助", "npc", 3),
            Encounter("山泉歇脚", "rest", 2),
            Encounter("竹间藏匣", "loot", 2),
        ],
        "travel_to": ["青石镇", "古寺残钟", "寒潭密径"],
    },
    "断桥渡口": {
        "desc": "断桥渡口白日破败，夜里却总有水雾和黑船一起出现。这里既能运货，也能运人，更能把一切目击者吞进河面以下。",
        "encounters": [
            Encounter("黑船水匪", "combat", 4),
            Encounter("渡口线人", "npc", 4),
            Encounter("夜雾中的活口踪迹", "mystery", 3),
            Encounter("漂来的账册残页", "loot", 1),
        ],
        "travel_to": ["青石镇", "黑松岭"],
    },
    "黑松岭": {
        "desc": "黑松岭已经不像匪寨，更像一套有地牢、有刑堂、有命令流转的控制枢纽。你越往里走，越能感觉到这里在替更大的秩序清路。",
        "encounters": [
            Encounter("黑松刑堂刀客", "combat", 5),
            Encounter("密林命令暗号", "mystery", 3),
            Encounter("废寨账册余烬", "loot", 2),
            Encounter("被囚的知情人", "npc", 2),
        ],
        "travel_to": ["雁回山道", "断桥渡口", "寒潭密径"],
    },
    "古寺残钟": {
        "desc": "古寺残钟香火未绝，真史却已残缺。钟楼、藏经阁与偏殿里同时埋着净空守下来的旧卷，也埋着黑松会正在翻找的东西。",
        "encounters": [
            Encounter("残钟回响", "mystery", 4),
            Encounter("守钟僧净空", "npc", 3),
            Encounter("寻卷刀客", "combat", 2),
            Encounter("藏经阁旧匣", "loot", 2),
            Encounter("偏殿调息", "rest", 2),
        ],
        "travel_to": ["雁回山道", "青竹林"],
    },
    "寒潭密径": {
        "desc": "寒潭密径是被埋掉的旧案坟场。百骨、寒铁、铸剑残台与水下秘道彼此咬合，像是在提醒后来者这里曾被人有计划地抹平。",
        "encounters": [
            Encounter("潭边毒使", "combat", 4),
            Encounter("石门残纹", "mystery", 4),
            Encounter("寒铁碎片", "loot", 2),
            Encounter("闭息调息", "rest", 1),
        ],
        "travel_to": ["青竹林", "黑松岭"],
    },
}


LOOT_TABLE: list[tuple[str, int]] = [
    ("止血散", 5),
    ("回气丸", 4),
    ("碎银", 6),
    ("旧地图碎片", 2),
    ("黑木令牌", 1),
    ("寒铁碎片", 1),
    ("竹叶青", 2),
    ("轻身符纸", 1),
]


NPCS: list[str] = [
    "赛西施",
    "韩青石",
    "赵鹤年",
    "净空",
    "蔡海",
    "采药人",
    "被囚的知情人",
]


FACTIONS: list[str] = ["雁回镖局", "黑松会", "残钟寺遗脉", "听雪楼", "水路帮盟"]


def pick_weighted(rng: random.Random, items: list[tuple[object, int]]):
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, w in items:
        upto += w
        if upto >= r:
            return item
    return items[-1][0]


def random_location(rng: random.Random) -> str:
    return rng.choice(list(LOCATIONS.keys()))


def random_encounter(rng: random.Random, location: str) -> Encounter:
    loc = LOCATIONS.get(location) or LOCATIONS["青石镇"]
    encounters: list[Encounter] = list(loc["encounters"])  # type: ignore[assignment]
    return pick_weighted(rng, [(e, e.weight) for e in encounters])


def random_loot(rng: random.Random) -> str:
    return pick_weighted(rng, [(name, w) for name, w in LOOT_TABLE])


def travel_options(location: str) -> list[str]:
    loc = LOCATIONS.get(location) or LOCATIONS["青石镇"]
    return list(loc["travel_to"])  # type: ignore[return-value]

