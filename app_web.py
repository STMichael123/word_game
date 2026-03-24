"""app_web.py — StoryWeaver Web 前端（FastAPI + 纯 HTML/JS，水墨风）"""
from __future__ import annotations

import asyncio
import json
import os
import socket
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from storyweaver import GameEngine
from storyweaver.quests import FINAL_GOAL_SUMMARY, stage_by_index

app = FastAPI(title="StoryWeaver Web")
SESSION_COOKIE = "sw_session_id"
ENGINE_POOL: dict[str, GameEngine] = {}
ENGINE_LOCKS: dict[str, Lock] = {}
POOL_LOCK = Lock()


# ─── 工具 ────────────────────────────────────────────────────────────────────

class ActionRequest(BaseModel):
    text: str


class SkillRequest(BaseModel):
    skill: str


def _get_session_id(request: Request) -> str:
    sid = request.cookies.get(SESSION_COOKIE)
    if sid and isinstance(sid, str):
        return sid
    return uuid4().hex


def _get_session_engine(session_id: str) -> tuple[GameEngine, Lock]:
    with POOL_LOCK:
        engine = ENGINE_POOL.get(session_id)
        if engine is None:
            engine = GameEngine()
            engine.bind_memory_namespace(f"session_{session_id}")
            ENGINE_POOL[session_id] = engine
        lock = ENGINE_LOCKS.get(session_id)
        if lock is None:
            lock = Lock()
            ENGINE_LOCKS[session_id] = lock
    return engine, lock


def _set_session_cookie(resp: Response, session_id: str) -> None:
    resp.set_cookie(key=SESSION_COOKIE, value=session_id, httponly=False, samesite="lax")


def _get_state_data(engine: GameEngine) -> dict[str, Any]:
    """从指定 session engine 提取结构化状态。调用时需持有对应 session lock。"""
    st = engine.state
    idx = int(st.flags.get("stage_idx", 0))
    stage = stage_by_index(idx)
    stage_timing = engine._get_stage_timing()
    bs = engine._boss_state()
    sk = engine._skirmish_state()
    return {
        "location": st.location,
        "day": st.day,
      "time_phase": str(st.flags.get("time_phase", "白昼") or "白昼"),
      "time_label": engine._time_label(),
        "turn": int(st.flags.get("turn", 0)),
        "stage_idx": idx,
        "health": st.health,
        "max_health": st.max_health,
        "stamina": st.stamina,
        "max_stamina": st.max_stamina,
        "reputation": st.reputation,
        "silver": st.silver,
        "martial_level": st.martial_level,
        "inner_power": st.inner_power,
        "inventory": list(st.inventory[-8:]),
        "stage_title": stage.title if stage else "终局",
        "stage_obj": stage.objective if stage else "已完成",
        "stage_conflict": stage.chapter_conflict if stage else "大局已定，江湖只余回声。",
        "stage_significance": stage.chapter_significance if stage else "你已走到故事终点。",
        "final_goal": FINAL_GOAL_SUMMARY,
        "stage_estimated_turns": int(stage_timing.get("estimated", 0)),
        "stage_turn_limit": int(stage_timing.get("limit", 0)),
        "stage_turn_elapsed": int(stage_timing.get("elapsed", 0)),
        "stage_turn_remaining": int(stage_timing.get("remaining", 0)),
        "game_over": bool(st.flags.get("game_over", False)),
        "game_over_reason": str(st.flags.get("game_over_reason", "")),
        "game_over_epilogue": str(st.flags.get("game_over_epilogue", "")),
        "can_export": idx >= 1,
        "llm_mode": str(st.flags.get("last_llm_mode", "")),
        "llm_error": str(st.flags.get("last_llm_error", "")),
        "llm_parse_fail_count": int(st.flags.get("llm_parse_fail_count", 0)),
        "active_quests": list(st.flags.get("active_side_quests", [])),
        "memory_preview": engine.memory_preview(5),
        # boss
        "boss_available": engine.is_boss_available(),
        "boss_active": bool(bs.get("active")),
        "boss_name": bs.get("name", ""),
        "boss_hp": bs.get("hp", 0),
        "boss_max_hp": bs.get("max_hp", 1),
        "boss_phase": bs.get("phase", 0),
        "boss_turn": bs.get("turn", 0),
        "boss_rage": bs.get("rage", 0),
        "boss_next_move": bs.get("next_move", "未显"),
        "boss_cooldowns": dict(bs.get("cooldowns", {})),
        "boss_log": list(bs.get("last_log", [])[-6:]),
        "skirmish_active": bool(sk.get("active")),
        "skirmish_name": sk.get("name", ""),
        "skirmish_hp": sk.get("hp", 0),
        "skirmish_max_hp": sk.get("max_hp", 1),
        "skirmish_turn": sk.get("turn", 0),
        "skirmish_rage": sk.get("rage", 0),
        "skirmish_next_move": sk.get("next_move", "未显"),
        "skirmish_cooldowns": dict(sk.get("cooldowns", {})),
        "skirmish_log": list(sk.get("last_log", [])[-6:]),
    }


def _scene_mode_from_state_data(sd: dict[str, Any]) -> str:
    if bool(sd.get("boss_active")):
        return "boss"
    if bool(sd.get("skirmish_active")):
        return "skirmish"
    return "story"


