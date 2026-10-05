#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕质检：行宽 / CPS / 时长 / 间隔 / 行数（SRT 与基础 VTT）。

用法:
  python qa_subtitle.py subs.srt
  python qa_subtitle.py subs.srt --max-line-width 18 --max-cps 9 --min-dur 1.0 --max-dur 6.0 --min-gap-ms 80 --max-lines 2

宽度算法: 全角=1, 半角=0.5, 空格不计（中文“每行 N 字”习惯）。
退出码: 0=通过, 1=有异常, 2=用法错误
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import argparse, re, sys, unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")


def parse_time(s):
    m = TS.search(s)
    if not m:
        return None
    h, mi, sec, ms = map(int, m.groups())
    return ((h * 60 + mi) * 60 + sec) + ms / 1000.0


def parse_subs(path):
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    blocks, cur = [], []
    for line in raw.split("\n"):
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        elif line.strip().upper() == "WEBVTT" or line.strip().startswith("NOTE"):
            continue
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)
    subs = []
    for b in blocks:
        tline = next((x for x in b if "-->" in x), None)
        if not tline:
            continue
        left, right = tline.split("-->", 1)
        st = parse_time(left)
        et = parse_time(right)
        if st is None or et is None:
            continue
        text_lines = [x for x in b if "-->" not in x and not re.fullmatch(r"\s*\d+\s*", x)]
        subs.append({"start": st, "end": et, "lines": text_lines})
    subs.sort(key=lambda x: x["start"])
    return subs


def width(s):
    s = re.sub(r"<[^>]+>", "", s)
    w = 0.0
    for ch in s:
        if ch.isspace():
            continue
        w += 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5
    return w


def fmt_t(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    mi, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{mi:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--max-line-width", type=float, default=18.0)
    ap.add_argument("--max-cps", type=float, default=9.0)
    ap.add_argument("--min-dur", type=float, default=1.0)
    ap.add_argument("--max-dur", type=float, default=6.0)
    ap.add_argument("--min-gap-ms", type=int, default=80)
    ap.add_argument("--max-lines", type=int, default=2)
    a = ap.parse_args()
    subs = parse_subs(a.file)
    if not subs:
        print("未解析到字幕条目, 请检查格式")
        return 2
    bad = 0
    prev = None
    for n, s in enumerate(subs, 1):
        issues = []
        dur = s["end"] - s["start"]
        if s["end"] <= s["start"]:
            issues.append(f"时间非法(结束≤开始)")
        if dur < a.min_dur:
            issues.append(f"时长 {dur:.2f}s < {a.min_dur}s")
        if dur > a.max_dur:
            issues.append(f"时长 {dur:.2f}s > {a.max_dur}s")
        if len(s["lines"]) > a.max_lines:
            issues.append(f"行数 {len(s['lines'])} > {a.max_lines}")
        if not any(x.strip() for x in s["lines"]):
            issues.append("空字幕")
        wids = [width(x) for x in s["lines"]]
        for w in wids:
            if w > a.max_line_width:
                issues.append(f"行宽 {w:.1f} > {a.max_line_width}")
                break
        if dur > 0:
            cps = sum(wids) / dur
            if cps > a.max_cps:
                issues.append(f"CPS {cps:.1f} > {a.max_cps}")
        if prev is not None:
            gap_ms = int(round((s["start"] - prev["end"]) * 1000))
            if gap_ms < 0:
                issues.append(f"与前一条重叠 {-gap_ms}ms")
            elif gap_ms < a.min_gap_ms:
                issues.append(f"间隔 {gap_ms}ms < {a.min_gap_ms}ms")
        prev = s
        if issues:
            bad += 1
            print(f"第 {n} 条 ({fmt_t(s['start'])}): " + " | ".join(issues))
    print("---")
    print(f"共 {len(subs)} 条, 异常 {bad} 条" + ("\n❌ 请修复后重跑" if bad else "\n✅ 全部通过"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
