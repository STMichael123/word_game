from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .state import GameState


@dataclass
class ConsistencyFix:
    changed: bool
    notes: list[str]


def enforce_state_invariants(state: GameState) -> ConsistencyFix:
    notes: list[str] = []
    changed = False

    if state.max_health <= 0:
        state.max_health = 100
        notes.append("max_health 修复为 100")
        changed = True
    if state.health > state.max_health:
        state.health = state.max_health
        notes.append("health 截断到 max_health")
        changed = True
    if state.health < 0:
        state.health = 0
        notes.append("health 修复为 0")
        changed = True

    if state.max_stamina <= 0:
        state.max_stamina = 100
        notes.append("max_stamina 修复为 100")
        changed = True
    if state.stamina > state.max_stamina:
        state.stamina = state.max_stamina
        notes.append("stamina 截断到 max_stamina")
        changed = True
    if state.stamina < 0:
        state.stamina = 0
        notes.append("stamina 修复为 0")
        changed = True

    # Inventory de-dup (keep first occurrence)
    seen: set[str] = set()
    new_inv: list[str] = []
    for it in state.inventory:
        if it in seen:
            changed = True
            notes.append(f"移除重复物品：{it}")
            continue
        seen.add(it)
        new_inv.append(it)
    state.inventory = new_inv

    # Simple death flag
    if state.health == 0 and not state.flags.get("is_dead"):
        state.flags["is_dead"] = True
        changed = True
        notes.append("角色死亡标记置为 true")
    if state.health > 0 and state.flags.get("is_dead"):
        state.flags["is_dead"] = False
        changed = True
        notes.append("角色死亡标记置为 false")

    return ConsistencyFix(changed=changed, notes=notes)


def record_fact(state: GameState, key: str, value: Any) -> None:
    state.known_facts[key] = value

