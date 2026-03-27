import copy
from collections import deque
from pathlib import Path

from storyweaver.engine import GameEngine
from storyweaver.llm_client import OfflineLLMClient


SKILLS = ["\u8f7b\u529f", "\u62db\u67b6", "\u5185\u529f", "\u7edd\u6280"]
MANUAL = {
    "query": "\u6253\u542c\u6d88\u606f",
    "explore": "\u63a2\u7d22\u56db\u5468",
    "rest": "\u4f11\u606f\u8c03\u606f",
    "combat": "\u4e3b\u52a8\u51fa\u624b\u6218\u6597",
    "negotiate": "\u4e0a\u524d\u4ea4\u6d89",
}
REPORT = Path("d:/NLProject/_tmp_autoplay_report.txt")


def log(*parts: object) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write(" ".join(str(x) for x in parts) + "\n")


def clone_engine(engine: GameEngine) -> GameEngine:
    return copy.deepcopy(engine)


def choose_input(turn: dict, desired_intents: list[str]) -> tuple[str, str, str]:
    options = list((turn or {}).get("options") or [])
    for intent in desired_intents:
        for opt in options:
            if str(opt.get("intent")) == intent:
                return str(opt.get("text") or ""), intent, "option"
    intent = desired_intents[0]
    return MANUAL[intent], intent, "manual"


def stage_plan(engine: GameEngine) -> list[str]:
    st = engine.state
    idx = int(st.flags.get("stage_idx", 0))
    counters = st.flags.get("objective_counters", {}) if isinstance(st.flags.get("objective_counters"), dict) else {}
    known = st.known_facts
    progress = int(st.flags.get("progress", 0))
    health = st.health
    stamina = st.stamina

    if idx == 0:
        return ["query"]
    if idx == 1:
        if int(counters.get("query_count", 0)) < 1:
            return ["query"]
        if int(counters.get("explore_count", 0)) < 1:
            return ["explore"]
        return ["query", "explore"]
    if idx == 2:
        if int(counters.get("explore_count", 0)) < 2:
            return ["explore"]
        return ["query", "explore"]
    if idx == 3:
        if int(counters.get("query_count", 0)) < 1:
            return ["query"]
        if int(counters.get("explore_count", 0)) < 2:
            return ["explore"]
        return ["query", "explore", "rest"]
    if idx == 4:
        if not bool(known.get("black_wood_token")):
            if health < 85 or stamina < 75:
                return ["rest"]
            return ["explore", "query"]
        if health < 90 or stamina < 80:
            return ["rest"]
        if int(counters.get("query_count", 0)) < 1:
            return ["query"]
        if int(counters.get("explore_count", 0)) < 2:
            return ["explore"]
        return ["query", "explore"]
    if idx == 5:
        if health < 85 or stamina < 75:
            return ["rest"]
        if int(counters.get("query_count", 0)) < 2:
            return ["query"]
        return ["query", "negotiate", "explore"]
    if idx == 6:
        if health < 100 or stamina < 90:
            return ["rest"]
        if int(counters.get("combat_win", 0)) < 1:
            return ["combat"]
        if int(counters.get("query_count", 0)) < 1:
            return ["query"]
        return ["query", "explore"]
    if idx == 7:
        if health < 100 or stamina < 100:
            return ["rest"]
        return ["boss"]
    return ["boss"]


def find_skill_sequence(engine: GameEngine, *, boss: bool, max_depth: int) -> list[str]:
    action_name = "boss_skill_action" if boss else "skirmish_skill_action"
    debug_key = "boss" if boss else "skirmish"
    queue = deque([(clone_engine(engine), [])])
    seen = set()

    while queue:
        sim, path = queue.popleft()
        if boss:
            state = sim._boss_state()
            key = (
                sim.state.health,
                sim.state.stamina,
                state.get("hp"),
                state.get("phase"),
                state.get("rage"),
                tuple(sorted(state.get("cooldowns", {}).items())),
            )
        else:
            state = sim._skirmish_state()
            key = (
                sim.state.health,
                sim.state.stamina,
                state.get("hp"),
                state.get("rage"),
                tuple(sorted(state.get("cooldowns", {}).items())),
            )
        if key in seen:
            continue
        seen.add(key)
        if len(path) >= max_depth:
            continue

        for skill in SKILLS:
            nxt = clone_engine(sim)
            turn = getattr(nxt, action_name)(skill)
            status = str(turn.get("debug", {}).get(debug_key))
            new_path = path + [skill]
            if status == "won":
                return new_path
            if status != "lost":
                queue.append((nxt, new_path))
    return []


