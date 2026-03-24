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
        "desc": "小镇依山傍水，青石铺路，客栈与药铺挤在一条街上。人不多，却总有江湖消息流转。",
        "encounters": [
            Encounter("客栈风波", "npc", 4),
            Encounter("市井流言", "mystery", 4),
            Encounter("药铺欠账", "npc", 3),
            Encounter("暗巷偷袭", "combat", 3),
            Encounter("路边遗落的包裹", "loot", 2),
        ],
        "travel_to": ["雁回山道", "青竹林", "断桥渡口"],
    },
    "雁回山道": {
        "desc": "山道蜿蜒，风从崖下卷起，行商少见，刀客常来。",
        "encounters": [
            Encounter("山贼拦路", "combat", 5),
            Encounter("落单镖师", "npc", 3),
            Encounter("石壁剑痕", "mystery", 2),
            Encounter("断崖寒风", "rest", 1),
        ],
        "travel_to": ["青石镇", "黑松岭", "古寺残钟"],
    },
    "青竹林": {
        "desc": "竹影如海，风过如涛。林深处常有隐士与妖魅传闻。",
        "encounters": [
            Encounter("竹林迷阵", "mystery", 4),
            Encounter("毒蛇出没", "combat", 3),
            Encounter("采药人求助", "npc", 3),
            Encounter("灵泉一口", "rest", 2),
            Encounter("竹间藏物", "loot", 2),
        ],
        "travel_to": ["青石镇", "古寺残钟", "寒潭密径"],
    },
    "断桥渡口": {
        "desc": "旧桥半断，渡口一叶扁舟。夜里水雾最浓，最易藏人。",
        "encounters": [
            Encounter("水匪截舟", "combat", 4),
            Encounter("渡船老叟", "npc", 4),
            Encounter("河面鬼火", "mystery", 3),
            Encounter("水边捡到银两", "loot", 1),
        ],
        "travel_to": ["青石镇", "黑松岭"],
    },
    "黑松岭": {
        "desc": "黑松压顶，林间常年不见日光。传闻有邪门外道盘踞。",
        "encounters": [
            Encounter("邪徒试剑", "combat", 5),
            Encounter("密林黑影", "mystery", 3),
            Encounter("废寨余烬", "loot", 2),
            Encounter("迷路的书生", "npc", 2),
        ],
        "travel_to": ["雁回山道", "断桥渡口", "寒潭密径"],
    },
    "古寺残钟": {
        "desc": "寺破钟残，香火断绝。墙上仍有残存的戒律与壁画。",
        "encounters": [
            Encounter("残钟回响", "mystery", 4),
            Encounter("寺中客僧", "npc", 3),
            Encounter("伏击暗器", "combat", 2),
            Encounter("香案下的旧匣", "loot", 2),
            Encounter("清修一夜", "rest", 2),
        ],
        "travel_to": ["雁回山道", "青竹林"],
    },
    "寒潭密径": {
        "desc": "寒潭如镜，水下暗流牵着一条密径。踏错一步，便是生死。",
        "encounters": [
            Encounter("潭下暗流", "combat", 4),
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
    "渡船老叟",
    "客栈掌柜",
    "药铺郎中",
    "落单镖师",
    "寺中客僧",
    "采药人",
    "迷路书生",
]


FACTIONS: list[str] = ["青竹门", "雁回镖局", "黑松会", "古寺遗脉"]


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