def _step_threadsafe(engine: GameEngine, engine_lock: Lock, user_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
  with engine_lock:
    turn = engine.step(user_text)
    sd = _get_state_data(engine)
    return turn, sd


def _pick_available_port(host: str, preferred_port: int, *, scan_limit: int = 20) -> int:
  for candidate in range(preferred_port, preferred_port + scan_limit):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      try:
        sock.bind((host, candidate))
        return candidate
      except OSError:
        continue
  return preferred_port


# ─── 路由 ────────────────────────────────────────────────────────────────────

@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    session_id = _get_session_id(request)
    engine, engine_lock = _get_session_engine(session_id)
    with engine_lock:
        if int(engine.state.flags.get("turn", 0)) <= 0 and not engine.state.flags.get("story_memory"):
            opening_turn = engine.opening_scene()
        else:
            opening_turn = {
                "narration": "你已回到当前行程，江湖局势仍在延续。",
                "options": list(engine.state.last_options or []),
                "system_messages": [],
            }
        init_sd = _get_state_data(engine)

    init_options = opening_turn.get("options") or []
    init_story = str(opening_turn.get("narration") or "")
    init_system_messages = opening_turn.get("system_messages") or []

    init_sd_json  = json.dumps(init_sd,      ensure_ascii=False)
    init_opt_json = json.dumps(init_options, ensure_ascii=False)
    init_story_js = json.dumps(init_story,   ensure_ascii=False)
    init_system_json = json.dumps(init_system_messages, ensure_ascii=False)

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>江湖织梦</title>
  <style>
    /* ══════════════════════════════════════════════════════
       Reset & 变量
    ══════════════════════════════════════════════════════ */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --paper:    #f2f0e8;
      --card:     #faf9f5;
      --hover:    #e9e5d8;
      --ink:      #18110a;
      --ink2:     #3c3025;
      --ink3:     #7a6b58;
      --line:     #cac3b4;
      --line2:    #ddd8cc;
      --gain:     #1e5218;   /* 增加 绿色 */
      --loss:     #8b1c1c;   /* 减少 红色 */
      --bar-bg:   #dedad0;
      --bar-fill: #2c2016;
    }}
    html, body {{
      height: 100%;
      overflow: hidden;
    }}
    body {{
      font-family: "Noto Serif SC", "Source Han Serif CN", "Songti SC", "SimSun", serif;
      background: var(--paper);
      color: var(--ink);
      display: flex;
      flex-direction: column;
    }}

    /* ══════════════════════════════════════════════════════
       顶部标题栏
    ══════════════════════════════════════════════════════ */
    .topbar {{
      display: flex;
      align-items: center;
      padding: 8px 22px;
      border-bottom: 2px solid var(--ink);
      background: var(--paper);
      flex-shrink: 0;
      gap: 10px;
    }}
    .brand {{
      display: flex;
      flex-direction: column;
      gap: 1px;
    }}
    .brand-title {{
      font-size: 18px;
      font-weight: bold;
      letter-spacing: 0.45em;
    }}
    .brand-sub {{
      font-size: 11px;
      color: var(--ink3);
      letter-spacing: 0.2em;
    }}
    .topbar-sep {{
      flex: 1;
    }}
    .sys-btn {{
      background: transparent;
      border: 1px solid var(--ink3);
      color: var(--ink2);
      font-family: inherit;
      font-size: 12px;
      letter-spacing: 0.1em;
      padding: 4px 12px;
      cursor: pointer;
      border-radius: 0;
      transition: background 100ms;
    }}
    .sys-btn:hover {{ background: var(--hover); }}
    #topbar-status {{
      font-size: 11px;
      color: var(--ink3);
      letter-spacing: 0.05em;
      min-width: 130px;
      text-align: right;
    }}

    /* ══════════════════════════════════════════════════════
       主布局：对话区 + 侧边栏
    ══════════════════════════════════════════════════════ */
    .layout {{
      flex: 1;
      display: grid;
      grid-template-columns: 1fr 296px;
      overflow: hidden;
      min-height: 0;
    }}

    /* ══════════════════════════════════════════════════════
       对话区
    ══════════════════════════════════════════════════════ */
    .chat-wrap {{
      display: flex;
      flex-direction: column;
      border-right: 1px solid var(--line);
      overflow: hidden;
    }}
    #dialog {{
      flex: 1;
      overflow-y: auto;
      padding: 22px 28px 14px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    /* 叙事块 */
    .narration {{
      background: var(--card);
      border: 1px solid var(--line2);
      border-left: 3px solid var(--ink2);
      padding: 14px 18px;
      font-size: 15px;
      line-height: 1.9;
      white-space: pre-wrap;
      animation: pop 180ms ease;
    }}
    .system-msg {{
      background: linear-gradient(180deg, #f6f1e6 0%, #efe7d7 100%);
      border: 1px solid var(--line);
      border-left: 4px solid #8a6a3f;
      padding: 12px 16px;
      font-size: 13px;
      line-height: 1.8;
      color: var(--ink2);
      white-space: pre-wrap;
      animation: pop 180ms ease;
    }}
    /* 玩家输入 */
    .user-msg {{
      align-self: flex-end;
      background: var(--ink);
      color: var(--paper);
      padding: 7px 14px;
      font-size: 13px;
      line-height: 1.6;
      max-width: 60%;
      animation: pop 120ms ease;
    }}
    /* 等待提示 */
    .waiting {{
      align-self: flex-start;
      font-size: 13px;
      color: var(--ink3);
      letter-spacing: 0.05em;
      border-left: 3px solid var(--bar-bg);
      padding: 6px 12px;
      animation: pop 120ms ease;
    }}
    @keyframes pop {{
      from {{ opacity: 0; transform: translateY(5px); }}
      to   {{ opacity: 1; transform: translateY(0);   }}
    }}

    /* ══════════════════════════════════════════════════════
       选项卡组
    ══════════════════════════════════════════════════════ */
    .options-group {{
      display: flex;
      flex-direction: column;
      gap: 7px;
      animation: pop 200ms ease;
    }}
    .opt-btn {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border: 1px solid var(--line2);
      background: var(--card);
      cursor: pointer;
      font-family: inherit;
      font-size: 14px;
      color: var(--ink);
      text-align: left;
      line-height: 1.5;
      transition: background 100ms, border-color 100ms;
    }}
    .opt-btn:hover         {{ background: var(--hover); border-color: var(--ink2); }}
    .opt-btn:active        {{ background: var(--bar-bg); }}
    .opt-btn:disabled      {{ opacity: 0.45; cursor: not-allowed; }}
    .opt-idx {{
      flex-shrink: 0;
      width: 22px; height: 22px;
      border: 1px solid var(--ink3);
      display: flex; align-items: center; justify-content: center;
      font-size: 12px; color: var(--ink3);
    }}
    .opt-text {{ flex: 1; }}
    .opt-mainline {{
      display: inline-block;
      margin-left: 8px;
      font-size: 11px;
      color: var(--ink2);
      border: 1px solid var(--line2);
      padding: 1px 6px;
      letter-spacing: 0.04em;
    }}
    .opt-meta {{
      font-size: 11px;
      white-space: nowrap;
      color: var(--ink3);
    }}
    .opt-meta.risk-low  {{ color: var(--gain); }}
    .opt-meta.risk-med  {{ color: var(--ink2); }}
    .opt-meta.risk-high {{ color: var(--loss); }}

    /* ══════════════════════════════════════════════════════
       输入栏
    ══════════════════════════════════════════════════════ */
    .input-bar {{
      border-top: 1px solid var(--line);
      padding: 11px 16px;
      display: flex;
      gap: 9px;
      background: var(--paper);
      flex-shrink: 0;
    }}
    #input {{
      flex: 1;
      border: 1px solid var(--line);
      background: var(--card);
      padding: 9px 13px;
      font-family: inherit;
      font-size: 14px;
      color: var(--ink);
      outline: none;
      border-radius: 0;
    }}
    #input:focus {{ border-color: var(--ink2); }}
    #input:disabled {{ opacity: 0.5; }}
    #send-btn {{
      border: 1px solid var(--ink2);
      background: var(--ink);
      color: var(--paper);
      font-family: inherit;
      font-size: 14px;
      padding: 9px 18px;
      letter-spacing: 0.2em;
      cursor: pointer;
      transition: background 100ms;
    }}
    #send-btn:hover    {{ background: var(--ink2); }}
    #send-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}

    /* ══════════════════════════════════════════════════════
       侧边栏
    ══════════════════════════════════════════════════════ */
    #sidebar {{
      overflow-y: auto;
      padding: 14px 13px 18px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: var(--paper);
    }}
    .panel-head {{
      font-size: 12px;
      font-weight: bold;
      letter-spacing: 0.55em;
      border-top:    2px solid var(--ink);
      border-bottom: 1px solid var(--line);
      padding: 5px 0 5px;
      margin-bottom: 10px;
      color: var(--ink);
    }}
    /* 分割线 */
    .divider {{
      border: none;
      border-top: 1px solid var(--line2);
      margin: 8px 0;
    }}
    /* 普通文本行 */
    .srow {{
      font-size: 13px;
      color: var(--ink);
      margin-bottom: 6px;
      display: flex;
      align-items: baseline;
      gap: 3px;
      flex-wrap: wrap;
    }}
    .slabel {{ color: var(--ink3); font-size: 12px; }}
    .sval   {{ font-weight: bold; }}

    /* 血条型状态 */
    .bar-row {{
      margin-bottom: 9px;
    }}
    .bar-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      margin-bottom: 3px;
    }}
    .bar-label {{ color: var(--ink3); }}
    .bar-nums  {{ color: var(--ink); font-weight: bold; font-size: 13px; }}
    .bar-track {{
      height: 5px;
      background: var(--bar-bg);
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: var(--bar-fill);
      transition: width 400ms ease;
    }}

    /* 增减徽章 */
    .delta {{
      font-size: 11px;
      font-weight: bold;
      margin-left: 3px;
    }}
    .delta-up {{ color: var(--gain); animation: fade-out 3s forwards; }}
    .delta-dn {{ color: var(--loss); animation: fade-out 3s forwards; }}
    @keyframes fade-out {{
      0%   {{ opacity: 1; }}
      65%  {{ opacity: 1; }}
      100% {{ opacity: 0; }}
    }}

    /* 任务面板 */
    .quest-item {{
      font-size: 12px;
      line-height: 1.8;
      color: var(--ink2);
      margin-bottom: 3px;
    }}
    .qtag {{
      display: inline-block;
      border: 1px solid var(--ink3);
      color: var(--ink3);
      font-size: 10px;
      padding: 0 4px;
      margin-right: 5px;
      letter-spacing: 0.05em;
    }}
    /* 背包 */
    .inv-text {{
      font-size: 12px;
      color: var(--ink2);
      line-height: 1.9;
    }}

    /* Boss 面板 */
    .boss-btn-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 10px;
    }}
    .skill-btn, .combat-skill-btn {{
      border: 1px solid var(--line2);
      background: var(--card);
      color: var(--ink);
      font-family: inherit;
      font-size: 12px;
      letter-spacing: 0.1em;
      padding: 7px 4px;
      cursor: pointer;
      transition: background 100ms;
    }}
    .skill-btn:hover, .combat-skill-btn:hover    {{ background: var(--hover); border-color: var(--ink2); }}
    .skill-btn:disabled, .combat-skill-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
    .boss-log {{
      font-size: 11px;
      color: var(--ink3);
      line-height: 1.7;
      max-height: 88px;
      overflow-y: auto;
      border-top: 1px solid var(--line2);
      padding-top: 6px;
      margin-top: 6px;
    }}

    /* ══════════════════════════════════════════════════════
       响应式
    ══════════════════════════════════════════════════════ */
    @media (max-width: 840px) {{
      .layout {{ grid-template-columns: 1fr; grid-template-rows: 1fr auto; }}
      #sidebar {{
        border-top: 1px solid var(--line);
        max-height: 38vh;
        overflow-y: auto;
        flex-direction: row;
        flex-wrap: wrap;
        gap: 10px;
        padding: 10px;
      }}
      #char-panel, #quest-panel {{ min-width: 200px; flex: 1; }}
      #boss-panel, #boss-unlock  {{ min-width: 180px; flex: 0 0 auto; }}
    }}
  </style>
