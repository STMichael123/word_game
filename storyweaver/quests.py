from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    objective: str
    chapter_intro: str
    chapter_conflict: str
    chapter_significance: str
    required_progress: int
    location_hint: str
    reward_reputation: int
    reward_silver: int
    unlock_flag: Optional[str] = None
    goal_counters: dict[str, int] = field(default_factory=dict)
    required_facts: list[str] = field(default_factory=list)
    estimated_turns: int = 10
    fail_turn_budget: int = 16
    win_guidance: str = ""
    preferred_intents: list[str] = field(default_factory=list)


STORY_BACKGROUND = (
    "十年前天门内乱后，宗师一脉销声匿迹，江湖表面恢复平静，暗地里却有一支名为黑松会的势力"
    "不断渗入镖局、渡口、寺院与山道。近月来，青石镇频现失踪、劫镖与灭口之事，像是有人在为一场更大的风暴清路。"
)

PLAYER_OPENING_STANCE = (
    "你以无名客的身份踏入青石镇，本为追查旧友失踪，却在第一夜便听见黑松会、镖路密信与天门旧部的名字同时出现。"
    "你意识到这不只是地方帮会的暗斗，而是一场会改写江湖秩序的连环局。"
)

FINAL_GOAL_SUMMARY = (
    "你的最终目标不是赢几场战斗，而是沿着黑松会这条线追到幕后宗师夜无锋，查明他为何重启天门旧局，并在终局前做出属于你的江湖抉择。"
)

ENDING_PATH_HINT = (
    "一路上，你可以靠武学压服群敌、靠人心聚拢同盟、靠财势布局、或靠证据逼近真相；不同积累会把你引向不同结局。"
)


MAIN_STORY: list[Stage] = [
    Stage(
        "s1",
        "青石镇异闻",
        "打听三条关于黑松会的情报",
        "青石镇的客栈、街口和药铺都在传同一个名字：黑松会。你初到此地，必须先摸清谁在撒网、谁在沉默。",
        "本章冲突在于情报混乱且真假难辨。你既要从街谈巷议里筛出真线索，也要避免过早惊动潜伏在镇上的耳目。",
        "青石镇是整条主线的入口。若你在此看不清黑松会的触角，后面每一章都会像在迷雾里挥刀。",
        6,
        "青石镇/客栈",
        5,
        20,
        "chapter_1_done",
        goal_counters={"query_count": 3},
        estimated_turns=6,
        fail_turn_budget=12,
        win_guidance="先通过打听与交涉建立信息优势，避免无意义硬战。",
        preferred_intents=["query", "negotiate"],
    ),
    Stage(
        "s2",
        "雁回山路",
        "护送镖师穿过山道并击退劫匪",
        "你顺着情报追到雁回山路，发现有人正在系统性截断镖路。被围上的不只是镖师，更是通往幕后真相的第一条活线。",
        "本章冲突是护送与伏击并行。你必须在赶路、护人和迎战之间做取舍，找出是谁在山道上替黑松会办事。",
        "若镖路被彻底切断，后面的密信、人物与证据都会断流；这一章决定你能否保住调查的活口。",
        14,
        "雁回山道",
        8,
        35,
        "chapter_2_done",
        goal_counters={"combat_win": 1},
        estimated_turns=8,
        fail_turn_budget=14,
        win_guidance="山路章节以护送与战斗为核心，优先清除威胁后再移动。",
        preferred_intents=["combat", "travel"],
    ),
    Stage(
        "s3",
        "古寺残钟",
        "在古寺寻找失落戒律并解读线索",
        "山路线索把你引到古寺残钟。寺中戒律残缺、僧众各怀心思，像有人早一步把关键页卷抽走，只留下供人误判的空壳。",
        "本章冲突在于线索碎裂且现场被刻意扰乱。你需要在古寺各处拼回缺失信息，确认谁在借佛门旧迹藏匿真相。",
        "古寺是黑松会与更高层布局第一次真正重叠的地方。你若能读懂残卷，就会第一次摸到终局棋手的影子。",
        22,
        "古寺残钟",
        10,
        40,
        "chapter_3_done",
        goal_counters={"explore_count": 3},
        estimated_turns=10,
        fail_turn_budget=18,
        win_guidance="古寺重线索收集，优先探索与询问，不要频繁休整浪费回合。",
        preferred_intents=["explore", "query"],
    ),
    Stage(
        "s4",
        "寒潭密径",
        "进入寒潭密径，取得寒铁碎片",
        "古寺中断裂的记载指向寒潭密径。那里的寒铁碎片既是证物，也是开启下一层真相的钥匙，各方势力都在抢先落子。",
        "本章冲突在于环境险恶与争夺同步升级。你需要顶住寒潭与埋伏的双重压力，把碎片先一步掌握在手里。",
        "寒铁碎片关系到后续势力谈判与真相拼图。拿不到它，你后面就只能被别人牵着走。",
        30,
        "寒潭密径",
        12,
        50,
        "chapter_4_done",
        goal_counters={"explore_count": 5},
        estimated_turns=12,
        fail_turn_budget=20,
        win_guidance="寒潭章节重在持续探索，必要时小幅休整后继续推进。",
        preferred_intents=["explore", "rest"],
    ),
    Stage(
        "s5",
        "黑松暗潮",
        "查明黑松会首领身份",
        "拿到寒潭线索后，你终于逼近黑松岭核心。黑松会不再只是暗处传闻，而是一张有层级、有纪律、并且在替某人遮掩真正意图的网。",
        "本章冲突在于你必须把“黑松会是谁”推进到“黑松会在替谁做事”。只有首领身份浮出水面，终局敌人才会现形。",
        "这是主线由地方黑帮案转向江湖大局的转折点。查明首领身份，意味着你第一次真正逼近幕后宗师。",
        40,
        "黑松岭",
        15,
        70,
        "chapter_5_done",
        required_facts=["black_wood_token"],
        estimated_turns=12,
        fail_turn_budget=22,
        win_guidance="黑松暗潮必须围绕令牌与真相，优先探索和打听相关线索。",
        preferred_intents=["explore", "query"],
    ),
    Stage(
        "s6",
        "三门会盟",
        "在三方势力间谈判并稳住局势",
        "你带着证据走进三门会盟，却发现所有人都想利用你手里的线索。有人想借你揭局，有人想借会盟嫁祸，还有人想让混乱先于真相发生。",
        "本章冲突不是单纯说服，而是在有限时间内判断谁值得结盟、谁在布陷阱，并防止局势彻底失控。",
        "这一章决定终局前你站在孤身一人还是有人同路的位置，也会直接影响你面对夜无锋时能借到多少江湖之力。",
        52,
        "青石镇/古寺",
        18,
        90,
        "chapter_6_done",
        goal_counters={"negotiate_win": 2},
        estimated_turns=10,
        fail_turn_budget=20,
        win_guidance="会盟阶段以谈判为主，战斗只用于破局。",
        preferred_intents=["negotiate", "query"],
    ),
    Stage(
        "s7",
        "断桥血战",
        "在断桥击败伏击者并保住密信",
        "会盟之后，所有暗流都涌向断桥。你握住的密信足以揭开幕后布局，也足以让所有想灭口的人同时现身。",
        "本章冲突在于伏击与争夺骤然公开化。你必须保住密信、击退来敌，并在血战中看清谁是真正替宗师铺路的人。",
        "断桥之战是终局前的筛选。能否保住密信，决定你是带着主动权进入终章，还是被迫在残缺信息下豪赌。",
        64,
        "断桥渡口",
        20,
        120,
        "chapter_7_done",
        goal_counters={"combat_win": 3},
        estimated_turns=12,
        fail_turn_budget=22,
        win_guidance="断桥血战必须快速建立战斗优势，减少无效移动。",
        preferred_intents=["combat", "explore"],
    ),
    Stage(
        "s8",
        "终局天门",
        "集齐线索并迎战幕后宗师",
        "当所有证据都指向天门旧局，你终于明白黑松会只是外壳，真正要重写江湖秩序的人一直在更高处等你。",
        "本章冲突在于最后的抉择与决断。你不仅要迎战夜无锋，还要决定自己要用哪一种方式结束这场风暴。",
        "终局天门会回收前七章埋下的所有积累。你的武学、人脉、证据与选择，都会在这里决定江湖最后记住怎样的你。",
        78,
        "黑松岭/寒潭",
        35,
        180,
        "final_clear",
        goal_counters={"combat_win": 4},
        required_facts=["black_wood_token"],
        estimated_turns=14,
        fail_turn_budget=26,
        win_guidance="终局阶段先补齐关键事实，再进入高风险战斗决断。",
        preferred_intents=["explore", "combat"],
    ),
]