def main() -> None:
    REPORT.write_text("", encoding="utf-8")
    engine = GameEngine()
    engine.client = OfflineLLMClient()
    turn = engine.opening_scene()
    trace: list[object] = []

    for step in range(160):
        plan = stage_plan(engine)
        if plan[0] == "boss":
            started = engine.boss_skill_action(SKILLS[2])
            if str(started.get("debug", {}).get("boss")) not in {"started", "ongoing"}:
                log("boss start failed", started.get("debug"))
                return
            seq = [
                "\u8f7b\u529f",
                "\u5185\u529f",
                "\u8f7b\u529f",
                "\u62db\u67b6",
                "\u8f7b\u529f",
                "\u7edd\u6280",
                "\u8f7b\u529f",
                "\u5185\u529f",
                "\u8f7b\u529f",
                "\u7edd\u6280",
                "\u5185\u529f",
                "\u8f7b\u529f",
            ]
            trace.append(("boss_seq", seq))
            result = started
            for skill in seq:
                result = engine.boss_skill_action(skill)
                log(
                    "boss-step",
                    skill,
                    result.get("debug"),
                    "hp=", engine.state.health,
                    "sta=", engine.state.stamina,
                    "boss_hp=", engine._boss_state().get("hp"),
                    "rage=", engine._boss_state().get("rage"),
                )
                if str(result.get("debug", {}).get("boss")) in {"won", "lost"}:
                    break
            log("FINAL_CLEAR=", bool(engine.state.flags.get("final_clear")))
            log("GAME_OVER=", bool(engine.state.flags.get("game_over")))
            log("ENDING=", engine.state.flags.get("ending"))
            log("HP=", engine.state.health, "STA=", engine.state.stamina)
            log("BOSS_SEQ=", seq)
            log("TRACE_TAIL=", trace[-12:])
            log("RESULT_DEBUG=", result.get("debug"))
            return

        text, used_intent, source = choose_input(turn, plan)
        turn = engine.step(text)
        trace.append(
            (
                step + 1,
                int(engine.state.flags.get("stage_idx", 0)),
                int(engine.state.flags.get("progress", 0)),
                engine.state.health,
                engine.state.stamina,
                plan,
                used_intent,
                source,
                dict(engine.state.known_facts),
            )
        )
        log(
            "step",
            step + 1,
            "stage=", int(engine.state.flags.get("stage_idx", 0)),
            "progress=", int(engine.state.flags.get("progress", 0)),
            "hp=", engine.state.health,
            "sta=", engine.state.stamina,
            "plan=", plan,
            "used=", used_intent,
            "source=", source,
            "facts=", sorted(engine.state.known_facts.keys()),
        )
        if engine.is_skirmish_active():
            seq = find_skill_sequence(engine, boss=False, max_depth=12)
            trace.append(("skirmish_seq", seq, engine._skirmish_state().get("name")))
            if not seq:
                log("skirmish no winning sequence")
                log(trace[-12:])
                return
            for skill in seq:
                turn = engine.skirmish_skill_action(skill)
                log(
                    "skirmish-step",
                    skill,
                    turn.get("debug"),
                    "hp=", engine.state.health,
                    "sta=", engine.state.stamina,
                    "enemy=", engine._skirmish_state().get("hp"),
                )
                if str(turn.get("debug", {}).get("skirmish")) in {"won", "lost"}:
                    break
            if engine.state.flags.get("game_over"):
                log("game over in skirmish", turn.get("debug"))
                log(trace[-12:])
                return

        if engine.state.flags.get("game_over"):
            log("game over", turn.get("debug"))
            log(trace[-12:])
            return

    log("loop exhausted")
    log(trace[-12:])


if __name__ == "__main__":
    main()