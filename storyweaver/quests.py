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
    goal_routes: list[dict[str, int]] = field(default_factory=list)
    required_fact_routes: list[list[str]] = field(default_factory=list)
    estimated_turns: int = 10
    fail_turn_budget: int = 16
    win_guidance: str = ""
    preferred_intents: list[str] = field(default_factory=list)


STORY_BACKGROUND = (
    "十年前，天门宗内乱骤起，正朔一脉被清洗，幸存者四散江湖。此后多年，关于天门的真相被层层篡改，"
    "而一支名为黑松会的势力则悄然渗入镖局、渡口、寺院与山道。近月来，青石镇接连出现失踪、劫镖、运人与灭口，"
    "像是有人正在替一场更大的秩序重构提前清路。"
)

PLAYER_OPENING_STANCE = (
    "你以无名客的身份踏入青石镇，本是为了追查旧友顾长风的失踪。可在抵达后的第一夜，黑松会、镖路密信、天门旧部与假死灭口"
    "几个名字竟在同一处交缠出现。你意识到顾长风卷入的不是一桩地方旧案，而是一场足以改写江湖秩序的连环局。"
)

FINAL_GOAL_SUMMARY = (
    "你的最终目标不是只赢几场战斗，而是沿着黑松会这条线追到幕后宗师夜无锋，查明天门旧局被谁篡改、顾长风为何还活着、"
    "以及夜无锋究竟想用什么方式重塑江湖。到了终局，你必须决定自己是以武、以人、以财，还是以证据来结束这场风暴。"
)

ENDING_PATH_HINT = (
    "一路上，你可以强闯、潜入、调查、谈判、设局、交易，也可以聚拢人心或公开真相。不同路径积累的不是同一种胜利，"
    "它们会把你带向截然不同的江湖收束。"
)


