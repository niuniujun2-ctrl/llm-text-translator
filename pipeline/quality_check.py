# -*- coding: utf-8 -*-
"""规则级质检 —— 输出高精度的疑似问题清单（供人工复核）

检查项: 简繁混杂（含豁免表）、真·未翻译残留（排除专名）、常见错字、
空译/漏译、长文本 cn==tc、高风险 %/{} 占位符不匹配、乱码。

用法: python quality_check.py [corpus.jsonl]   （默认读脚本同目录的 corpus.jsonl）
依赖: opencc（pip install opencc-python-reimplemented）
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import json, os, re, sys, io, collections
from opencc import OpenCC

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "corpus.jsonl")
OUT_ISSUES = os.path.join(BASE, "issues_rule_v2.jsonl")
OUT_SUMMARY = os.path.join(BASE, "issues_summary_v2.txt")

s2t = OpenCC('s2t')
t2s = OpenCC('t2s')

# chars where simplified<->traditional conversion is a dialect/orthographic
# variant or multi-meaning char, NOT an error when seen in the other script.
EXEMPT = set("台秘群里托干吃才游了家升床借峰布欲郁余后面发复尽占只表冲斗谷术系回万卫无须选阳叶云赞证制种筑准走组范吊杰仆朴气确舍绳团王于苏志几价据历炼盘划汇伙克卷夸礼曲胜并复几")

# conservative typo patterns
TYPO_PATTERNS = [
    (r'做为', '做为->作为'),
    (r'既使', '既使->即使'),
    (r'帐号', '帐号->账号'),
    (r'座标', '座标->坐标'),
    (r'登陆', '登陆->登录(游戏语境)'),
    (r'巳经', '巳经->已经'),
    (r'以经', '以经->已经'),
    (r'什幺', '什幺->什么'),
    (r'必需[被是要有在去做得用由]', '必需+动词->必须'),
    (r'我门', '我门->我们'),
    (r'你门', '你门->你们'),
    (r'的的', '的的 重复'),
]

def ascii_alpha_ratio(s):
    letters = sum(1 for c in s if c.isascii() and c.isalpha())
    return letters / max(1, len(s))

def has_cjk(s):
    return bool(re.search(r'[\u4e00-\u9fff]', s))

def cjk_ratio(s):
    cjk = len(re.findall(r'[\u4e00-\u9fff]', s))
    return cjk / max(1, len(s))

# proper-noun-ish: value with no real sentence structure (all caps, brand, digits, language names)
LANG_NAMES = set("Japanese English French German Spanish Italian Portuguese Russian Chinese Traditional Simplified "
                 "日本語 英语 英语 法语 德语 西班牙语 意大利语 葡萄牙语 俄语 中文 简体中文 繁體中文 韩语 韩国语")

def is_proper_noun(val):
    s = val.strip()
    if not s:
        return True
    if re.fullmatch(r'[A-Z0-9 ™®:&()\[\]\.\-\'’/\\ %$#+*_~!?，。、·•]+', s):
        return True
    # mostly uppercase words or short brand-like tokens
    words = re.findall(r'[A-Za-z]+', s)
    if words and all(w.isupper() for w in words) and len(''.join(words)) >= 5:
        return True
    # language-name rows like "日本語 – 日语", "Português (Brasil)"
    if cjk_ratio(s) > 0 and len(s) <= 16:
        toks = re.split(r'[–—\-()（）、，,\s]+', s)
        if all(t in LANG_NAMES or not re.search(r'[\u4e00-\u9fff]', t) for t in toks if t):
            return True
    return False

def diff_chars(val, conv):
    """chars where conversion changed the glyph"""
    out = []
    for a, b in zip(val, conv):
        if a != b:
            out.append(a)
    return out

issues = []
stats = collections.Counter()
per_type = collections.Counter()

def add(itype, file, path, lang, key, en, value, evidence):
    issues.append({"type": itype, "file": file, "path": path, "lang": lang,
                   "key": key, "en": en, "value": value, "evidence": evidence})
    per_type[itype] += 1

def check_loc(en_val, cn_val, tc_val, file, path, key):
    stats['loc_entries'] += 1
    for lang, val in (("cn", cn_val), ("tc", tc_val)):
        if not isinstance(val, str):
            continue
        stats['%s_checked' % lang] += 1
        if not has_cjk(val):
            if (en_val is not None and isinstance(en_val, str) and en_val.strip() and not val.strip()):
                add('missing_translation', file, path, lang, key, en_val, val, 'empty cn/tc')
            # pure ASCII 且与英文原文完全相同 → 疑似未翻译（排除专名）
            elif (en_val is not None and isinstance(en_val, str) and len(en_val) >= 20
                    and val == en_val and not is_proper_noun(en_val)):
                add('untranslated_sentence', file, path, lang, key, en_val, val, 'identical to en sentence')
            continue
        # strict script mixing
        if lang == 'cn':
            conv = t2s.convert(val)
            d = [c for c in diff_chars(val, conv) if c not in EXEMPT]
            if d:
                add('tc_in_cn', file, path, lang, key, en_val, val,
                    'traditional chars in cn: %s' % ''.join(d)[:20])
        else:
            conv = s2t.convert(val)
            d = [c for c in diff_chars(val, conv) if c not in EXEMPT]
            if d:
                add('cn_in_tc', file, path, lang, key, en_val, val,
                    'simplified chars in tc: %s' % ''.join(d)[:20])
        # typos
        for pat, desc in TYPO_PATTERNS:
            if re.search(pat, val):
                add('typo', file, path, lang, key, en_val, val, desc)
                break
        # missing translation
        if en_val is not None and isinstance(en_val, str) and en_val.strip() and not val.strip():
            add('missing_translation', file, path, lang, key, en_val, val, 'empty cn/tc')
        # mojibake
        if re.search(r'[\ufffd]', val) or any(w in val for w in ('锟斤拷', '烫烫烫')):
            add('mojibake', file, path, lang, key, en_val, val, 'replacement char')
    # cn==tc for long text
    if (isinstance(cn_val, str) and isinstance(tc_val, str) and cn_val == tc_val
            and len(cn_val) >= 40 and has_cjk(cn_val)):
        add('cn_equals_tc', file, path, 'cn/tc', key, en_val, cn_val, 'identical long cn/tc')
    # high-risk placeholder mismatch (% and {}) for cn
    if isinstance(en_val, str) and isinstance(cn_val, str):
        et = (len(re.findall(r'%(?:[0-9]+\$)?[sdif]', en_val)),
              len(re.findall(r'\{[^}]*\}', en_val)))
        ct = (len(re.findall(r'%(?:[0-9]+\$)?[sdif]', cn_val)),
              len(re.findall(r'\{[^}]*\}', cn_val)))
        if et != ct:
            add('placeholder_mismatch', file, path, 'cn', key, en_val, cn_val,
                'placeholders en=%s cn=%s' % (et, ct))

with open(CORPUS, encoding='utf-8') as fh:
    for line in fh:
        rec = json.loads(line)
        file = rec['file']
        path = rec['path']
        en = rec['langs'].get('en')
        cn = rec['langs'].get('cn')
        tc = rec['langs'].get('tc')
        if rec['kind'] == 'loc':
            for key in sorted(set(list((cn or {}).keys()) + list((tc or {}).keys()))):
                check_loc(
                    en.get(key) if isinstance(en, dict) else None,
                    cn.get(key) if isinstance(cn, dict) else None,
                    tc.get(key) if isinstance(tc, dict) else None,
                    file, path, key)
        else:
            # subtitles: script mixing + typos on the whole block text
            for lang, val in (("cn", cn), ("tc", tc)):
                if not isinstance(val, str) or not has_cjk(val):
                    continue
                stats['%s_checked' % lang] += 1
                if lang == 'cn':
                    conv = t2s.convert(val)
                    d = [c for c in diff_chars(val, conv) if c not in EXEMPT]
                    if d:
                        add('tc_in_cn', file, path, lang, '<subtitles>', en, val,
                            'traditional chars in cn subtitle: %s' % ''.join(d)[:20])
                else:
                    conv = s2t.convert(val)
                    d = [c for c in diff_chars(val, conv) if c not in EXEMPT]
                    if d:
                        add('cn_in_tc', file, path, lang, '<subtitles>', en, val,
                            'simplified chars in tc subtitle: %s' % ''.join(d)[:20])
                for pat, desc in TYPO_PATTERNS:
                    if re.search(pat, val):
                        add('typo', file, path, lang, '<subtitles>', en, val, desc)
                        break

with open(OUT_ISSUES, 'w', encoding='utf-8') as fh:
    for it in issues:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')

with open(OUT_SUMMARY, 'w', encoding='utf-8') as fh:
    fh.write('loc entries checked: %d (cn=%d tc=%d)\n' % (
        stats['loc_entries'], stats['cn_checked'], stats['tc_checked']))
    fh.write('total issues: %d\n' % len(issues))
    for t, n in per_type.most_common():
        fh.write('  %-28s %d\n' % (t, n))

print('loc entries: %d' % stats['loc_entries'])
print('total issues: %d' % len(issues))
for t, n in per_type.most_common():
    print('  %-28s %d' % (t, n))
