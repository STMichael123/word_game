from __future__ import annotations

import random
from dataclasses import dataclass

from .state import GameState


@dataclass
class Enemy:
    name: str
    hp: int
    atk: int
    defense: int
    style: str
    reward_silver: int
    reward_rep: int
    faction: str = "江湖散人"
    origin: str = "来路未明"
    clue_text: str = ""
    clue_fact_key: str = ""
    clue_fact_value: str = ""
    evidence_item: str = ""


@dataclass
class CombatResult:
    won: bool
    log_lines: list[str]
    hp_delta: int
    stamina_delta: int
    silver_delta: int
    rep_delta: int
    loot: list[str]


DEFAULT_ENEMY_POOL: list[Enemy] = [
    Enemy("山道悍匪", 48, 12, 4, "猛攻", 18, 2, faction="流匪", origin="山道草寇"),
    Enemy("黑松刺客", 64, 16, 6, "快刀", 25, 3, faction="黑松会", origin="黑松岭暗桩", clue_text="此人袖口缝着黑松会的暗纹，像是在替一张横跨镇市与山道的大网跑腿。", clue_fact_key="black_pine_activity", clue_fact_value="黑松会已将暗桩撒入各地"),
    Enemy("渡口水匪", 56, 14, 5, "缠斗", 22, 2, faction="水匪", origin="断桥下游水寨", clue_text="水匪提到近来有人高价要他们半夜接黑船，不许问船上运的是谁。", clue_fact_key="black_pine_activity", clue_fact_value="黑松会正借水路转运活口"),
    Enemy("邪门刀客", 78, 18, 8, "压制", 35, 4, faction="邪门客", origin="外路刀门"),
    Enemy("黑松会执事", 96, 21, 10, "毒刃", 48, 5, faction="黑松会", origin="黑松会内堂", clue_text="执事身上藏着黑木令副牌，口风里还带出顾长风并未死透的消息。", clue_fact_key="black_wood_token", clue_fact_value="True"),
]