</head>
<body>

<!-- ══ 顶部标题栏 ══════════════════════════════════════ -->
<div class="topbar">
  <div class="brand">
    <div class="brand-title">江 湖 织 梦</div>
    <div class="brand-sub">武侠文字冒险</div>
  </div>
  <div class="topbar-sep"></div>
  <button class="sys-btn" onclick="sysCmd('/save')">存　档</button>
  <button class="sys-btn" onclick="sysCmd('/load')">读　档</button>
  <button class="sys-btn" id="export-btn" onclick="exportStory()" style="display:none;">导出故事</button>
  <button class="sys-btn" onclick="confirmReset()">重　开</button>
  <span id="topbar-status"></span>
</div>

<!-- ══ 主体布局 ══════════════════════════════════════════ -->
<div class="layout">

  <!-- 对话区 -->
  <div class="chat-wrap">
    <div id="dialog"></div>
    <div class="input-bar">
      <input id="input" placeholder="输入行动，或点击选项…" autocomplete="off"/>
      <button id="send-btn">行　动</button>
    </div>
  </div>

  <!-- 侧边栏 -->
  <aside id="sidebar">

    <!-- 人物状态 -->
    <div id="char-panel">
      <div class="panel-head">人　物　状　态</div>

      <div class="srow"><span class="slabel">所在：</span><span class="sval" id="s-loc">—</span></div>
      <div class="srow">
        <span class="slabel">时序：</span><span class="sval" id="s-day">—</span>
        <span class="slabel" style="margin-left:10px;">回合：</span><span class="sval" id="s-turn">—</span>
      </div>
      <hr class="divider"/>

      <!-- 气血条 -->
      <div class="bar-row">
        <div class="bar-head">
          <span class="bar-label">气血</span>
          <span><span class="bar-nums" id="s-hp">—</span><span id="d-hp"></span></span>
        </div>
        <div class="bar-track"><div class="bar-fill" id="bar-hp" style="width:0%"></div></div>
      </div>
      <!-- 体力条 -->
      <div class="bar-row">
        <div class="bar-head">
          <span class="bar-label">体力</span>
          <span><span class="bar-nums" id="s-sta">—</span><span id="d-sta"></span></span>
        </div>
        <div class="bar-track"><div class="bar-fill" id="bar-sta" style="width:0%"></div></div>
      </div>
      <hr class="divider"/>

      <div class="srow">
        <span class="slabel">声望：</span><span class="sval" id="s-rep">—</span><span id="d-rep"></span>
        <span class="slabel" style="margin-left:14px;">银两：</span><span class="sval" id="s-sil">—</span><span id="d-sil"></span>
      </div>
      <div class="srow">
        <span class="slabel">武学境界：</span><span class="sval" id="s-ml">—</span><span id="d-ml"></span>
      </div>
      <div class="srow">
        <span class="slabel">内力：</span><span class="sval" id="s-ip">—</span><span id="d-ip"></span>
      </div>
      <hr class="divider"/>

      <div class="slabel" style="font-size:11px;margin-bottom:4px;">背　包</div>
      <div class="inv-text" id="s-inv">无</div>
      <hr class="divider"/>
      <div class="slabel" style="font-size:11px;margin-bottom:4px;">记 忆 索 引</div>
      <div class="inv-text" id="s-mem">无</div>
    </div>

    <!-- 任务状态 -->
    <div id="quest-panel">
      <div class="panel-head">任　务　状　态</div>
      <div class="quest-item" id="q-main">—</div>
      <div class="quest-item" id="q-side" style="margin-top:4px;"></div>
    </div>

    <!-- Boss 解锁入口（未进入战斗时显示） -->
    <div id="boss-unlock" style="display:none;">
      <div class="panel-head">终　章</div>
      <button class="sys-btn" style="width:100%;padding:8px;letter-spacing:0.2em;" onclick="bossStart()">开启终章 Boss 战</button>
    </div>

    <!-- 江湖遭遇战面板 -->
    <div id="skirmish-panel" style="display:none;">
      <div class="panel-head" id="skirmish-head">江湖遭遇战</div>

      <div class="bar-row">
        <div class="bar-head">
          <span class="bar-label" id="skirmish-name-lbl">—</span>
          <span class="bar-nums" id="skirmish-hp-txt">—</span>
        </div>
        <div class="bar-track"><div class="bar-fill" id="bar-skirmish" style="width:100%;background:var(--loss);"></div></div>
      </div>

      <div class="srow" style="font-size:12px;">
        <span class="slabel">回合：</span><span id="skirmish-turn">—</span>
        <span class="slabel" style="margin-left:10px;">怒势：</span><span id="skirmish-rage">—</span>/100
      </div>
      <div class="srow" style="font-size:12px;">
        <span class="slabel">出招预兆：</span><span id="skirmish-move">—</span>
      </div>

      <div class="boss-log" id="skirmish-log"></div>

      <div class="boss-btn-row">
        <button class="combat-skill-btn" data-skill="轻功">轻　功</button>
        <button class="combat-skill-btn" data-skill="招架">招　架</button>
        <button class="combat-skill-btn" data-skill="内功">内　功</button>
        <button class="combat-skill-btn" data-skill="绝技">绝　技</button>
      </div>
    </div>

    <!-- Boss 战面板（战斗中显示） -->
    <div id="boss-panel" style="display:none;">
      <div class="panel-head" id="boss-head">终章 Boss</div>

      <div class="bar-row">
        <div class="bar-head">
          <span class="bar-label" id="boss-name-lbl">—</span>
          <span class="bar-nums" id="boss-hp-txt">—</span>
        </div>
        <div class="bar-track"><div class="bar-fill" id="bar-boss" style="width:100%;background:var(--loss);"></div></div>
      </div>

      <div class="srow" style="font-size:12px;">
        <span class="slabel">阶段：</span><span id="boss-phase">—</span>
        <span class="slabel" style="margin-left:10px;">怒气：</span><span id="boss-rage">—</span>/100
        <span class="slabel" style="margin-left:10px;">回合：</span><span id="boss-turn">—</span>
      </div>
      <div class="srow" style="font-size:12px;">
        <span class="slabel">出招预兆：</span><span id="boss-move">—</span>
      </div>

      <div class="boss-log" id="boss-log"></div>

      <div class="boss-btn-row">
        <button class="skill-btn" data-skill="轻功">轻　功</button>
        <button class="skill-btn" data-skill="招架">招　架</button>
        <button class="skill-btn" data-skill="内功">内　功</button>
        <button class="skill-btn" data-skill="绝技">绝　技</button>
      </div>
    </div>

  </aside>
