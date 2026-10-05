#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""占位符/格式符一致性检查（启发式，配合人工复核）。

用法:
  python qa_placeholders.py seg.tsv            # 两列: 原文<TAB>译文
  python qa_placeholders.py seg.jsonl          # {"src": "...", "tgt": "..."}
  python qa_placeholders.py seg.tsv --extra "<[^>]+>"

退出码: 0=无异常, 1=有异常, 2=用法错误
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import argparse, json, re, sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_PATTERNS = [
    r"%\d+\$[sd]",                       # %1$s
    r"%[sd]",                            # %s %d
    r"%\([A-Za-z_]\w*\)[sd]",            # %(name)s
    r"\{\{[^{}]*\}\}",                 # {{var}}
    r"\{[^{}]*\}",                      # {0} {name}
    r"\$\{[^}]+\}",                      # ${var}
    r"\$[A-Za-z_]\w*",                   # $var
    r"\\n", r"\\t",                    # \n \t
    r"&\w",                              # &File 快捷键标记
    r"\[\[[^\]]*\]\]",                  # [[key]] 本地化 key
    r"<[^/>][^>]*>|</[^>]+>",             # <b> </b> 标签
]


def load(path):
    rows = []
    if path.lower().endswith(".jsonl"):
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            rows.append((i, str(o.get("src", "")), str(o.get("tgt", ""))))
    else:
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"[warn] 第 {i} 行缺少制表符, 已跳过")
                continue
            rows.append((i, parts[0], parts[1]))
    return rows


def extract(text, pats):
    out = []
    for p in pats:
        out += re.findall(p, text)
    return sorted(out)


def disp(items):
    return [x.replace("\\", "\\\\") for x in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--extra", action="append", default=[], help="追加自定义正则（可多次）")
    a = ap.parse_args()
    pats = DEFAULT_PATTERNS + a.extra
    bad = 0
    total = 0
    for i, src, tgt in load(a.file):
        total += 1
        cs, ct = Counter(extract(src, pats)), Counter(extract(tgt, pats))
        if cs != ct:
            bad += 1
            only_s = list((cs - ct).elements())
            only_t = list((ct - cs).elements())
            print(f"行 {i}: 占位符不一致")
            if only_s:
                print(f"    原文有而译文缺: {disp(only_s)}")
            if only_t:
                print(f"    译文多出: {disp(only_t)}")
    print("---")
    print(f"检查 {total} 条, 异常 {bad} 条" + ("\n❌ 有占位符差异, 请修复" if bad else "\n✅ 全部一致"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