CHAPTER_ENEMY_POOLS: dict[str, list[Enemy]] = {
    "s1": [
        Enemy("客栈灭口耳目", 52, 13, 5, "快刀", 20, 2, faction="黑松会", origin="归去来客栈外街", clue_text="耳目死咬着赛西施最近盯上了几批夜半投宿的人，黑松会怕她看得太多。", clue_fact_key="qingstone_black_pine", clue_fact_value="True"),
        Enemy("棺铺盯梢刀手", 54, 12, 5, "缠斗", 18, 2, faction="黑松会", origin="韩记棺材铺后巷", clue_text="刀手靴底沾着棺木灰，显然在韩记棺材铺外守了不止一夜，顾长风那具尸体多半有假。", clue_fact_key="han_qingshi_fake_body", clue_fact_value="True"),
        Enemy("地头帮闲", 46, 11, 4, "缠斗", 16, 1, faction="地痞帮闲", origin="青石镇街市", clue_text="帮闲说镇西渡口近来常有不登记的夜船靠岸。", clue_fact_key="black_pine_activity", clue_fact_value="黑松会已渗入青石镇水路"),
    ],
    "s2": [
        Enemy("截镖悍匪", 62, 15, 6, "猛攻", 28, 3, faction="山道匪帮", origin="雁回山道", clue_text="对手提到有人高价买赵鹤年镖队的命，镖车里装的根本不是寻常货。", clue_fact_key="escort_ambush_contract", clue_fact_value="True", evidence_item="镖局信物"),
        Enemy("黑松伏弩手", 58, 16, 5, "伏射", 26, 3, faction="黑松会", origin="雁回山道密林", clue_text="伏弩手携带黑松会传令竹管，里头写着先断山道，再截旧部联系。", clue_fact_key="black_pine_on_mountain", clue_fact_value="True"),
        Enemy("追信刀客", 64, 15, 6, "追魂", 30, 3, faction="黑松会", origin="雁回绝壁小道", clue_text="刀客承认赵鹤年护送的那封密信会把人直接引到残钟寺。", clue_fact_key="jingkong_true_scroll", clue_fact_value="True"),
    ],
    "s3": [
        Enemy("伪僧守钟人", 66, 15, 7, "借势", 30, 3, faction="古寺伪僧", origin="古寺残钟", clue_text="守钟人提到净空守的根本不是钟，而是一卷足以翻案的真史残页。", clue_fact_key="jingkong_true_scroll", clue_fact_value="True"),
        Enemy("寻卷刀客", 60, 14, 5, "逼近", 24, 2, faction="黑松会", origin="古寺偏殿", clue_text="刀客腰牌刻着黑松会内堂印记，嘴里却反复问顾长风是否已被引出来。", clue_fact_key="black_pine_temple_search", clue_fact_value="True"),
        Enemy("藏经阁灭迹人", 68, 16, 6, "压制", 32, 3, faction="黑松会", origin="藏经阁暗室", clue_text="灭迹人承认残卷已被拆走大半，只剩净空还在硬撑。", clue_fact_key="temple_scroll_missing", clue_fact_value="True"),
    ],
    "s4": [
        Enemy("寒潭巡哨", 72, 17, 8, "压制", 34, 4, faction="寒潭守卫", origin="寒潭密径", clue_text="巡哨口中提到寒铁碎片已被送往黑松岭，连铸剑台残件也有人要一并收走。", clue_fact_key="cold_iron_route", clue_fact_value="黑松岭"),
        Enemy("潭边毒使", 70, 18, 6, "毒刃", 36, 4, faction="黑松会", origin="寒潭外线", clue_text="毒使身上带着一张通往黑松岭的湿地图，角落还压着苏婉晴的人留下的记号。", clue_fact_key="tingxuelou_involved", clue_fact_value="True"),
        Enemy("寒潭封口客", 74, 18, 7, "裂势", 38, 4, faction="黑松会", origin="寒潭百骨洞", clue_text="封口客说他们不是来守潭，而是来等一个会追顾长风旧线的人自己送上门。", clue_fact_key="black_pine_route_map", clue_fact_value="True"),
    ],
    "s5": [
        Enemy("黑松刑堂刀客", 84, 19, 9, "压制", 44, 5, faction="黑松会", origin="黑松岭刑堂", clue_text="刑堂刀客承认首领惯用天门旧部的人手，苍狼在这里只是代人执刀。", clue_fact_key="black_pine_leader_uses_tianmen", clue_fact_value="True"),
        Enemy("苍狼亲随", 86, 20, 9, "裂夜", 45, 5, faction="黑松会", origin="黑松岭内寨", clue_text="亲随咬死苍狼只是看门人，真正下令的人从不亲临刑堂。", clue_fact_key="canglang_is_not_master", clue_fact_value="True"),
        Enemy("黑木令主随从", 88, 20, 10, "快刀", 46, 5, faction="黑松会", origin="黑松岭内圈", clue_text="随从怀中的密札写着首领近日将赴三门会盟，顾长风则会被带去做压场的筹码。", clue_fact_key="gu_changfeng_captive", clue_fact_value="True", evidence_item="黑木令牌"),
    ],
    "s6": [
        Enemy("三门说客护卫", 78, 18, 8, "借势", 40, 4, faction="会盟外卫", origin="会盟外圈营地", clue_text="护卫提到有人打算借会盟嫁祸黑松会，好逼沈岳先替人出刀。", clue_fact_key="alliance_false_flag", clue_fact_value="True"),
        Enemy("黑松说客", 76, 17, 7, "游斗", 38, 4, faction="黑松会", origin="会盟暗席", clue_text="说客供认黑松会正在拉拢断桥一线的伏兵，连蔡海的人也被拿来试探价码。", clue_fact_key="black_pine_bridge_plot", clue_fact_value="True"),
        Enemy("水路试锋客", 80, 18, 8, "缠斗", 42, 4, faction="蔡海水路帮", origin="会盟偏席", clue_text="试锋客放话蔡海已经握住几条生死水路，谁能拿出真相谁就能借船。", clue_fact_key="caihai_water_route", clue_fact_value="True"),
    ],
    "s7": [
        Enemy("断桥伏击手", 86, 20, 9, "追魂", 48, 5, faction="断桥伏兵", origin="断桥渡口", clue_text="伏击手掉出一枚镖局旧印，说明内部有人通敌，赵鹤年一路上的防线早被卖过。", clue_fact_key="escort_guild_infiltrated", clue_fact_value="True", evidence_item="镖局信物"),
        Enemy("黑松死士", 92, 21, 10, "裂势", 50, 5, faction="黑松会", origin="断桥水雾", clue_text="死士临死前喊出“宗师将临天门”，还说沈岳的人已经被逼到不得不提前动身。", clue_fact_key="tianmen_master_nearby", clue_fact_value="True"),
        Enemy("正道断后客", 90, 20, 9, "回风", 49, 5, faction="南武林盟", origin="奈何桥北岸", clue_text="断后客误把你当成搅局者，交手间却透露沈岳已调正道人手压向天门旧址。", clue_fact_key="shenyue_forces_moving", clue_fact_value="True"),
    ],
    "s8": [
        Enemy("天门外门弟子", 98, 22, 10, "回风", 55, 6, faction="天门旧部", origin="终局外山门", clue_text="对手言语间承认黑松会只是宗师借用的刀，真正的新秩序会在天门旧址重立。", clue_fact_key="black_pine_is_front", clue_fact_value="True"),
        Enemy("夜无锋近侍", 104, 23, 11, "裂夜", 60, 6, faction="天门宗师一脉", origin="终局秘径", clue_text="近侍怀中藏着直通宗师闭关地的秘图，还备着专门压顾长风证词的口供底稿。", clue_fact_key="final_master_lair_map", clue_fact_value="True", evidence_item="宗师秘图"),
        Enemy("黑松护法", 102, 23, 11, "裂夜", 58, 6, faction="黑松会", origin="天门外山门", clue_text="护法承认夜无锋已经不需要黑松会继续藏身，接下来只等最后的收束。", clue_fact_key="black_pine_is_front", clue_fact_value="True"),
    ],
}


