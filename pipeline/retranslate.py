# -*- coding: utf-8 -*-
"""批量重译管线: build(建任务) -> translate(翻译,断点续传) -> writeback(写回)

用法:
  python retranslate.py build
  python retranslate.py translate                  # 需本地模型端点（LLM_ENDPOINT，默认 8080）
  MOD_DIR="<你的mod目录>" python retranslate.py writeback
  python retranslate.py all                        # build + translate

写回保持原文件格式（缩进/BOM/换行），cn/tc 双写（tc = OpenCC s2t）。
作者: AI 助手「苍娜」(Hermes Agent)｜人类监督: niuniujun2-ctrl
"""
import json, os, sys, io, re, time, urllib.request, collections, threading
from concurrent.futures import ThreadPoolExecutor
from opencc import OpenCC

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.abspath(__file__))
MOD = os.environ.get("MOD_DIR", "")   # 写回目标（你的 mod / 文本目录），建议用环境变量传入
CORPUS = os.path.join(BASE, "corpus.jsonl")
TASKS = os.path.join(BASE, "tasks.jsonl")
DONE = os.path.join(BASE, "done.jsonl")
FAILED = os.path.join(BASE, "failed.jsonl")
LOG = os.path.join(BASE, "translate_progress.log")

s2t = OpenCC('s2t')

# 术语表（按你的项目修改；示例如下）
GLOSSARY = ("Terminology (keep consistent): "
            "The Constant=永恒常量; Silent Assassin=沉默刺客; The Maelstrom=大漩涡; Diana=戴安娜")

SYSTEM = ("You are a professional game localization translator. Translate each English line into "
          "natural simplified Chinese. " + GLOSSARY + ". "
          "Preserve HTML tags, placeholders (like %s, {0}), brackets and all formatting exactly. "
          "Keep character/place names transliterated consistently. "
          "The input is numbered lines. Reply with the same line numbers, one translation per line, no extra text.")

ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://127.0.0.1:8080/v1/chat/completions")
BATCH = 25
CONCURRENCY = 4
MAX_RETRY = 3

SEG_RE = re.compile(r'(//(?:\[[^\]]*\]|\([^)]*\))\\\\)')

LANG_NAMES = set("Japanese English French German Spanish Italian Portuguese Russian Chinese Traditional Simplified "
                 "日本語 英语 法语 德语 西班牙语 意大利语 葡萄牙语 俄语 中文 简体中文 繁體中文 韩语 韩国语")

def is_proper_noun(s):
    s = s.strip()
    if not s:
        return True
    if re.fullmatch(r'[A-Z0-9 ™®:&()\[\]\.\-\'’/\\ %$#+*_~!?，。、·•]+', s):
        return True
    words = re.findall(r'[A-Za-z]+', s)
    if words and all(w.isupper() for w in words) and len(''.join(words)) >= 5:
        return True
    if re.search(r'[\u4e00-\u9fff]', s) and len(s) <= 16:
        toks = re.split(r'[–—\-()（）、，,\s]+', s)
        if all(t in LANG_NAMES or not re.search(r'[\u4e00-\u9fff]', t) for t in toks if t):
            return True
    return False

def should_skip(en):
    if not isinstance(en, str) or not en.strip():
        return True
    if not re.search(r'[A-Za-z]', en):
        return True
    if is_proper_noun(en):
        return True
    return False

def split_subtitle(s):
    parts = SEG_RE.split(s)
    segs = []
    cur = ''
    for p in parts:
        if p == '':
            continue
        if SEG_RE.fullmatch(p):
            cur += p
        else:
            segs.append((cur, p))
            cur = ''
    if cur and not segs:
        segs.append((cur, ''))
    return segs

def join_subtitle(segs):
    return ''.join(pre + txt for pre, txt in segs)

# ---------------- build ----------------
def build_tasks():
    n = 0
    with open(TASKS, 'w', encoding='utf-8') as out:
        with open(CORPUS, encoding='utf-8') as fh:
            for line in fh:
                rec = json.loads(line)
                file = rec['file']
                path = rec['path']
                en = rec['langs'].get('en')
                if rec['kind'] == 'loc':
                    cn = rec['langs'].get('cn') or {}
                    for key, ev in (en.items() if isinstance(en, dict) else []):
                        if should_skip(ev):
                            continue
                        task = {"id": n, "kind": "loc", "file": file, "path": path, "key": key, "text": ev}
                        out.write(json.dumps(task, ensure_ascii=False) + '\n')
                        n += 1
                else:
                    if not isinstance(en, str) or not en.strip():
                        continue
                    segs = split_subtitle(en)
                    for i, (pre, txt) in enumerate(segs):
                        if not txt.strip():
                            continue
                        task = {"id": n, "kind": "subseg", "file": file, "path": path,
                                "seg": i, "prefix": pre, "text": txt}
                        out.write(json.dumps(task, ensure_ascii=False) + '\n')
                        n += 1
    print("tasks:", n, "->", TASKS)