</div>

<script>
  /* ── 常量 ──────────────────────────────────────────────── */
  const INTENT_CN = {{
    explore:"探索", negotiate:"交涉", combat:"战斗", query:"打听",
    rest:"休整", travel:"前往", use_item:"使用", inventory:"背包", unknown:"行动"
  }};
  const RISK_CN = {{ low:"低", medium:"中", high:"高" }};

  /* ── DOM 引用 ───────────────────────────────────────────── */
  const dialogEl  = document.getElementById("dialog");
  const inputEl   = document.getElementById("input");
  const sendBtn   = document.getElementById("send-btn");
  const statusEl  = document.getElementById("topbar-status");
  let idleStatus = "";

  function setIdleStatus(text) {{
    idleStatus = text || "";
    if (!busy) statusEl.textContent = idleStatus;
  }}

  window.addEventListener("error", (ev) => {{
    statusEl.textContent = "前端脚本错误: " + (ev.message || "未知错误");
  }});

  window.addEventListener("unhandledrejection", (ev) => {{
    const msg = ev && ev.reason ? String(ev.reason) : "Promise 未处理异常";
    statusEl.textContent = "前端脚本错误: " + msg;
  }});

  let prevState = null;
  let busy = false;
  let currentOptions = [];

  /* ══════════════════════════════════════════════════════════
     侧边栏渲染
  ══════════════════════════════════════════════════════════ */
  function setTxt(id, val) {{
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? "—";
  }}

  function clearDialogOptions() {{
    dialogEl.querySelectorAll(".options-group").forEach(el => el.remove());
    currentOptions = [];
  }}

  function resetDialogSurface() {{
    dialogEl.innerHTML = "";
    currentOptions = [];
  }}

  function isCombatActiveState(sd) {{
    return !!(sd && (sd.skirmish_active || sd.boss_active));
  }}

  function shouldSuppressMainDialog(data) {{
    const mode = data && data.scene_mode ? String(data.scene_mode) : "";
    if (mode === "skirmish" || mode === "boss") return true;
    return isCombatActiveState(data && data.state_data ? data.state_data : null);
  }}

  function setBar(id, val, maxVal) {{
    const el = document.getElementById(id);
    if (el) el.style.width = (maxVal > 0 ? Math.round(val / maxVal * 100) : 0) + "%";
  }}

  function showDelta(id, newVal, oldVal) {{
    const el = document.getElementById(id);
    if (!el) return;
    const d = newVal - (oldVal ?? newVal);
    if (d === 0) {{ el.innerHTML = ""; return; }}
    const cls  = d > 0 ? "delta-up" : "delta-dn";
    const sign = d > 0 ? "+" : "";
    // 重建节点以强制重播动画
    el.innerHTML = `<span class="delta ${{cls}}">${{sign}}${{d}}</span>`;
  }}

  function renderState(sd) {{
    const p = prevState;
    const exportBtn = document.getElementById("export-btn");
    if (exportBtn) exportBtn.style.display = sd.can_export ? "" : "none";
    if (!busy && sd.llm_mode && sd.llm_mode !== "online") {{
      setIdleStatus("叙事已降级为离线模式" + (sd.llm_error ? "（" + sd.llm_error + "）" : ""));
    }} else if (sd.llm_mode === "online") {{
      setIdleStatus("在线叙事已连接");
    }}

    // 位置/时间
    setTxt("s-loc",  sd.location);
    setTxt("s-day",  sd.time_label || ("第" + sd.day + "日"));
    setTxt("s-turn", sd.turn);

    // 气血
    setTxt("s-hp",  sd.health + "/" + sd.max_health);
    setBar("bar-hp", sd.health, sd.max_health);
    // 体力
    setTxt("s-sta", sd.stamina + "/" + sd.max_stamina);
    setBar("bar-sta", sd.stamina, sd.max_stamina);

    // 声望/银两/武学/内力
    setTxt("s-rep", sd.reputation);
    setTxt("s-sil", sd.silver);
    setTxt("s-ml",  sd.martial_level);
    setTxt("s-ip",  sd.inner_power);

    // 背包
    document.getElementById("s-inv").textContent =
      (sd.inventory && sd.inventory.length) ? sd.inventory.join("、") : "无";

    const memoryPreview = Array.isArray(sd.memory_preview) ? sd.memory_preview : [];
    document.getElementById("s-mem").textContent = memoryPreview.length
      ? memoryPreview.map(item => `${{item.memory_timestamp || ""}} ${{item.memory_index || ""}}`.trim()).join("\\n")
      : "无";

    // 增减高亮
    if (p) {{
      showDelta("d-hp",  sd.health,        p.health);
      showDelta("d-sta", sd.stamina,       p.stamina);
      showDelta("d-rep", sd.reputation,    p.reputation);
      showDelta("d-sil", sd.silver,        p.silver);
      showDelta("d-ml",  sd.martial_level, p.martial_level);
      showDelta("d-ip",  sd.inner_power,   p.inner_power);
    }}
    prevState = sd;

    // 任务
    document.getElementById("q-main").innerHTML =
      `<span class="qtag">主线</span>${{sd.stage_title}}：${{sd.stage_obj}}` +
      `<div class="quest-item"><span class="qtag">章意</span>${{sd.stage_conflict}}</div>` +
      `<div class="quest-item"><span class="qtag">终局</span>${{sd.final_goal}}</div>` +
      `<div class="quest-item"><span class="qtag">章时</span>预计${{sd.stage_estimated_turns}}回合 / 时限${{sd.stage_turn_limit}}回合 / 剩余${{sd.stage_turn_remaining}}回合</div>`;
    const sideEl = document.getElementById("q-side");
    if (sd.active_quests && sd.active_quests.length) {{
      sideEl.innerHTML = sd.active_quests
        .map(q => `<div class="quest-item"><span class="qtag">支线</span>${{q}}</div>`)
        .join("");
    }} else {{
      sideEl.textContent = "暂无活跃支线任务";
    }}

    // 江湖遭遇战面板
    if (sd.skirmish_active) {{
      document.getElementById("skirmish-panel").style.display = "";
      setTxt("skirmish-head", sd.skirmish_name || "江湖遭遇战");
      setTxt("skirmish-name-lbl", sd.skirmish_name || "敌手");
      setTxt("skirmish-hp-txt", sd.skirmish_hp + "/" + sd.skirmish_max_hp);
      setBar("bar-skirmish", sd.skirmish_hp, sd.skirmish_max_hp);
      setTxt("skirmish-turn", sd.skirmish_turn);
      setTxt("skirmish-rage", sd.skirmish_rage);
      setTxt("skirmish-move", sd.skirmish_next_move);
      const skLogEl = document.getElementById("skirmish-log");
      if (sd.skirmish_log && sd.skirmish_log.length) {{
        skLogEl.innerHTML = sd.skirmish_log.map(l => `<div>${{l}}</div>`).join("");
      }} else {{
        skLogEl.innerHTML = "";
      }}
      clearDialogOptions();
      setIdleStatus("遭遇战进行中，请使用右侧技能按钮");
      updateSkirmishBtns(sd);
    }} else {{
      document.getElementById("skirmish-panel").style.display = "none";
    }}

    // Boss 面板可见性
    if (sd.boss_active) {{
      document.getElementById("boss-unlock").style.display = "none";
      document.getElementById("boss-panel").style.display  = "";
      // boss 数值
      setTxt("boss-head",    sd.boss_name || "终章 Boss");
      setTxt("boss-name-lbl", sd.boss_name || "Boss");
      setTxt("boss-hp-txt",  sd.boss_hp + "/" + sd.boss_max_hp);
      setBar("bar-boss", sd.boss_hp, sd.boss_max_hp);
      setTxt("boss-phase", sd.boss_phase);
      setTxt("boss-rage",  sd.boss_rage);
      setTxt("boss-turn",  sd.boss_turn);
      setTxt("boss-move",  sd.boss_next_move);
      // 战斗日志
      const logEl = document.getElementById("boss-log");
      if (sd.boss_log && sd.boss_log.length) {{
        logEl.innerHTML = sd.boss_log.map(l => `<div>${{l}}</div>`).join("");
      }} else {{
        logEl.innerHTML = "";
      }}
      clearDialogOptions();
      setIdleStatus("终章战斗进行中，请使用右侧技能按钮");
      updateSkillBtns(sd);
    }} else if (sd.boss_available) {{
      document.getElementById("boss-panel").style.display  = "none";
      document.getElementById("boss-unlock").style.display = "";
    }} else {{
      document.getElementById("boss-panel").style.display  = "none";
      document.getElementById("boss-unlock").style.display = "none";
    }}

    if (sd.game_over) {{
      statusEl.textContent = "本局失败：" + (sd.game_over_reason || "章节超时") + "，请 /reset 重开。";
    }}

    const combatActive = isCombatActiveState(sd);
    inputEl.disabled = busy || combatActive;
    sendBtn.disabled = busy || combatActive;
    inputEl.placeholder = combatActive ? "战斗中请使用右侧技能按钮…" : "输入行动，或点击选项…";
  }}

  /* ══════════════════════════════════════════════════════════
     对话区渲染
  ══════════════════════════════════════════════════════════ */
  function addNarration(text) {{
    const div = document.createElement("div");
    div.className = "narration";
    div.textContent = text || "";
    dialogEl.appendChild(div);
    scrollDown();
    return div;
  }}

  function addSystemMsg(text) {{
    const div = document.createElement("div");
    div.className = "system-msg";
    div.textContent = text || "";
    dialogEl.appendChild(div);
    scrollDown();
    return div;
  }}

  function renderSystemMessages(msgs) {{
    (msgs || []).forEach(msg => {{
      if (msg) addSystemMsg(msg);
    }});
  }}

  function addUserMsg(text) {{
    const div = document.createElement("div");
    div.className = "user-msg";
    div.textContent = text;
    dialogEl.appendChild(div);
    scrollDown();
  }}

  function addWaiting() {{
    const div = document.createElement("div");
    div.className = "waiting";
    div.textContent = "笔墨酝酿中·";
    dialogEl.appendChild(div);
    scrollDown();
    let dots = 1;
    const timer = setInterval(() => {{
      dots = (dots % 3) + 1;
      div.textContent = "笔墨酝酿中" + "·".repeat(dots);
    }}, 380);
    return {{ remove() {{ clearInterval(timer); div.remove(); }} }};
  }}

  function escHtml(s) {{
    return String(s).replace(/[&<>"]/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;", '"':"&quot;"}}[c]));
  }}

  function renderOptions(opts) {{
    // 移除所有旧选项组（querySelectorAll 确保全清，避免 :last-of-type 误判）
    dialogEl.querySelectorAll(".options-group").forEach(el => el.remove());
    currentOptions = opts || [];
    if (!currentOptions.length) return;

    const group = document.createElement("div");
    group.className = "options-group";
    currentOptions.forEach((opt, i) => {{
      const btn = document.createElement("button");
      btn.className = "opt-btn";
      const intentTxt = INTENT_CN[opt.intent] || opt.intent || "行动";
      const risk = opt.risk || "low";
      const riskCls = {{ low:"risk-low", medium:"risk-med", high:"risk-high" }}[risk] || "risk-med";
      const riskTxt = RISK_CN[risk] || risk;
      const mainlineBadge = opt.hint === "mainline"
        ? `<span class="opt-mainline">主线建议</span>`
        : "";
      btn.innerHTML =
        `<span class="opt-idx">${{i + 1}}</span>` +
        `<span class="opt-text">${{escHtml(opt.text || "")}}${{mainlineBadge}}</span>` +
        `<span class="opt-meta ${{riskCls}}">${{escHtml(intentTxt)}}·风险${{escHtml(riskTxt)}}</span>`;
      btn.addEventListener("click", () => submitAction(opt.text || String(i + 1)));
      group.appendChild(btn);
    }});
    dialogEl.appendChild(group);
    scrollDown();
  }}

  async function typewriter(el, text) {{
    const chunks = text.split(/([。！？…\\n])/).filter(Boolean);
    let acc = "";
    for (const c of chunks) {{
      acc += c;
      el.textContent = acc;
      scrollDown();
      await new Promise(r => setTimeout(r, 40));
    }}
    el.textContent = text;
  }}

  function scrollDown() {{
    dialogEl.scrollTop = dialogEl.scrollHeight;
  }}

  /* ══════════════════════════════════════════════════════════
     网络请求
  ══════════════════════════════════════════════════════════ */
  async function postJson(path, body) {{
    const r = await fetch(path, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(body)
    }});
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }}

  async function getJson(path) {{
    const r = await fetch(path, {{ cache: "no-store" }});
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }}

  async function refreshLlmStatus() {{
    try {{
      const data = await getJson("/api/llm/status?probe=1");
      if (data.ok) {{
        setIdleStatus("在线叙事已连接：" + (data.provider || "openai-compatible") + " / " + (data.model || ""));
      }} else if (!data.configured) {{
        setIdleStatus("未配置在线叙事模型");
      }} else {{
        setIdleStatus("在线叙事未连通（" + (data.reason || "unknown") + "）");
      }}
    }} catch (e) {{
      setIdleStatus("在线叙事状态探测失败");
    }}
  }}

  function updateSkillBtns(sd) {{
    if (!sd || !sd.boss_active) return;
    const cdMap = {{ 轻功:"qg", 招架:"zg", 内功:"ng", 绝技:"jj" }};
    document.querySelectorAll(".skill-btn").forEach(b => {{
      const cd = (sd.boss_cooldowns || {{}})[ cdMap[b.dataset.skill] ] || 0;
      b.disabled = cd > 0 || busy;
      b.textContent = cd > 0 ? b.dataset.skill + "(冷" + cd + ")" : b.dataset.skill;
    }});
  }}

  function updateSkirmishBtns(sd) {{
    if (!sd || !sd.skirmish_active) return;
    const cdMap = {{ 轻功:"qg", 招架:"zg", 内功:"ng", 绝技:"jj" }};
    document.querySelectorAll(".combat-skill-btn").forEach(b => {{
      const cd = (sd.skirmish_cooldowns || {{}})[ cdMap[b.dataset.skill] ] || 0;
      b.disabled = cd > 0 || busy;
      b.textContent = cd > 0 ? b.dataset.skill + "(冷" + cd + ")" : b.dataset.skill;
    }});
  }}

  function setBusy(v) {{
    busy = v;
    const combatActive = isCombatActiveState(prevState);
    sendBtn.disabled = v || combatActive;
    inputEl.disabled = v || combatActive;
    statusEl.textContent = v ? "江湖风云变幻…" : idleStatus;
    document.querySelectorAll(".sys-btn").forEach(b => b.disabled = v);
    document.querySelectorAll(".opt-btn").forEach(b => b.disabled = v);
    document.querySelectorAll(".skill-btn").forEach(b => b.disabled = v);
    document.querySelectorAll(".combat-skill-btn").forEach(b => b.disabled = v);
    if (!v && prevState) {{
      updateSkillBtns(prevState);
      updateSkirmishBtns(prevState);
    }}
  }}

  /* ══════════════════════════════════════════════════════════
     行动提交
  ══════════════════════════════════════════════════════════ */
  async function submitAction(text) {{
    const t = (text || inputEl.value || "").trim();
    if (!t || busy) return;
    inputEl.value = "";
    addUserMsg(t);
    const wait = addWaiting();
    setBusy(true);
    try {{
      const data = await postJson("/api/submit", {{ text: t }});
      wait.remove();
      if (data.state_data) renderState(data.state_data);
      if (data.error) statusEl.textContent = data.error;
      renderSystemMessages(data.system_messages || []);
      if (shouldSuppressMainDialog(data)) {{
        clearDialogOptions();
        return;
      }}
      const narDiv = addNarration("");
      await typewriter(narDiv, data.narration || "（本回合无叙事）");
      renderOptions(data.options || []);
    }} catch (e) {{
      wait.remove();
      addNarration("本回合生成失败，请稍后重试。");
      statusEl.textContent = String(e);
    }} finally {{
      setBusy(false);
      inputEl.focus();
    }}
  }}

  async function sysCmd(cmd) {{
    if (busy) return;
    addUserMsg(cmd);
    const wait = addWaiting();
    setBusy(true);
    try {{
      const data = await postJson("/api/submit", {{ text: cmd }});
      wait.remove();
      if (cmd === "/reset") {{
        resetDialogSurface();
      }}
      if (data.state_data) renderState(data.state_data);
      renderSystemMessages(data.system_messages || []);
      addNarration(data.narration || "");
      renderOptions(data.options || []);
    }} catch (e) {{
      wait.remove();
      addNarration("操作失败。");
    }} finally {{
      setBusy(false);
      inputEl.focus();
    }}
  }}

  async function exportStory() {{
    if (busy) return;
    setBusy(true);
    try {{
      const data = await postJson("/api/export", {{}});
      const txt = String(data.story_text || "");
      if (!txt.trim()) {{
        addNarration("暂无可导出的故事内容。");
        return;
      }}
      const blob = new Blob([txt], {{ type: "text/plain;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "storyweaver_jianghu_story.txt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      statusEl.textContent = "故事已导出。";
    }} catch (e) {{
      addNarration("导出失败，请稍后重试。");
      statusEl.textContent = String(e);
    }} finally {{
      setBusy(false);
    }}
  }}

  function confirmReset() {{
    if (confirm("确定要重开新档？当前进度将丢失。")) sysCmd("/reset");
  }}

  /* ══════════════════════════════════════════════════════════
     Boss 战
  ══════════════════════════════════════════════════════════ */
  async function bossStart() {{
    if (busy) return;
    const wait = addWaiting();
    setBusy(true);
    try {{
      const data = await postJson("/api/boss/start", {{}});
      wait.remove();
      if (data.state_data) renderState(data.state_data);
      renderSystemMessages(data.system_messages || []);
      if (shouldSuppressMainDialog(data)) {{
        clearDialogOptions();
        return;
      }}
      const narDiv = addNarration("");
      await typewriter(narDiv, data.narration || data.message || "");
      renderOptions(data.options || []);
    }} catch (e) {{
      wait.remove();
      addNarration("开启Boss战失败。");
    }} finally {{
      setBusy(false);
    }}
  }}

  document.querySelectorAll(".skill-btn").forEach(b => {{
    b.addEventListener("click", async () => {{
      if (busy) return;
      const wait = addWaiting();
      setBusy(true);
      try {{
        const data = await postJson("/api/boss/skill", {{ skill: b.dataset.skill }});
        wait.remove();
        if (data.state_data) renderState(data.state_data);
        renderSystemMessages(data.system_messages || []);
        if (shouldSuppressMainDialog(data)) {{
          clearDialogOptions();
          return;
        }}
        const narDiv = addNarration("");
        await typewriter(narDiv, data.narration || data.message || "");
        renderOptions(data.options || []);
      }} catch (e) {{
        wait.remove();
        addNarration("技能操作失败。");
      }} finally {{
        setBusy(false);
      }}
    }});
  }});

  document.querySelectorAll(".combat-skill-btn").forEach(b => {{
    b.addEventListener("click", async () => {{
      if (busy) return;
      const wait = addWaiting();
      setBusy(true);
      try {{
        const data = await postJson("/api/skirmish/skill", {{ skill: b.dataset.skill }});
        wait.remove();
        if (data.state_data) renderState(data.state_data);
        renderSystemMessages(data.system_messages || []);
        if (shouldSuppressMainDialog(data)) {{
          clearDialogOptions();
          return;
        }}
        const narDiv = addNarration("");
        await typewriter(narDiv, data.narration || data.message || "");
        renderOptions(data.options || []);
      }} catch (e) {{
        wait.remove();
        addNarration("遭遇战操作失败。");
      }} finally {{
        setBusy(false);
      }}
    }});
  }});

  /* ══════════════════════════════════════════════════════════
     绑定事件
  ══════════════════════════════════════════════════════════ */
  sendBtn.addEventListener("click",  () => submitAction(inputEl.value));
  inputEl.addEventListener("keydown", e => {{
    if (e.key === "Enter") {{ submitAction(inputEl.value); return; }}
    // 数字键快捷选项（输入框为空时）
    if (!inputEl.value && e.key >= "1" && e.key <= "9") {{
      const idx = parseInt(e.key) - 1;
      if (currentOptions[idx]) {{ e.preventDefault(); submitAction(currentOptions[idx].text || e.key); }}
    }}
  }});

  /* ══════════════════════════════════════════════════════════
     初始化
  ══════════════════════════════════════════════════════════ */
  renderState({init_sd_json});
  renderSystemMessages({init_system_json});
  addNarration({init_story_js});
  renderOptions({init_opt_json});
  inputEl.focus();
  refreshLlmStatus();
</script>
</body>
</html>
"""
    resp = HTMLResponse(
        content=page,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
    _set_session_cookie(resp, session_id)
    return resp


# ─── API 端点 ─────────────────────────────────────────────────────────────────

@app.get("/api/llm/status")
def api_llm_status(request: Request, probe: int = 0) -> JSONResponse:
  session_id = _get_session_id(request)
  engine, engine_lock = _get_session_engine(session_id)
  with engine_lock:
    data = engine.llm_status(probe=bool(probe))
  resp = JSONResponse(data)
  _set_session_cookie(resp, session_id)
  return resp

@app.post("/api/submit")
async def api_submit(req: ActionRequest, request: Request) -> JSONResponse:
  session_id = _get_session_id(request)
  engine, engine_lock = _get_session_engine(session_id)
  save_slot = f"{session_id}_slot1"
  text = (req.text or "").strip()

  if not text:
    with engine_lock:
      return JSONResponse(
        {
          "narration": "请输入行动。",
          "options": [],
          "state_data": _get_state_data(engine),
          "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
          "error": "请输入行动。",
        }
      )

  with engine_lock:
    if text == "/save":
      p = engine.save(save_slot)
      return JSONResponse(
        {
          "narration": f"已保存到 {p}",
          "options": [],
          "state_data": _get_state_data(engine),
          "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
          "error": "",
        }
      )
    if text == "/load":
      ok = engine.load(save_slot)
      loaded_opts = list(engine.state.last_options or []) if ok else []
      return JSONResponse(
        {
          "narration": "读取成功，已恢复上次进度。" if ok else "未找到存档。",
          "options": loaded_opts,
          "system_messages": [],
          "state_data": _get_state_data(engine),
          "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
          "error": "",
        }
      )
    if text == "/reset":
      engine.reset()
      opening_turn = engine.opening_scene()
      return JSONResponse(
        {
          "narration": str(opening_turn.get("narration") or "已重开新档。江湖再度展开…"),
          "options": opening_turn.get("options") or [],
          "system_messages": opening_turn.get("system_messages") or [],
          "state_data": _get_state_data(engine),
          "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
          "error": "",
        }
      )

  try:
    turn, sd = await asyncio.to_thread(_step_threadsafe, engine, engine_lock, text)
  except Exception as e:
    with engine_lock:
      fallback = {
        "id": "o1",
        "text": "继续探索周边",
        "intent": "explore",
        "target": None,
        "risk": "medium",
      }
      return JSONResponse(
        {
          "narration": "本回合生成暂时失败，请重试。",
          "options": [fallback],
          "system_messages": [],
          "state_data": _get_state_data(engine),
          "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
          "error": str(e),
        }
      )

  scene_mode = _scene_mode_from_state_data(sd)
  resp = JSONResponse(
    {
      "narration": turn.get("narration", ""),
      "options": turn.get("options", []),
      "system_messages": turn.get("system_messages", []),
      "state_data": sd,
      "scene_mode": scene_mode,
      "error": "",
    }
  )
  _set_session_cookie(resp, session_id)
  return resp


@app.post("/api/boss/start")
def api_boss_start(request: Request) -> JSONResponse:
  session_id = _get_session_id(request)
  engine, engine_lock = _get_session_engine(session_id)
  with engine_lock:
    ok, msg = engine.start_boss_fight()
    narration = "【终章 Boss】" + msg + ("\n请使用技能按钮出招。" if ok else "")
    resp = JSONResponse(
      {
        "narration": narration,
        "options": [],
        "system_messages": [],
        "state_data": _get_state_data(engine),
        "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
        "error": "",
      }
    )
    _set_session_cookie(resp, session_id)
    return resp


@app.post("/api/boss/skill")
def api_boss_skill(req: SkillRequest, request: Request) -> JSONResponse:
  session_id = _get_session_id(request)
  engine, engine_lock = _get_session_engine(session_id)
  with engine_lock:
    turn = engine.boss_skill_action(req.skill)
    resp = JSONResponse(
      {
        "narration": str(turn.get("narration") or ""),
        "options": turn.get("options") or [],
        "system_messages": turn.get("system_messages") or [],
        "state_data": _get_state_data(engine),
        "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
        "error": "",
      }
    )
    _set_session_cookie(resp, session_id)
    return resp


@app.post("/api/skirmish/skill")
def api_skirmish_skill(req: SkillRequest, request: Request) -> JSONResponse:
  session_id = _get_session_id(request)
  engine, engine_lock = _get_session_engine(session_id)
  with engine_lock:
    turn = engine.skirmish_skill_action(req.skill)
    resp = JSONResponse(
      {
        "narration": str(turn.get("narration") or ""),
        "options": turn.get("options") or [],
        "system_messages": turn.get("system_messages") or [],
        "state_data": _get_state_data(engine),
        "scene_mode": _scene_mode_from_state_data(_get_state_data(engine)),
        "error": "",
      }
    )
    _set_session_cookie(resp, session_id)
    return resp


@app.post("/api/export")
def api_export_story(request: Request) -> JSONResponse:
    session_id = _get_session_id(request)
    engine, engine_lock = _get_session_engine(session_id)
    with engine_lock:
        resp = JSONResponse({"story_text": engine.export_story()})
        _set_session_cookie(resp, session_id)
        return resp


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    raw_port = os.getenv("APP_PORT") or os.getenv("PORT") or "7865"
    try:
        preferred_port = int(raw_port)
    except ValueError:
        preferred_port = 7865
    port = _pick_available_port(host, preferred_port)
    if port != preferred_port:
        print(f"端口 {preferred_port} 已被占用，自动切换到 {port}。")
    uvicorn.run("app_web:app", host=host, port=port, reload=False)
