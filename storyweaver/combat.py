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
    Enemy("黑松刺客", 64, 16, 6, "快刀", 25, 3, faction="黑松会", origin="黑松岭暗桩", clue_text="此人袖口缝着黑松会的暗纹。", clue_fact_key="black_pine_activity", clue_fact_value="黑松会已将暗桩撒入各地"),
    Enemy("渡口水匪", 56, 14, 5, "缠斗", 22, 2, faction="水匪", origin="断桥下游水寨"),
    Enemy("邪门刀客", 78, 18, 8, "压制", 35, 4, faction="邪门客", origin="外路刀门"),
    Enemy("黑松会执事", 96, 21, 10, "毒刃", 48, 5, faction="黑松会", origin="黑松会内堂", clue_text="执事身上藏着黑木令副牌。", clue_fact_key="black_wood_token", clue_fact_value="True"),
]


CHAPTER_ENEMY_POOLS: dict[str, list[Enemy]] = {
    "s1": [
        Enemy("黑松会暗哨", 52, 13, 5, "快刀", 20, 2, faction="黑松会", origin="青石镇潜伏耳目", clue_text="暗哨低声提到黑松会正在青石镇搜集镖路消息。", clue_fact_key="qingstone_black_pine", clue_fact_value="True"),
        Enemy("地头帮闲", 46, 11, 4, "缠斗", 16, 1, faction="地痞帮闲", origin="青石镇街市"),
    ],
    "s2": [
        Enemy("截镖悍匪", 62, 15, 6, "猛攻", 28, 3, faction="山道匪帮", origin="雁回山道", clue_text="对手提到有人高价买镖师的命。", clue_fact_key="escort_ambush_contract", clue_fact_value="True", evidence_item="镖局信物"),
        Enemy("黑松伏弩手", 58, 16, 5, "伏射", 26, 3, faction="黑松会", origin="雁回山道密林", clue_text="伏弩手携带黑松会传令竹管。", clue_fact_key="black_pine_on_mountain", clue_fact_value="True"),
    ],
    "s3": [
        Enemy("伪僧守钟人", 66, 15, 7, "借势", 30, 3, faction="古寺伪僧", origin="古寺残钟", clue_text="守钟人提到残卷已被人先行拆走。", clue_fact_key="temple_scroll_missing", clue_fact_value="True"),
        Enemy("寻卷刀客", 60, 14, 5, "逼近", 24, 2, faction="黑松会", origin="古寺偏殿", clue_text="刀客腰牌刻着黑松会内堂印记。", clue_fact_key="black_pine_temple_search", clue_fact_value="True"),
    ],
    "s4": [
        Enemy("寒潭巡哨", 72, 17, 8, "压制", 34, 4, faction="寒潭守卫", origin="寒潭密径", clue_text="巡哨口中提到寒铁碎片已被送往黑松岭。", clue_fact_key="cold_iron_route", clue_fact_value="黑松岭"),
        Enemy("潭边毒使", 70, 18, 6, "毒刃", 36, 4, faction="黑松会", origin="寒潭外线", clue_text="毒使身上带着一张通往黑松岭的湿地图。", clue_fact_key="black_pine_route_map", clue_fact_value="True"),
    ],
    "s5": [
        Enemy("黑松刑堂刀客", 84, 19, 9, "压制", 44, 5, faction="黑松会", origin="黑松岭刑堂", clue_text="刑堂刀客承认首领惯用天门旧部的人手。", clue_fact_key="black_pine_leader_uses_tianmen", clue_fact_value="True"),
        Enemy("黑木令主随从", 88, 20, 10, "快刀", 46, 5, faction="黑松会", origin="黑松岭内圈", clue_text="随从怀中的密札写着首领近日将赴三门会盟。", clue_fact_key="leader_heading_to_alliance", clue_fact_value="True", evidence_item="黑木令牌"),
    ],
    "s6": [
        Enemy("三门说客护卫", 78, 18, 8, "借势", 40, 4, faction="会盟外卫", origin="会盟外圈营地", clue_text="护卫提到有人打算借会盟嫁祸黑松会。", clue_fact_key="alliance_false_flag", clue_fact_value="True"),
        Enemy("黑松说客", 76, 17, 7, "游斗", 38, 4, faction="黑松会", origin="会盟暗席", clue_text="说客供认黑松会正在拉拢断桥一线的伏兵。", clue_fact_key="black_pine_bridge_plot", clue_fact_value="True"),
    ],
    "s7": [
        Enemy("断桥伏击手", 86, 20, 9, "追魂", 48, 5, faction="断桥伏兵", origin="断桥渡口", clue_text="伏击手掉出一枚镖局旧印，说明内部有人通敌。", clue_fact_key="escort_guild_infiltrated", clue_fact_value="True", evidence_item="镖局信物"),
        Enemy("黑松死士", 92, 21, 10, "裂势", 50, 5, faction="黑松会", origin="断桥水雾", clue_text="死士临死前喊出“宗师将临天门”。", clue_fact_key="tianmen_master_nearby", clue_fact_value="True"),
    ],
    "s8": [
        Enemy("天门外门弟子", 98, 22, 10, "回风", 55, 6, faction="天门旧部", origin="终局外山门", clue_text="对手言语间承认黑松会只是宗师借用的刀。", clue_fact_key="black_pine_is_front", clue_fact_value="True"),
        Enemy("黑松护法", 102, 23, 11, "裂夜", 58, 6, faction="黑松会", origin="终局秘径", clue_text="护法怀中藏着直通宗师闭关地的秘图。", clue_fact_key="final_master_lair_map", clue_fact_value="True", evidence_item="宗师秘图"),
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