MAIN_STORY: list[Stage] = [
    Stage(
        "s1",
        "青石镇异闻",
        "确认黑松会在青石镇的运作方式，并查明顾长风死讯真假",
        "青石镇表面仍是寻常市井，可客栈流言、药铺旧债、渡口夜雾与棺材铺验尸都在指向同一件事：黑松会已经把手伸进了镇中。",
        "本章冲突在于局势尚未明牌。你不知道谁是饵、谁是线人、谁已经被收买，也不知道顾长风的死讯究竟是真灭口还是假尸惑人。",
        "这是整条主线的起点。玩家若能在这里看清黑松会如何掳人、运人和封口，后面所有章节都会有更稳的落脚点。",
        6,
        "青石镇/客栈/渡口/棺材铺",
        5,
        20,
        "chapter_1_done",
        goal_counters={"query_count": 2},
        goal_routes=[{"query_count": 2}, {"explore_count": 1, "negotiate_win": 1}, {"query_count": 1, "explore_count": 1}],
        estimated_turns=6,
        fail_turn_budget=12,
        win_guidance="第一章重在摸清暗网结构。打听、验尸、渡口调查、与赛西施或孙家周旋都可成为有效推进，不必拘泥于单一路径。",
        preferred_intents=["query", "explore", "negotiate"],
    ),
    Stage(
        "s2",
        "雁回山路",
        "确认山道封锁背后的真实目的，并保住通往残钟寺的联系线",
        "雁回山道已成黑松会截断旧部联系的险关。赵鹤年的镖队、密信与伏兵都说明这里截的不是货，而是通往旧案真相的活线。",
        "本章冲突是护人、护信、查内鬼三线并行。你既可能护镖同行，也可能先设伏、审俘或反查山道中的通风者。",
        "若这条山道彻底被黑松会掌控，后面的残钟寺、净空与天门旧部联系都会被活活掐断。",
        14,
        "雁回山道",
        8,
        35,
        "chapter_2_done",
        goal_counters={"combat_win": 1},
        goal_routes=[{"combat_win": 1}, {"query_count": 1, "explore_count": 1}, {"combat_win": 1, "query_count": 1}],
        estimated_turns=8,
        fail_turn_budget=14,
        win_guidance="第二章允许护镖、设伏、审俘、伪装同行等多种推进。只要能确认黑松会在切断联络，并保住或记住密信线索，就算达成核心目标。",
        preferred_intents=["combat", "explore", "query", "travel"],
    ),
    Stage(
        "s3",
        "古寺残钟",
        "在残钟寺找到被篡改前的历史入口，并确认寒潭密径与正朔旧部的关系",
        "残钟寺表面香火未绝，暗里却是被篡改历史覆盖的真相废墟。净空、假僧、残卷、地宫与旧号都在等一个能把碎片重新拼起来的人。",
        "本章冲突在于真假信息并存。你可能先见净空，也可能先撞见假僧、禁区机关或被偷换的经卷，必须在伪历史中找出真正通往旧案的入口。",
        "这一章是黑松会阴影首次与天门旧史正面重叠的地方。读懂这里，玩家才会第一次真正理解夜无锋问题不只是强敌，而是正统本身被篡改。",
        22,
        "古寺残钟",
        10,
        40,
        "chapter_3_done",
        goal_counters={"explore_count": 2},
        goal_routes=[{"explore_count": 2}, {"query_count": 1, "explore_count": 1}, {"negotiate_win": 1, "explore_count": 1}],
        estimated_turns=10,
        fail_turn_budget=18,
        win_guidance="第三章重在拼接历史断层。探索、询问、取得净空信任、辨认真伪文本都算有效推进，不要求固定先后顺序。",
        preferred_intents=["explore", "query", "negotiate"],
    ),
    Stage(
        "s4",
        "寒潭密径",
        "在寒潭密径取得与掌门信物相关的关键证物，并确认听雪楼开始介入",
        "寒潭密径是天门旧局留下的坟场。百骨洞、铸剑台与寒铁碎片一起证明，正朔旧部并非无故消失，而是在这里被有计划地埋葬。",
        "本章冲突在于环境险恶、证物争夺与追兵步步紧逼同步发生。你既可以潜行、强闯、解谜，也可能顺着遗骸与旧器一点点拼出真相。",
        "寒铁碎片不只是道具，它关系到天门掌门信物、旧案正统与后续联盟是否会相信你。",
        30,
        "寒潭密径",
        12,
        50,
        "chapter_4_done",
        goal_counters={"explore_count": 3},
        goal_routes=[{"explore_count": 3}, {"explore_count": 2, "combat_win": 1}, {"query_count": 1, "explore_count": 2}],
        estimated_turns=12,
        fail_turn_budget=20,
        win_guidance="第四章是环境叙事与夺证并行的章节。潜行、强夺、辨真伪都可推进，只要玩家拿到寒铁碎片或其可靠旁证，并意识到听雪楼已经下场。",
        preferred_intents=["explore", "combat", "rest", "query"],
    ),
    Stage(
        "s5",
        "黑松暗潮",
        "突破黑松会表层迷雾，确认其真正主使并找出顾长风与会盟计划的关系",
        "黑松岭不再只是匪寨，而是一套严密运转的控制枢纽。苍狼也许只是看门人，真正发号施令的人藏在更深处，而顾长风正被囚在这套机器的中心。",
        "本章冲突在于真假主使、地牢线、账册线与潜入路线同时存在。你不一定要正面闯寨，也可以策反、伪装、潜入或沿命令流转反推真正的主人。",
        "这一章是故事从地方暗潮转向江湖大局的决定性转折。玩家要第一次明确：黑松会只是外壳，夜无锋才是布局之人。",
        40,
        "黑松岭",
        15,
        70,
        "chapter_5_done",
        required_facts=["black_wood_token"],
        goal_routes=[{"explore_count": 2, "query_count": 1}, {"combat_win": 1, "explore_count": 1}, {"negotiate_win": 1, "explore_count": 1}],
        estimated_turns=12,
        fail_turn_budget=22,
        required_fact_routes=[["black_wood_token"], ["leader_heading_to_alliance"]],
        win_guidance="第五章允许从地牢、账册、内线、假投名状等多线切入。关键不是固定救人方式，而是确认黑松会外壳之下的真正布局者与会盟目标。",
        preferred_intents=["explore", "query", "combat", "negotiate"],
    ),
    Stage(
        "s6",
        "三门会盟",
        "在三方势力之间试探、交易与拆局，决定终局前你以何种姿态入场",
        "三门会盟不是简单的结盟仪式，而是一场利益、名分、情报和恐惧同时发力的政治斗争。每个人都在看你手里究竟握着几分真相、几分筹码。",
        "本章冲突不是单纯说服，而是判断谁能合作、谁可利用、谁会背叛，并决定你要成为聚盟者、操盘者还是孤行者。",
        "这一章直接决定终局前你能借到多少江湖之力，也决定夜无锋会以何种方式被迫提前暴露。",
        52,
        "三门会盟台/回雁楼",
        18,
        90,
        "chapter_6_done",
        goal_counters={"negotiate_win": 1},
        goal_routes=[{"negotiate_win": 1, "query_count": 1}, {"query_count": 2}, {"negotiate_win": 1, "explore_count": 1}],
        estimated_turns=10,
        fail_turn_budget=20,
        required_fact_routes=[["leader_heading_to_alliance"], ["black_wood_token"], ["black_pine_bridge_plot"]],
        win_guidance="第六章是一座政治场。游说、亮证、布陷、交易、反向操盘都能推进，只要你让至少一方动起来，并逼出夜无锋布局的一部分。",
        preferred_intents=["negotiate", "query", "explore", "combat"],
    ),
    Stage(
        "s7",
        "断桥血战",
        "在奈何桥一役中保住至少一半主动权，并为终局做出不可回退的取舍",
        "会盟之后，所有暗流都在奈何桥上公开冲撞。桥上不只有追兵，还有盟友、旧友、证据、退路和牺牲。你必须在同一场混乱里选择先保什么、先舍什么。",
        "本章冲突在于护人、护物、断后、诈降和突围同时发生。真正可怕的不是敌人多强，而是你无法把一切都带到终局。",
        "奈何桥是终局前的最大筛选。玩家带着怎样的损失、怎样的信义和怎样的残缺进入终章，将直接决定最后一战的气质。",
        64,
        "断桥渡口/奈何桥",
        20,
        120,
        "chapter_7_done",
        goal_counters={"combat_win": 2},
        goal_routes=[{"combat_win": 2}, {"combat_win": 1, "explore_count": 1}, {"combat_win": 1, "query_count": 1}],
        estimated_turns=12,
        fail_turn_budget=22,
        required_fact_routes=[["black_pine_bridge_plot"], ["escort_guild_infiltrated"], ["tianmen_master_nearby"]],
        win_guidance="第七章不是单一大战，而是高压局势处理。护人、护证、断桥、诈降、反埋伏都算有效手段，重点是带着某种代价保住进入终局的资格。",
        preferred_intents=["combat", "explore", "query", "negotiate"],
    ),
    Stage(
        "s8",
        "终局天门",
        "在天门旧址揭开旧局真相，并以自己的方式终结夜无锋的秩序",
        "当所有证据、旧账与存活下来的人都指向天门旧址，你终于明白黑松会只是夜无锋用来清理道路的刀。真正等待你的，是一整套由恐惧与正统伪装起来的新秩序。",
        "本章冲突在于最后的价值选择。你不仅要面对夜无锋本人的武力与说服，还要决定江湖到底应当由什么活下去。",
        "终局会回收前七章留下的所有积累与代价。你一路以来选择以武、以人、以财或以证推动局势，都会在这里得到回应。",
        78,
        "天门旧址/黑松岭/寒潭秘道",
        35,
        180,
        "final_clear",
        goal_counters={"combat_win": 2},
        required_facts=["black_wood_token"],
        goal_routes=[{"combat_win": 2}, {"negotiate_win": 1, "query_count": 1}, {"query_count": 2, "explore_count": 1}],
        required_fact_routes=[["black_wood_token"], ["black_pine_is_front", "final_master_lair_map"], ["leader_heading_to_alliance", "tianmen_master_nearby"]],
        estimated_turns=14,
        fail_turn_budget=26,
        win_guidance="终局允许攻山、潜入、公开审判、单刀赴会、先救人后翻案等多种形态。关键不是单一打赢，而是以你一路累积出的方式击穿夜无锋的秩序。",
        preferred_intents=["explore", "combat", "query", "negotiate"],
    ),
]