# ---------------- translate ----------------
def load_done():
    done = {}
    if os.path.exists(DONE):
        with open(DONE, encoding='utf-8') as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    done[d['id']] = d['cn']
                except Exception:
                    pass
    return done

def call_batch(items):
    user = "\n".join("%d. %s" % (it['id'], it['text']) for it in items)
    body = json.dumps({
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "temperature": 0.3, "top_k": 20, "top_p": 0.6, "max_tokens": 2048,
    }).encode('utf-8')
    req = urllib.request.Request(ENDPOINT, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        d = json.load(resp)
    content = d['choices'][0]['message']['content'].strip()
    out = {}
    for line in content.splitlines():
        m = re.match(r'^\s*(\d+)[.)、:：]?\s*(.*)$', line)
        if m:
            out[int(m.group(1))] = m.group(2).strip()
    return out

def _try_batch(items):
    last = None
    for attempt in range(3):
        try:
            res = call_batch(items)
            missing = [it['id'] for it in items if it['id'] not in res]
            if not missing:
                return res
            last = RuntimeError('missing ids: %s' % missing[:5])
        except Exception as e:
            last = e
        time.sleep(3 * (attempt + 1))
    return None

def translate_batch_with_retry(items):
    """Translate batch; on missing ids (usually output truncation), recursively split."""
    res = _try_batch(items)
    if res is not None:
        return res
    if len(items) <= 1:
        raise RuntimeError('single item failed: %s' % items[0]['text'][:50])
    mid = len(items) // 2
    out = {}
    for half in (items[:mid], items[mid:]):
        out.update(translate_batch_with_retry(half))
    return out

def run_translation():
    tasks = []
    with open(TASKS, encoding='utf-8') as fh:
        for line in fh:
            tasks.append(json.loads(line))
    done = load_done()
    pending = [t for t in tasks if t['id'] not in done]
    total = len(tasks)
    print("total tasks: %d, done: %d, pending: %d" % (total, len(done), len(pending)))
    if not pending:
        print("nothing to do")
        return

    lock = threading.Lock()
    state = {'done': len(done)}
    started = time.time()
    logf = open(LOG, 'a', encoding='utf-8')

    def worker(chunk):
        try:
            res = translate_batch_with_retry(chunk)
        except Exception as e:
            with lock:
                with open(FAILED, 'a', encoding='utf-8') as ff:
                    for it in chunk:
                        ff.write(json.dumps(it, ensure_ascii=False) + '\n')
                print("batch failed (%d tasks): %s" % (len(chunk), e))
            return
        with lock:
            with open(DONE, 'a', encoding='utf-8') as df:
                for it in chunk:
                    df.write(json.dumps({"id": it['id'], "cn": res.get(it['id'], '')}, ensure_ascii=False) + '\n')
            state['done'] += len(chunk)
            elapsed = time.time() - started
            rate = state['done'] / elapsed if elapsed > 0 else 0
            eta = (total - state['done']) / rate / 60 if rate > 0 else 0
            msg = "progress: %d/%d (%.1f%%)  %.1f tasks/s  ETA %.0f min" % (
                state['done'], total, 100.0 * state['done'] / total, rate, eta)
            print(msg)
            logf.write(msg + '\n')
            logf.flush()

    chunks = [pending[i:i + BATCH] for i in range(0, len(pending), BATCH)]
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        list(ex.map(worker, chunks))

    pending2 = [t for t in tasks if t['id'] not in load_done()]
    if pending2:
        print("remaining %d tasks after pass 1, retrying individually..." % len(pending2))
        for t in pending2:
            try:
                res = translate_batch_with_retry([t])
                with open(DONE, 'a', encoding='utf-8') as df:
                    df.write(json.dumps({"id": t['id'], "cn": res.get(t['id'], '')}, ensure_ascii=False) + '\n')
            except Exception as e:
                with open(FAILED, 'a', encoding='utf-8') as ff:
                    ff.write(json.dumps(t, ensure_ascii=False) + '\n')
                print("FAILED task %d: %s" % (t['id'], e))
    logf.close()
    print("done. completed:", len(load_done()), "/", total)

# ---------------- write back ----------------
def detect_indent(text):
    for ln in text.splitlines()[1:]:
        m = re.match(r'^(\s+)"', ln)
        if m:
            return '\t' if '\t' in m.group(1) else m.group(1)
    return '  '

def write_json(path, data):
    raw = open(path, encoding='utf-8').read()
    indent = detect_indent(raw)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        if indent:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        else:
            json.dump(data, fh, ensure_ascii=False)
        fh.write('\n')

def clean_cn(s):
    s = s.strip()
    # strip model noise prefixes like '> ' (never part of real game text)
    s = re.sub(r'^>\s?', '', s)
    s = re.sub(r'^-\s?', '', s)
    return s

def write_back():
    if not MOD:
        print("请先设置 MOD_DIR 环境变量指向你的 mod 目录（写回目标）")
        return
    done = load_done()
    if not done:
        print("no translations to write back")
        return
    files = collections.defaultdict(list)
    with open(TASKS, encoding='utf-8') as fh:
        for line in fh:
            t = json.loads(line)
            if t['id'] in done:
                files[t['file']].append(t)

    n_loc = n_sub = 0
    for file, tasks in sorted(files.items()):
        fpath = os.path.join(MOD, file)
        data = json.load(open(fpath, encoding='utf-8'))
        # group subtitle segs by block path
        subblocks = collections.defaultdict(dict)  # (file, path_tuple) -> {seg_idx: (prefix, cn)}
        for t in tasks:
            if t['kind'] == 'loc':
                node = data
                for seg in t['path']:
                    node = node[seg]
                cn_key = None
                for cand in ("chineseSimplified", "cn"):
                    if cand in node and isinstance(node[cand], dict):
                        cn_key = cand
                        break
                if cn_key is None:
                    cn_key = "chineseSimplified"
                    node.setdefault(cn_key, {})
                node[cn_key][t['key']] = clean_cn(done[t['id']])
                tc_key = None
                for cand in ("chineseTraditional", "tc", "zh"):
                    if cand in node and isinstance(node[cand], dict):
                        tc_key = cand
                        break
                if tc_key is None:
                    tc_key = "chineseTraditional"
                    node.setdefault(tc_key, {})
                node[tc_key][t['key']] = s2t.convert(done[t['id']])
                n_loc += 1
            else:
                subblocks[(t['file'], tuple(t['path']))][t['seg']] = (t['prefix'], done[t['id']])
        # write back subtitle blocks
        if subblocks:
            for (_, path_tuple), segs in subblocks.items():
                path = list(path_tuple)
                node = data
                for seg in path:
                    node = node[seg]
                # rebuild from ORIGINAL en structure to stay safe with empty/trailing segments
                en_key = None
                for cand in ("en", "english"):
                    if cand in node and isinstance(node[cand], str):
                        en_key = cand
                        break
                if en_key is None:
                    continue
                parts = []
                for i, (pre, txt) in enumerate(split_subtitle(node[en_key])):
                    if i in segs:
                        parts.append(pre + clean_cn(segs[i][1]))
                    else:
                        parts.append(pre + txt)
                cn_str = ''.join(parts)
                cn_key = None
                for cand in ("cn", "chineseSimplified"):
                    if cand in node and isinstance(node[cand], str):
                        cn_key = cand
                        break
                if cn_key is None:
                    cn_key = "cn"
                node[cn_key] = cn_str
                tc_key = None
                for cand in ("tc", "zh", "chineseTraditional"):
                    if cand in node and isinstance(node[cand], str):
                        tc_key = cand
                        break
                if tc_key is None:
                    tc_key = "tc"
                node[tc_key] = s2t.convert(cn_str)
                n_sub += 1
        write_json(fpath, data)
    print("loc entries written:", n_loc)
    print("subtitle blocks written:", n_sub)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "build":
        build_tasks()
    elif cmd == "translate":
        run_translation()
    elif cmd == "writeback":
        write_back()
    elif cmd == "all":
        build_tasks()
        run_translation()
    else:
        print("usage: retranslate.py build|translate|writeback|all")
