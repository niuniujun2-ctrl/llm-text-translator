# llm-text-translator —— 本地 LLM 批量翻译管线（游戏 / Mod 文本）

> 🤖 本仓库的代码与文档由 **AI 编写**（AI 助手「苍娜」，运行于 Hermes Agent）；人类作者负责需求、验收与发布。详见「关于本项目」。

用**本地大模型**（llama.cpp + 腾讯混元 HY-MT1.5-7B，或任意 OpenAI 兼容端点）批量翻译
游戏 / Mod 的 JSON 文本。零 token 成本、可复现、带质量门：

```
extract.py  →  corpus.jsonl  →  quality_check.py  →  retranslate.py  →  build_table.py
（提取语料）     （全量记录）      （规则质检）        build→translate→writeback   （对照表）
```

出自真实项目：HITMAN「Better Localisation」SMF mod 约 **2.8 万条**文本的全量重译与质控
（本仓库为提炼后的通用版本）。

## 环境

```bash
pip install -r requirements.txt     # OpenCC（繁简检测/转换）
# 另需一个 OpenAI 兼容的本地模型端点（llama.cpp 推荐，见 docs/pipeline-guide.md §1）
```

## 快速开始

```bash
# 1. 提取：指向要翻译的 mod / 游戏文本目录（输出在脚本同目录）
python pipeline/extract.py "D:/.../Mods/YourMod"

# 2. 质检：先看语料里的既有问题（简繁混杂 / 占位符 / 空译 / 乱码…）
python pipeline/quality_check.py

# 3. 翻译：build 任务 → translate（断点续传）→ writeback（写回 + 简繁双写）
python pipeline/retranslate.py build
python pipeline/retranslate.py translate         # 需要本地模型服务在 8080
MOD_DIR="D:/.../Mods/YourMod" python pipeline/retranslate.py writeback

# 4. 复检 + 对照表
python pipeline/quality_check.py                 # 写回后重跑
python pipeline/build_table.py                   # → 翻译对照表.txt
```

独立质检器（吃任意「原文<TAB>译文」TSV 或 `{"src","tgt"}` JSONL）：

```bash
python qa/qa_placeholders.py seg.tsv             # 占位符/格式符一致性
python qa/qa_terms.py         seg.tsv gloss.tsv  # 术语表一致性
python qa/qa_harmony.py       seg.tsv            # 零和谐（软化/删改检测）
python qa/qa_subtitle.py      subs.srt           # 字幕行宽/CPS/时长/间隔
```

## 设计要点（为什么这样做）

- **行号协议**：输入 `1. <text>`、输出 `1. <译文>`，比 JSON 数组回显稳；按行号解析。
- **递归拆分**：长批会静默漏行（截断）——发现缺号就把该批对半拆，直到成功。
- **断点续传**：每批落盘 `done.jsonl`（last-wins 去重），随崩随续。
- **格式保持**：写回时保持原缩进（tab/空格探测）、BOM、换行风格；cn/tc 双写（tc = s2t）。
- **术语先行**：system prompt 内嵌术语表（改 `retranslate.py` 的 `GLOSSARY`）。
- **模型噪声清洗**：`> `、`- ` 前缀等习惯性噪声统一清掉。

## 局限与注意

- 当前配置为「英 → 中」示例；换语言对改 `SYSTEM` / `GLOSSARY` 即可。
- 这不是「一键汉化」：不同游戏的文本载体千差万别，**提取与写回两端通常要按项目适配**——
  本仓库给出的是经实战验证的骨架、协议与规则。载体解包/回封工具地图见
  `docs/汉化全类型资料.md`。

## 文档

- [`docs/pipeline-guide.md`](docs/pipeline-guide.md) —— 管线细节、模型配置、质量门与坑全集
- [`docs/汉化全类型资料.md`](docs/汉化全类型资料.md) —— 各引擎汉化的载体与工具地图

## 许可

MIT（见 LICENSE）。

## 关于本项目

- **本仓库代码与文档由 AI 编写**：管线脚本、质检器、文档与全部验证由 AI 助手 **苍娜**
  （运行于 Hermes Agent）完成。
- 人类作者 [@niuniujun2-ctrl](https://github.com/niuniujun2-ctrl) 负责提出需求、验收与发布。
- 已在 HITMAN SMF 汉化项目（约 2.8 万条文本、多轮全量重译）上完整使用并验证。
