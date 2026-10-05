# -*- coding: utf-8 -*-
"""从 tasks.jsonl + done.jsonl 生成 EN→CN 对照表（人工复核用）

用法: python build_table.py（在脚本同目录生成 翻译对照表.txt）
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import json, os, sys, io, collections, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
BASE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(BASE, "tasks.jsonl")
DONE = os.path.join(BASE, "done.jsonl")
OUT = os.path.join(BASE, "翻译对照表.txt")

# load tasks
tasks = []
for line in open(TASKS, encoding='utf-8'):
    tasks.append(json.loads(line))

# load done (last wins per id)
done = {}
for line in open(DONE, encoding='utf-8'):
    try:
        d = json.loads(line)
        done[d['id']] = d['cn']
    except Exception:
        pass

SEP = "─" * 78

def clean_cn(s):
    s = s.strip()
    s = re.sub(r'^>\s?', '', s)
    s = re.sub(r'^-\s?', '', s)
    return s

lines = []
lines.append("全量重译对照表（EN → CN）")
lines.append("引擎: 本地混元 HY-MT1.5-7B | 生成: 2026-08-07 | 总计: %d 条" % len(tasks))
lines.append("")
lines.append("字段说明: kind=loc 词条 / kind=subseg 字幕段（prefix=时间轴标记）")

n_missing = 0
for t in tasks:
    cn = clean_cn(done.get(t['id'], ''))
    if not cn:
        n_missing += 1
        cn = "（缺失）"
    if t['kind'] == 'loc':
        loc = "%s | %s" % (t['file'], t['key'])
        lines.append("【%05d】loc | %s" % (t['id'], loc))
        lines.append("  EN: %s" % t['text'])
        lines.append("  CN: %s" % cn)
    else:
        loc = "%s | %s" % (t['file'], t['path'][-1] if t['path'] else '?')
        lines.append("【%05d】subseg | %s" % (t['id'], loc))
        lines.append("  TAG: %s" % (t['prefix'] if t.get('prefix') else '(无)'))
        lines.append("  EN: %s" % t['text'])
        lines.append("  CN: %s" % cn)
    lines.append(SEP)

# stats
n_loc = sum(1 for t in tasks if t['kind'] == 'loc')
n_sub = len(tasks) - n_loc
lines[1] += " | 词条 %d / 字幕段 %d | 缺失译文 %d" % (n_loc, n_sub, n_missing)

with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
    fh.write("\n".join(lines) + "\n")

print("written:", OUT)
print("lines:", len(lines), "| loc:", n_loc, "| subseg:", n_sub, "| missing cn:", n_missing)
import os as _os
print("size:", _os.path.getsize(OUT), "bytes")