SIDE_QUESTS: list[dict[str, object]] = [
    {
        "id": "q_alchemist",
        "title": "药铺旧债",
        "trigger_locations": ["青石镇"],
        "trigger_intents": ["query", "negotiate", "explore"],
        "resolve_intents": ["negotiate", "query"],
        "objective": "帮药铺追回欠款或协商分期",
        "reward": {"silver": 35, "item": "上品止血散", "reputation": 4},
    },
    {
        "id": "q_ferry",
        "title": "渡口失踪案",
        "trigger_locations": ["断桥渡口"],
        "trigger_intents": ["explore", "query"],
        "resolve_intents": ["explore", "combat"],
        "objective": "调查夜雾中失踪的商旅",
        "reward": {"silver": 45, "item": "渡口水图", "reputation": 5},
    },
    {
        "id": "q_monk",
        "title": "古寺残卷",
        "trigger_locations": ["古寺残钟"],
        "trigger_intents": ["explore", "query"],
        "resolve_intents": ["explore", "query"],
        "objective": "收集三页残卷交给客僧",
        "reward": {"silver": 30, "item": "清心诀抄本", "reputation": 6},
    },
    {
        "id": "q_escort",
        "title": "孤镖千里",
        "trigger_locations": ["雁回山道", "黑松岭"],
        "trigger_intents": ["query", "explore", "combat"],
        "resolve_intents": ["combat", "travel"],
        "objective": "护送落单镖师安全返镇",
        "reward": {"silver": 55, "item": "镖局信物", "reputation": 7},
    },
]


def stage_by_index(idx: int) -> Optional[Stage]:
    if idx < 0 or idx >= len(MAIN_STORY):
        return None
    return MAIN_STORY[idx]

