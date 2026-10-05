#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零和谐检查：敏感语汇的“替换/删除/淡化”侦测（启发式，配合人工复核）。

用法:
  python qa_harmony.py seg.tsv harmony.json
  # harmony.json 形如: {"map": [{"src": ["fuck", "shit"], "tgt": ["操", "妈的", "狗屎"]}, ...]}
  # 省略配置文件时使用内置演示词表（仅示意, 请自定义）

逻辑: 原文命中某组敏感词, 而译文完全不含该组允许的对应表达 → 疑似软化/删除（Major）。
      译文命中数 < 原文命中数 → 提示力度可能不足（仅供参考）。
退出码: 0=无 Major 问题, 1=有疑似软化, 2=用法错误
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import json, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEMO = {"map": [
    {"src": ["fuck", "fucking", "fucked", "shit", "bullshit", "bastard"],
     "tgt": ["操", "艹", "他妈", "妈的", "干", "草", "狗屎", "屎", "混蛋", "王八蛋", "屁"]},
    {"src": ["damn", "damn it"],
     "tgt": ["该死", "见鬼", "妈的"]},
]}


def load_segs(path):
    rows = []
    if path.lower().endswith(".jsonl"):
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if line:
                o = json.loads(line)
                rows.append((i, str(o.get("src", "")), str(o.get("tgt", ""))))
    else:
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                rows.append((i, parts[0], parts[1]))
    return rows


def count_hits(text, words):
    low = text.casefold()
    c = 0
    for w in words:
        c += low.count(w.casefold())
    return c


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    segs = load_segs(sys.argv[1])
    if len(sys.argv) >= 3:
        cfg = json.load(open(sys.argv[2], encoding="utf-8"))
    else:
        cfg = DEMO
        print("[note] 未提供配置文件, 使用内置演示词表（请按项目自定义 harmony.json）")
    groups = cfg.get("map", [])
    majors, minors = 0, 0
    for ln, src, tgt in segs:
        for g in groups:
            sc = count_hits(src, g["src"])
            tc = count_hits(tgt, g["tgt"])
            if sc > 0 and tc == 0:
                majors += 1
                print(f"行 {ln}: 疑似软化/删除 —— 原文敏感词命中 {sc} 处, 译文未见对应表达")
                print(f"    原文: {src}")
                print(f"    译文: {tgt}")
            elif sc > 0 and 0 < tc < sc:
                minors += 1
                print(f"行 {ln}: 力度可能不足（原文 {sc} 处 → 译文 {tc} 处, 仅供参考）")
    print("---")
    print(f"疑似软化 {majors} 处, 力度提示 {minors} 处"
          + ("\n❌ 请回退补译（换模型/拆句/占位符技术）" if majors else "\n✅ 未发现零和谐问题"))
    return 1 if majors else 0


if __name__ == "__main__":
    sys.exit(main())
