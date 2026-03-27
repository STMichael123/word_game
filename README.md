# word_game

江湖织梦（StoryWeaver）是一个基于 LLM 的武侠文字游戏项目，采用 NLU 意图识别、状态一致性管理和 LLM 叙事生成来驱动剧情推进。

LLM 通过 OpenAI 兼容接口调用（推荐在 `.env` 中配置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`；旧的 `NVIDIA_*` / `OPENAI_*` 变量也兼容）。

默认推荐使用更大的通用文本模型，例如 `gpt-5.4`。如果你当前的服务商支持更高质量的对话模型，也建议把 `.env` 里的 `LLM_MODEL` 显式设成该模型，而不是依赖较弱或不兼容的默认名。

## 安全提醒（非常重要）

请不要把 API KEY 写进代码、README 或截图里。若密钥曾暴露，建议立刻吊销并重签。

## 功能概览

- 主线 8 章节 + 可触发支线任务，目标游玩时长约 2-3 小时
- 地点事件、江湖奇遇、战斗结果、掉落和声望变化都带随机性，并支持 seed 复现
- 规则式 NLU + 轻量实体抽取，用于理解地点、人物和物品相关输入
- 游戏状态、一致性修复、长期叙事 memory 与外置 memory 文档同步维护
- LLM 基于当前状态、本轮结果和压缩记忆生成剧情及 2~4 个下一步选项
- FastAPI + 原生 HTML/JS Web 前端，带常驻侧栏、战斗面板和状态展示

## 快速开始（Windows / PowerShell）

1) 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) 配置环境变量

- 复制 `.env.example` 为 `.env`
- 填入 `LLM_API_KEY`
- 如果你使用第三方 OpenAI 兼容服务，同时确认 `LLM_BASE_URL` 与 `LLM_MODEL` 和你的服务商一致
- 如果没有单独指定模型，项目默认会使用 `gpt-5.4`

3) 运行 Web 前端

```bash
python app_web.py
```

如果默认端口 `7865` 被占用，程序会自动切换到下一个可用端口。

## 玩法提示

- 支持自然语言输入，例如：`去客栈打听消息`、`探索后山`、`与长老谈判`
- 也支持数字选项：`1`、`2`、`3`
- 输入 `/save` 保存，`/load` 读取，`/reset` 重开
- 如果你想先看一份不剧透过头但足够实用的主线通关说明，可以直接看 [GAME_GUIDE.md](GAME_GUIDE.md)

## 项目结构

- `storyweaver/`：核心逻辑（NLU、状态、一致性、世界事件、LLM 客户端、memory 文档）
- `app_web.py`：网页入口
- `tests/`：测试用例
