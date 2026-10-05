# -*- coding: utf-8 -*-
"""提取游戏/Mod JSON 里的可翻译文本 → corpus.jsonl

支持的结构（覆盖 SMF mod 常见形态）:
  - localisation 块: {"english": {...}, "chineseSimplified": {...}, ...}
  - subtitles 块:    {"subtitles": {"en": "...", "cn": "...", ...}}
  - languages 块:    locr(key->str dict) 与 dlge(整段字幕) 两种
      注: 部分文件用 "zh" 当繁体键
用法: python extract.py <MOD目录>     （输出写在本脚本同目录）
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MOD = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()   # 待提取的 mod / 文本目录
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.jsonl")
STATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_stats.txt")

LANGS = {"english": "en", "chineseSimplified": "cn", "chineseTraditional": "tc", "japanese": "jp"}
SUBTITLE_LANGS = {"en": "en", "cn": "cn", "tc": "tc", "jp": "jp"}

records = []
stats = {"en": 0, "cn": 0, "tc": 0, "jp": 0}
chars = {"en": 0, "cn": 0, "tc": 0, "jp": 0}
files_with_text = set()
n_loc_blocks = 0
n_subtitle_blocks = 0
n_zstring = 0
errors = []


def walk(obj, file, path, out):
    global n_loc_blocks, n_subtitle_blocks, n_zstring
    if isinstance(obj, dict):
        # localisation block: {"english": {...}, "chineseSimplified": {...}, ...}
        if "english" in obj and isinstance(obj.get("english"), dict):
            langs = {k: v for k, v in LANGS.items() if isinstance(obj.get(k), dict)}
            if langs:
                n_loc_blocks += 1
                rec = {"file": file, "kind": "loc", "path": path, "langs": {}, "keynames": {}}
                for full, short in langs.items():
                    d = obj[full]
                    rec["langs"][short] = d
                    rec["keynames"][short] = full
                    stats[short] += len(d)
                    chars[short] += sum(len(str(v)) for v in d.values())
                    if d:
                        files_with_text.add(file)
                out.append(rec)
                return
        # subtitles block: {"cn": "...", "tc": "...", "jp": "..."}
        if "subtitles" in obj and isinstance(obj["subtitles"], dict):
            sub = obj["subtitles"]
            has = {k: v for k, v in SUBTITLE_LANGS.items() if k in sub and isinstance(sub[k], str)}
            if has:
                n_subtitle_blocks += 1
                rec = {"file": file, "kind": "subtitle", "path": path + ["subtitles"], "langs": {}, "keynames": {}}
                for full, short in has.items():
                    v = sub[full]
                    rec["langs"][short] = v
                    rec["keynames"][short] = full
                    stats[short] += 1
                    chars[short] += len(v)
                    files_with_text.add(file)
                out.append(rec)
                return
        # dlge languages block: {"languages": {"en": "...", "cn": "...", "tc": "...", ...}}
        # or locr block: {"languages": {"en": {...}, "cn": {...}, "tc": {...}, ...}} (key->str dicts)
        # note: some files use "zh" instead of "tc" for Traditional Chinese
        if "languages" in obj and isinstance(obj["languages"], dict):
            langs = obj["languages"]

            def pick(*keys):
                for k in keys:
                    if k in langs:
                        return k
                return None

            cn_k = pick("cn")
            tc_k = pick("tc", "zh")
            if cn_k is not None and tc_k is not None:
                cn_v, tc_v = langs[cn_k], langs[tc_k]
                if isinstance(cn_v, dict) and isinstance(tc_v, dict):
                    # locr style localisation block
                    n_loc_blocks += 1
                    rec = {"file": file, "kind": "loc", "path": path + ["languages"], "langs": {}, "keynames": {}}
                    for short in ("en", "cn", "tc", "jp"):
                        if short in langs and isinstance(langs[short], dict):
                            d = langs[short]
                            rec["langs"][short] = d
                            rec["keynames"][short] = short
                            stats[short] += len(d)
                            chars[short] += sum(len(str(v)) for v in d.values())
                            if d:
                                files_with_text.add(file)
                    out.append(rec)
                    return
                if isinstance(cn_v, str) and isinstance(tc_v, str):
                    # dlge style subtitle block
                    n_subtitle_blocks += 1
                    rec = {"file": file, "kind": "subtitle", "path": path + ["languages"], "langs": {}, "keynames": {}}
                    for short, act in (("en", "en"), ("cn", cn_k), ("tc", tc_k), ("jp", "jp")):
                        if act in langs and isinstance(langs[act], str):
                            rec["langs"][short] = langs[act]
                            rec["keynames"][short] = act
                            stats[short] += 1
                            chars[short] += len(langs[act])
                            files_with_text.add(file)
                    out.append(rec)
                    return
        # ZString typed properties (stats only, not in corpus)
        if obj.get("type") == "ZString" and isinstance(obj.get("value"), str):
            n_zstring += 1
        for k, v in obj.items():
            if k == "subtitles":
                continue
            walk(v, file, path + [k], out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, file, path + [i], out)


json_files = []
for dp, dn, fn in os.walk(MOD):
    for f in fn:
        if f.endswith(".json"):
            json_files.append(os.path.join(dp, f))

for fp in json_files:
    rel = os.path.relpath(fp, MOD)
    try:
        with open(fp, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        errors.append((rel, str(e)))
        continue
    walk(data, rel, [], records)

with open(OUT, "w", encoding="utf-8") as fh:
    for rec in records:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

with open(STATS, "w", encoding="utf-8") as fh:
    fh.write("json files: %d\n" % len(json_files))
    fh.write("parse errors: %d\n" % len(errors))
    for e in errors[:20]:
        fh.write("  ERR %s: %s\n" % (e[0], e[1]))
    fh.write("loc blocks: %d\n" % n_loc_blocks)
    fh.write("subtitle blocks: %d\n" % n_subtitle_blocks)
    fh.write("zstring props: %d\n" % n_zstring)
    fh.write("files with text: %d\n" % len(files_with_text))
    fh.write("records total: %d\n" % len(records))
    for lang in ("en", "cn", "tc", "jp"):
        fh.write("  %s: entries=%d chars=%d\n" % (lang, stats[lang], chars[lang]))

print("done: %d records -> %s" % (len(records), OUT))
print("stats:", stats)
print("chars:", chars)
print("files:", len(json_files), "errors:", len(errors))
