#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""术语表一致性检查（启发式，配合人工复核）。

用法:
  python qa_terms.py seg.tsv glossary.tsv
    seg.tsv      : 两列 原文<TAB>译文
    glossary.tsv : 两列 源术语<TAB>目标译词（# 开头行忽略）

逻辑: 原文包含源术语（忽略大小写）时, 译文必须包含对应译词, 否则记一条违规。
退出码: 0=无异常, 1=有异常, 2=用法错误
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_pairs(path):
    rows = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            print(f"[warn] {path} 第 {i} 行缺少制表符, 已跳过")
            continue
        rows.append((i, parts[0].strip(), parts[1].strip()))
    return rows


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    seg_file, gloss_file = sys.argv[1], sys.argv[2]
    segs = load_pairs(seg_file)
    gloss = load_pairs(gloss_file)
    used = {gi: 0 for gi in range(len(gloss))}
    violations = []
    checked = 0
    for ln, src, tgt in segs:
        low = src.casefold()
        for gi, (_, st, tt) in enumerate(gloss):
            if not st or not tt:
                continue
            if st.casefold() in low:
                checked += 1
                used[gi] += 1
                if tt not in tgt:
                    violations.append((ln, st, tt, src, tgt))
    for ln, st, tt, src, tgt in violations:
        print(f"行 {ln}: 术语 [{st} -> {tt}] 未按表译出")
        print(f"    原文: {src}")
        print(f"    译文: {tgt}")
    unused = [st for gi, (_, st, _tt) in enumerate(gloss) if used[gi] == 0]
    print("---")
    print(f"含术语句段 {checked} 处, 违规 {len(violations)} 处"
          + ("\n❌ 术语不一致" if violations else "\n✅ 术语全部命中"))
    if unused:
        print(f"未使用术语（供参考, 可能本项目无涉及）: {unused}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