SIDE_QUESTS: list[dict[str, object]] = [
    {
        "id": "q_alchemist",
        "title": "药铺旧债",
        "trigger_locations": ["青石镇"],
        "trigger_intents": ["query", "negotiate", "explore"],
        "resolve_intents": ["negotiate", "query"],
        "objective": "解决孙老实的债务困局，并顺势摸到黑松会胁迫药铺的线头",
        "reward": {"silver": 35, "item": "上品止血散", "reputation": 4},
    },
    {
        "id": "q_ferry",
        "title": "渡口失踪案",
        "trigger_locations": ["断桥渡口"],
        "trigger_intents": ["explore", "query"],
        "resolve_intents": ["explore", "combat"],
        "objective": "查出黑船如何在夜雾里转运活口，并决定是救人、烧船还是反向追踪暗哨",
        "reward": {"silver": 45, "item": "渡口水图", "reputation": 5},
    },
    {
        "id": "q_monk",
        "title": "古寺残卷",
        "trigger_locations": ["古寺残钟"],
        "trigger_intents": ["explore", "query"],
        "resolve_intents": ["explore", "query"],
        "objective": "在残钟寺钟楼、藏经阁与塔林之间找齐宗门记事残卷，补全被篡改的旧史",
        "reward": {"silver": 30, "item": "清心诀抄本", "reputation": 6},
    },
    {
        "id": "q_escort",
        "title": "孤镖千里",
        "trigger_locations": ["雁回山道", "黑松岭"],
        "trigger_intents": ["query", "explore", "combat"],
        "resolve_intents": ["combat", "travel"],
        "objective": "护送失散镖师小伍子返镇，让雁回镖局的信义与后手得以延续",
        "reward": {"silver": 55, "item": "镖局信物", "reputation": 7},
    },
]


def stage_by_index(idx: int) -> Optional[Stage]:
    if idx < 0 or idx >= len(MAIN_STORY):
        return None
    return MAIN_STORY[idx]