def spawn_enemy(rng: random.Random, danger_tier: int, stage_id: str | None = None) -> Enemy:
    pool = CHAPTER_ENEMY_POOLS.get(stage_id or "", DEFAULT_ENEMY_POOL)
    base = rng.choice(pool)
    scale = max(1.0, 1.0 + 0.16 * (danger_tier - 1))
    return Enemy(
        name=base.name,
        hp=int(base.hp * scale),
        atk=int(base.atk * scale),
        defense=int(base.defense * scale),
        style=base.style,
        reward_silver=int(base.reward_silver * scale),
        reward_rep=max(1, int(base.reward_rep * scale)),
        faction=base.faction,
        origin=base.origin,
        clue_text=base.clue_text,
        clue_fact_key=base.clue_fact_key,
        clue_fact_value=base.clue_fact_value,
        evidence_item=base.evidence_item,
    )


def run_auto_combat(state: GameState, rng: random.Random, enemy: Enemy) -> CombatResult:
    player_hp = state.health
    player_stamina = state.stamina
    enemy_hp = enemy.hp
    logs: list[str] = [f"你遭遇【{enemy.name}】，对方招式：{enemy.style}。"]

    for i in range(1, 8):  # max 7 rounds; avoid over-punishing
        if player_hp <= 0 or enemy_hp <= 0:
            break
        # Player turn: weighted by stamina
        critical = rng.random() < 0.12
        base_atk = 12 + state.martial_level * 3 + state.inner_power // 8
        if player_stamina < 20:
            base_atk = int(base_atk * 0.8)
        damage = max(1, base_atk - enemy.defense + rng.randint(-2, 4))
        if critical:
            damage += 8
        enemy_hp -= damage
        player_stamina = max(0, player_stamina - rng.randint(6, 12))
        logs.append(f"第{i}回合：你出招命中，造成 {damage} 伤害。敌方剩余 {max(enemy_hp, 0)}。")
        if enemy_hp <= 0:
            break

        # Enemy turn
        guard = rng.random() < 0.18
        incoming = max(1, enemy.atk - (state.martial_level + (4 if guard else 0)) + rng.randint(-4, 2))
        player_hp -= incoming
        logs.append(f"第{i}回合：{enemy.name}反击，造成 {incoming} 伤害。你剩余 {max(player_hp, 0)}。")
        if guard:
            logs.append("你成功格挡了部分攻势。")

    won = enemy_hp <= 0 and player_hp > 0
    if not won and player_hp <= 0:
        # Keep long-run playability: being defeated does not hard-end the campaign.
        player_hp = max(8, state.max_health // 8)
        logs.append("你力竭倒地，所幸被路人救下，勉强保住一口气。")

    hp_delta = player_hp - state.health
    stamina_delta = player_stamina - state.stamina
    silver_delta = enemy.reward_silver if won else -min(12, state.silver)
    rep_delta = enemy.reward_rep if won else -2
    loot = ["血纹刀穗"] if won and rng.random() < 0.2 else []
    return CombatResult(
        won=won,
        log_lines=logs,
        hp_delta=hp_delta,
        stamina_delta=stamina_delta,
        silver_delta=silver_delta,
        rep_delta=rep_delta,
        loot=loot,
    )

