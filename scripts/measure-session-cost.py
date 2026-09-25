#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
# ^ pyyaml нужен РЕЖИМУ `--journal-projection`: он зовёт И1 (`check_lesson_destiny`), а тот
# читает реестр судеб `parse_yaml_file`. До правки шапка объявляла `dependencies = []`, и
# заявленная Д2 возможность на своём же документированном пути вызова НЕ РАБОТАЛА:
#   uv run  scripts/measure-session-cost.py --journal-projection <журнал> -> ERROR: PyYAML не установлен
#   python3 scripts/measure-session-cost.py --journal-projection <журнал> -> 25 строк
# Зелёной сьюта при этом была: все тесты зовут прибор через `python3`, где системный pyyaml
# есть (ревью NA-EPIC-56, находка №4). Импорт `yaml` остаётся ЛЕНИВЫМ (внутри
# `_lesson_destiny_module`), поэтому `wave-brief.py` с `dependencies = []`, подгружающий этот
# модуль по пути, зависимость не наследует — проверено прогоном обоих приборов под `uv run`.
"""Прибор цены сессии и вердикт по бюджету — ADR-102 Д1/Д2 (NA-EPIC-52, задача DEV-448).

Единица счёта — УНИКАЛЬНЫЙ `message.id`: одно обращение к модели записано в транскрипт
несколькими строками, и каждая несёт СВОЮ копию `message.usage`. Наивная сумма по строкам
даёт 15 269 107 против 6 127 395 по обращениям (2,49x, замер §1.1 спутника ADR-102) — поэтому
здесь усушка идёт по id, а не по строкам.

Прибор и вердикт живут в ОДНОМ файле по Д1 дословно: разнеси их по двум — и правило печати
разойдётся с правилом сравнения, ровно тот дефект, что решением чинится. Профиль правила счёта
(`counting-rule`) печатается ВСЕГДА, включая отчёт без бюджета, и дословно повторяется ключом
`sessionCostBudget` (.nauta-gates.yaml); расхождение профилей — отказ сравнения, а не молчаливое
сравнение несравнимого.

Границы (§5 спутника): читает файлы и ничего не пишет; в дерево не переносит содержимое
транскриптов — только агрегаты и ГОЛОВЫ команд; вердикта по величине, которой дерево не задаёт
(вклад TTL кэша платформы, доля ходов с двумя и более инструментами), не выносит.

Разрешение сессии — три ступени §1.4: аргумент (позиционный либо `--session`) →
`$CLAUDE_CODE_SESSION_ID` → объявленный отказ. Выбора «самый свежий файл по mtime» нет ни на
одной ступени: это то же необъявленное правило счёта, только спрятанное глубже.

Коды — объявленная ЧЕТВЁРКА (§13.2 спутника): 0 — в бюджете, либо ключа нет, либо транскрипта
нет; 1 — НЕ СМОГ (сессия не названа, конфигурация неполна, профили разошлись); 2 — использование;
3 — ИЗМЕРИЛ, превышение. Мягкость кода 3 объявлена на ВЫЗОВЕ, не здесь: прибор несёт честный код.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import sys
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GATES = REPO_ROOT / ".nauta-gates.yaml"
UNIT = "unique-message-id"
ACTOR_SET = "session-file + <sid>/subagents/*.jsonl"
CLASSIFIER = "executable-position"
COLD_PAUSE = 300
EARLY_CALLS = 10                 # «первые обращения актора» предела раннего результата
EARLY_LIMIT = 8192               # предел раннего результата, символов (= предел брифа стадии)
NOT_MEASURED = "NOT-MEASURED:"   # форма Д5 дословно
TOP_RESULTS = 5

# Перечень обёрток объявлен, а не подразумевается (пункт 5 §2 спутника). Обёртка сама тоже
# считается именем: `bash scripts/check.sh` даёт {bash, check.sh}, не одно из двух.
WRAPPERS_NEXT = {"bash", "sh", "zsh", "env", "time", "nohup", "xargs", "sudo", "npx"}
WRAPPERS_SUB = {"uv": {"run", "tool"}, "python": {"-m"}, "python3": {"-m"}}
VALUE_FLAGS = {"--with", "--with-requirements", "--python", "--index", "--extra", "-p"}
SEARCH_NAMES = {"grep", "rg", "ag", "ack", "find", "fd", "ripgrep"}
SEARCH_TOOLS = {"Grep", "Glob"}
SLICE_MARKS = ("preflight", "role-slice")
BRIEF_RUNNER = "wave-brief.py"   # §13.3: брифом считается ЗАПУСК прибора, не имя в команде
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT_RE = re.compile(r"(?:^|\s)\d?>>?\s*([^\s&|;<>]+)")
GATE_CLASSES = ("pytest", "check.sh")   # порог §7: `pytest` ∪ `check.sh`, союз по КОМАНДЕ


# Д4 ADR-114: пятый исход управляемых файлов — файл ВНЕ перечня `readBudgets`, чей оборот за
# сессию превысил 1× веса. Кандидаты ищутся ТЕМ ЖЕ текстом команды, что и объявленные записи
# (`read_of`, ниже) — никакого нового источника текста не заводится, только более широкий
# набор относительных путей `.md`, которые эта команда упоминает.
CANDIDATE_PATH_RE = re.compile(r"[\w][\w./-]*\.md\b")


class BudgetError(Exception):
    """Отказ конфигурации: бюджет прочитан, но неполон либо несравним (§3, строки 2-4)."""


@dataclasses.dataclass
class Call:
    """Одно обращение к модели — уникальный `message.id`, склеенный из своих строк."""
    cid: str
    ts: float
    read: int = 0
    write: int = 0
    gen: int = 0
    tools: list = dataclasses.field(default_factory=list)   # [(имя инструмента, вход)]


def _ts(raw: str) -> float:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _segments(cmd: str, depth: int = 0) -> list[list[str]]:
    """Пункты 1-2 §2: резка на сегменты по `&&`, `||`, `;`, `|`, переводу строки ТОЛЬКО вне
    кавычек; закавыченный текст выбрасывается целиком как данные. Подстановка `$( … )`
    открывает вложенный сегмент — в том числе внутри двойных кавычек, где она исполняется
    (внутри одинарных не исполняется и не открывает)."""
    segs: list[list[str]] = []
    tokens: list[str] = []
    tok = ""
    i = 0
    n = len(cmd)
    while i < n:
        c = cmd[i]
        if c == "'":
            j = cmd.find("'", i + 1)
            i = n if j < 0 else j + 1
            if tok:
                tokens.append(tok)
                tok = ""
            continue
        if c == '"':
            j = i + 1
            while j < n and cmd[j] != '"':
                j += 2 if cmd[j] == "\\" else 1
            if depth < 4:
                for sub in _substitutions(cmd[i + 1:j]):
                    segs.extend(_segments(sub, depth + 1))
            i = j + 1
            if tok:
                tokens.append(tok)
                tok = ""
            continue
        if cmd.startswith("$(", i):
            j = _close_paren(cmd, i + 1)
            if depth < 4:
                segs.extend(_segments(cmd[i + 2:j], depth + 1))
            i = j + 1
            continue
        if cmd.startswith("&&", i) or cmd.startswith("||", i):
            i += 2
            c = ";"
        elif c in ";|\n":
            i += 1
        else:
            if c in " \t":
                if tok:
                    tokens.append(tok)
                    tok = ""
            else:
                tok += c
            i += 1
            continue
        if tok:
            tokens.append(tok)
            tok = ""
        if tokens:
            segs.append(tokens)
            tokens = []
    if tok:
        tokens.append(tok)
    if tokens:
        segs.append(tokens)
    return segs


def _close_paren(text: str, start: int) -> int:
    depth = 0
    for k in range(start, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return len(text)


def _substitutions(text: str) -> list[str]:
    out, i = [], 0
    while True:
        i = text.find("$(", i)
        if i < 0:
            return out
        j = _close_paren(text, i + 1)
        out.append(text[i + 2:j])
        i = j + 1


def _skip_options(tokens: list[str]) -> list[str]:
    k = 0
    while k < len(tokens) and tokens[k].startswith("-"):
        k += 2 if tokens[k] in VALUE_FLAGS else 1
    return tokens[k:]


def _names(tokens: list[str], depth: int = 0) -> set[str]:
    """Пункты 3-6 §2: ведущее присваивание пропускается; имя — БАЗОВОЕ имя пути первого
    исполняемого токена; объявленные обёртки разворачиваются и сами тоже считаются именами."""
    idx = 0
    while idx < len(tokens) and ASSIGN_RE.match(tokens[idx]):
        idx += 1
    rest = _skip_options(tokens[idx:])
    if not rest:
        return set()
    name = rest[0].rsplit("/", 1)[-1]
    if not name:
        return set()
    names = {name}
    tail = rest[1:]
    if depth >= 4:
        return names
    if name in WRAPPERS_NEXT:
        inner = _skip_options([t for t in tail if not ASSIGN_RE.match(t)])
        if inner:
            names |= _names(inner, depth + 1)
    elif name in WRAPPERS_SUB:
        for k, t in enumerate(tail):
            if t in WRAPPERS_SUB[name]:
                inner = _skip_options(tail[k + 1:])
                if inner:
                    names |= _names(inner, depth + 1)
                break
    return names


def classify(command: str) -> set[str]:
    """Классификатор `executable-position` §2 — одна команда даёт МНОЖЕСТВО имён (пункт 6).

    Цена ошибки измерена: над 525 вызовами Bash координатора вопрос «сколько раз звали
    `pytest` ∪ `check.sh`» даёт 0 / 16 / 53 / 131 по правилам «первое слово / голова сегмента /
    исполняемая позиция / подстрока» (§1.2). Здесь реализована ТРЕТЬЯ строка."""
    names: set[str] = set()
    for seg in _segments(command):
        names |= _names(seg)
    return names


def read_actor(path: pathlib.Path) -> tuple[dict[str, Call], list[tuple[float, str, int]]]:
    """Обращения актора по уникальным `message.id` и его результаты инструментов.

    Строки одного id идут НЕ подряд и несут ПОБАЙТОВО одинаковый `usage` — берётся максимум по
    каждому полю, а не сумма: сумма и есть та ошибка, ради которой объявлена единица счёта."""
    calls: dict[str, Call] = {}
    results: list[tuple[float, str, int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        stamp = _ts(rec.get("timestamp"))
        if rec.get("type") == "assistant" and msg.get("id"):
            usage = msg.get("usage") or {}
            call = calls.get(msg["id"])
            if call is None:
                call = calls[msg["id"]] = Call(cid=msg["id"], ts=stamp)
            call.ts = min(call.ts, stamp) if call.ts else stamp
            call.read = max(call.read, int(usage.get("cache_read_input_tokens") or 0))
            call.write = max(call.write, int(usage.get("cache_creation_input_tokens") or 0))
            call.gen = max(call.gen, int(usage.get("output_tokens") or 0))
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    call.tools.append((blk.get("name", ""), blk.get("input") or {},
                                       blk.get("id", "")))
            continue
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "tool_result":
                body = blk.get("content")
                size = len(body) if isinstance(body, str) else len(json.dumps(body,
                                                                              ensure_ascii=False))
                results.append((stamp, blk.get("tool_use_id", ""), size))
    return calls, results


def head_of(tool: tuple) -> str:
    """Голова вызова — то единственное из транскрипта, что уносится в отчёт (граница §5)."""
    name, inp, _ = tool
    if name == "Bash":
        text = str(inp.get("command", ""))
    else:
        arg = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
        text = f"{name} {arg}".strip()
    text = " ".join(text.split())
    return text[:70] + ("…" if len(text) > 70 else "")


def read_of(tool: tuple) -> str:
    """Полный текст входа вызова — для сверки с путями управляемых файлов. Голова (`head_of`)
    здесь не годится: она обрезана 70 символами, и путь в конце длинной команды пропал бы."""
    name, inp, _ = tool
    if name == "Bash":
        return str(inp.get("command", ""))
    return " ".join(str(inp.get(k, "")) for k in ("file_path", "path", "pattern", "glob"))


def _candidate_paths(commands: list) -> set[str]:
    """Все относительные `.md`-пути, упомянутые в Bash-командах актора — кандидаты «вне
    перечня» для пятого исхода Д4. Область НЕ ограничена `content/`: правило Д4 общее — любой
    файл, замеченный сессией и не объявленный `readBudgets`, а не только навигационный слой.

    Путь берётся через `read_of`, а не из одного ключа `command`. Прежняя форма перебирала
    ТОЛЬКО Bash-вызовы и была слепа к нативному `Read`/`Grep`/`Glob` — то есть к основному
    пути чтения у потребителя. Замер (ревью NA-EPIC-56, находка №2): один и тот же файл,
    прочитанный дважды по 1500 Б при весе 2000, давал «не в перечне — оборот 1.50×» через
    `cat` и НИ ОДНОЙ строки через `Read`. Молчание было неотличимо от «ни один файл вне
    перечня порог не превысил» — ровно тот класс, ради которого пятый исход и заведён."""
    found: set[str] = set()
    for _, t in commands:
        found |= set(CANDIDATE_PATH_RE.findall(read_of(t)))
    return found


def measure(name: str, path: pathlib.Path, pause: int, managed: tuple = ()) -> dict:
    """Метрики одного актора. Каждая величина здесь — либо порогуемая (§3), либо печатаемая
    без вердикта (норма спеки «A measured quantity has no threshold»)."""
    calls_by_id, results = read_actor(path)
    calls = sorted(calls_by_id.values(), key=lambda c: (c.ts, c.cid))
    ctx = [c.read + c.write for c in calls]
    cold = [c for i, c in enumerate(calls) if i and c.ts - calls[i - 1].ts > pause]
    tools = [(c.ts, t) for c in calls for t in c.tools]
    by_id = {t[2]: t for _, t in tools}
    # Классы — СПИСОК, параллельный `commands`, а не отображение по отметке времени: у одного
    # обращения несколько вызовов Bash несут ОДНУ отметку, и словарь по ней схлопывал 525
    # вызовов живой сессии до 419 (замер на корпусе c9ba9a29 при сверке с §1.2 спутника).
    commands = [(ts, t) for ts, t in tools if t[0] == "Bash"]
    classes = [classify(str(t[1].get("command", ""))) for _, t in commands]
    searches = [ts for ts, t in tools if t[0] in SEARCH_TOOLS]
    searches += [ts for (ts, _), names in zip(commands, classes) if names & SEARCH_NAMES]
    slice_at = next((ts for (ts, _), names in zip(commands, classes)
                     if any(m in n for n in names for m in SLICE_MARKS)), None)
    written: list[tuple[float, str]] = []
    for ts, t in commands:
        for target in REDIRECT_RE.findall(str(t[1].get("command", ""))):
            if target not in ("/dev/null", "&1", "&2"):
                written.append((ts, target))
    reread = []
    for ts, t in tools:
        touched = [str(t[1].get("file_path", ""))] if t[0] != "Bash" else \
            [tok for seg in _segments(str(t[1].get("command", ""))) for tok in seg]
        for wts, target in written:
            if ts > wts and target in touched:
                reread.append(target)
    # Чтение управляемого файла считается по ВСЕЙ сессии (Д9): окна `TOP_RESULTS` и
    # `EARLY_CALLS`/`EARLY_LIMIT` для этой величины сняты — свои исходные предикаты они
    # исполняют по-прежнему, но прочтение целиком на сороковом обращении ими невидимо.
    # Д4 ADR-114: `tracked` расширяет `managed` кандидатами вне перечня — иначе пятому исходу
    # («не в перечне, оборот N×») нечем было бы измерить оборот файла, о котором `readBudgets`
    # молчит.
    tracked = tuple(managed) + tuple(sorted(_candidate_paths(commands) - set(managed)))
    reads = {rel: [0, 0, "", 0] for rel in tracked}
    for _, rid, size in results:
        text = read_of(by_id.get(rid, ("", {}, "")))
        for rel in tracked:
            if rel and rel in text:
                slot = reads[rel]
                slot[0] += size
                slot[3] += 1
                if size > slot[1]:
                    slot[1], slot[2] = size, head_of(by_id.get(rid, ("", {}, "")))
    ranked = []
    for rts, rid, size in results:
        weight = sum(1 for c in calls if c.ts > rts)
        ranked.append((size * weight, size, weight, head_of(by_id.get(rid, ("", {}, "")))))
    ranked.sort(reverse=True)
    early_ts = calls[EARLY_CALLS - 1].ts if len(calls) >= EARLY_CALLS else float("inf")
    # Бриф опознаётся ИСПОЛНЯЕМОЙ ПОЗИЦИЕЙ (§2) плюс обязательный `--stage`, а не вхождением
    # имени в голову: подстрока засчитала `cat -n scripts/wave-brief.py` — ЧТЕНИЕ ИСХОДНИКА
    # прибора — за бриф и дала 9 397 (§13.3); без `--stage` бриф ВОЛНЫ сравнивался бы с пределом
    # брифа СТАДИИ.
    brief_ids = {t[2] for (_, t), names in zip(commands, classes)
                 if BRIEF_RUNNER in names and "--stage" in str(t[1].get("command", ""))}
    early = [(size, head_of(by_id.get(rid, ("", {}, "")))) for rts, rid, size in results
             if size > EARLY_LIMIT and rts <= early_ts and rid not in brief_ids]
    brief = max([size for _, rid, size in results if rid in brief_ids] or [0])
    return {
        "name": name, "calls": len(calls), "read": sum(c.read for c in calls),
        "write": sum(c.write for c in calls), "gen": sum(c.gen for c in calls),
        "mean": round(sum(ctx) / len(ctx)) if ctx else 0, "peak": max(ctx) if ctx else 0,
        "cold": len(cold), "cold_cost": sum(c.write for c in cold),
        "max_cold_write": max([c.write for c in cold] or [0]),
        "multi": sum(1 for c in calls if len(c.tools) > 1),
        "classes": classes, "searches": searches, "slice_at": slice_at,
        "reread": reread, "ranked": ranked, "early": early, "brief": brief, "reads": reads,
        "weighted": sum(w for w, _, _, _ in ranked),
    }


def report(actors: list[dict], sid: str, pause: int) -> list[str]:
    """Отчёт. Профиль печатается первым и всегда — число без правила не есть число (Д1)."""
    subs = len(actors) - 1
    out = [f"цена сессии {sid}", "",
           "counting-rule:", f"  unit: {UNIT}", f"  actorSet: {ACTOR_SET}",
           f"  bashClassifier: {CLASSIFIER}", f"  cold-pause={pause}s",
           f"  прочитано файлов акторов: {len(actors)} (субагентов: {subs})", "", "акторы:"]
    for a in actors:
        out.append(f"  {a['name']}: обращений {a['calls']}, чтение из кэша {a['read']}, "
                   f"запись в кэш {a['write']}, генерация {a['gen']}, "
                   f"средний контекст {a['mean']}, пиковый {a['peak']}")
    cold = sum(a["cold"] for a in actors)
    cold_cost = sum(a["cold_cost"] for a in actors)
    calls = sum(a["calls"] for a in actors)
    multi = sum(a["multi"] for a in actors)
    out += ["", f"холодные обращения (пауза > {pause} с): {cold}, цена {cold_cost}, "
                f"максимальная одиночная запись {max([a['max_cold_write'] for a in actors] or [0])}",
            "", "величины без порога — дерево ими не управляет, число печатается, власти "
                "над ним гейт не берёт:",
            f"  вклад TTL кэша платформы: {cold_cost} токенов записи после паузы, "
            f"превысившей {pause} с",
            f"  доля ходов с двумя и более инструментами: "
            f"{round(100 * multi / calls) if calls else 0} % ({multi} из {calls})"]
    counts: dict[str, int] = {}
    for a in actors:
        for names in a["classes"]:
            for n in names:
                counts[n] = counts.get(n, 0) + 1
    out += ["", f"классификатор {CLASSIFIER} — вызовы по именам:"]
    out += [f"  {n}: {c}" for n, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:12]] \
        or ["  вызовов не было"]
    out += ["", "наблюдаемость механизмов:"]
    for a in actors:
        total = len(a["searches"])
        if a["slice_at"] is None:
            out.append(f"  {a['name']}: срез не получен — доля поисков после среза не "
                       f"определена (поисков всего {total})")
        else:
            after = sum(1 for ts in a["searches"] if ts > a["slice_at"])
            out.append(f"  {a['name']}: поисков после среза {after} из {total} — доля "
                       f"{round(100 * after / total) if total else 0} %")
        out.append(f"  {a['name']}: перечитываний собственного файла-посредника "
                   f"{len(a['reread'])}" + (f" — {', '.join(sorted(set(a['reread'])))}"
                                            if a["reread"] else ""))
    out += ["", "самые дорогие результаты (взвешенная цена = размер x число последующих "
                "обращений):"]
    ranked = sorted(((w, s, k, h, a["name"]) for a in actors for w, s, k, h in a["ranked"]),
                    reverse=True)[:TOP_RESULTS]
    out += [f"  {n} {w} (размер {s} x {k}) — `{h}`" for w, s, k, h, n in ranked] \
        or ["  результатов не было"]
    early = [(a["name"], size, head) for a in actors for size, head in a["early"]]
    out += ["", f"ранние результаты сверх предела {EARLY_LIMIT} символов "
                f"(первые {EARLY_CALLS} обращений актора; бриф — единственное исключение):"]
    out += [f"    {n}: {size} символов — `{head}`" for n, size, head in early] \
        or ["    превысивших предел нет"]
    return out + [""]


def parse_read_budgets(raw: str) -> list[dict]:
    """Перечень управляемых файлов (Д8, расширен Д1/Д2/Д4 ADR-114) — ТЕМ ЖЕ ручным разбором,
    что `sessionCostBudget`.

    Библиотеки YAML в этом файле нет по причине, объявленной докстрокой `parse_budget`, и
    вторым читателем формата прибор не обзаводится: разбор один, ключа два. Форма записи —
    `path`, `bytes` (число ЛИБО null при НАЗВАННОМ `status`), `keys` (список измерений в
    скобках, `[волна]`/`[судьба, волна]`/`[]` — единственная форма списка, которую несёт этот
    конфиг, поэтому разбор скобочного списка живёт ЗДЕСЬ и нигде больше), необязательный
    `keyed-in` (Д2 ADR-114: измерение объявлено НЕ в самом файле, а в НАЗВАННОМ реестре).
    """
    m = re.search(r"^readBudgets:[^\n]*\n", raw, re.M)
    if not m:
        return []
    out: list[dict] = []
    for line in raw[m.end():].splitlines():
        if line.strip() and not line.startswith((" ", "\t")):
            break
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        if body.startswith("- "):
            out.append({})
            body = body[2:]
        if not out:
            raise BudgetError(f"поле `{body}` стоит вне записи `readBudgets`")
        key, value, _ = _kv(body)
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        out[-1][key] = value
    return out


def _weight_outcome(total: int, size: int) -> str:
    """Д4/AC-024/AC-025 ADR-114: порог «не дороже одного раза» меряется ЖИВЫМ весом файла
    (`wc -c`), а НЕ бюджетом чтения (`bytes`, ADR-102 Д4/ADR-108 Д9) — это отдельная величина,
    печатаемая ДОПОЛНИТЕЛЬНО к состоянию budget-класса, а не вместо него: файл, читанный кусками
    сверх бюджета, но НИЖЕ собственного веса, остаётся «не дороже одного раза» (AC-024), а
    читанный сверх ВЕСА обязан называть множитель, а не «в пределах» (AC-025). Пусто, если файл
    в сессии не назван вовсе — оборот без чтения не определён."""
    if not total or not size:
        return ""
    ratio = total / size
    if ratio <= 1:
        return f"; прочитан не дороже одного раза (вес {size}, оборот {ratio:.2f}×)"
    return f"; ПРЕВЫШЕНИЕ веса файла — {ratio:.2f}× (вес {size})"


def _invalid_budget_note(budget: str | None, size: int) -> str:
    """Д4/AC-027 ADR-114: `bytes`, не МЕНЬШИЙ живого веса файла, никогда не сработает как
    бюджет — запись отклоняется ПОИМЁННО, называя оба числа, а не принимается молча как
    рабочая (строгое неравенство — граница `bytes == size` тоже невалидна)."""
    if budget is None or int(budget) < size:
        return ""
    return (f"; запись отклонена как невалидная: bytes={budget} не меньше живого веса {size} "
            f"(AC-027, строгое неравенство)")


def managed_lines(actors: list[dict], budgets: list[dict]) -> list[str]:
    """Наблюдаемость «прочитан целиком» — Д9: по каждой записи РОВНО ОДНА строка из четырёх
    исходов, и все четыре отличимы от `NOT-MEASURED:` (Д5).

    Граница «целиком» снимается над самим файлом В МОМЕНТ ЗАМЕРА и константой не
    записывается никогда: константа не сдвинулась бы вместе с ростом файла, и отчёт
    продолжал бы звать выдержку полным прочтением.
    """
    out = ["", "управляемые файлы (перечень и бюджет чтения — конфигурация дерева):"]
    if not budgets:
        out.append(f"  перечень не объявлен: ключа управляемых файлов в {GATES.name} нет — "
                   "тихий проход (ADR-031 Д3), ноль строк вместо молчания")
        return out
    for entry in budgets:
        rel = str(entry.get("path", ""))
        raw = str(entry.get("bytes", ""))
        budget = raw if raw.isdigit() else None
        status = str(entry.get("status", "") or "не назван")
        tail = "" if budget else f" — бюджет не объявлен (status: {status})"
        target = REPO_ROOT / rel
        if not rel or not target.is_file():
            out.append(f"  {rel}: {NOT_MEASURED} файла в дереве нет — записи бюджета есть, "
                       "предмета нет (это не «не читался»)")
            continue
        size = target.stat().st_size
        total, biggest, head, times = (actors and actors[0]["reads"].get(rel)
                                       or [0, 0, "", 0])[:4]
        for a in actors[1:]:
            got, one, h, k = a["reads"].get(rel, [0, 0, "", 0])[:4]
            total += got
            times += k
            if one > biggest:
                biggest, head = one, h
        if total == 0:
            state = "в сессии не назван"
        elif biggest >= size:
            state = f"ПРОЧИТАН ЦЕЛИКОМ одним вызовом — `{head}`"
        elif total >= size:
            state = f"НАКОПЛЕНО кусками до {total} байт за {times} вызовов"
        elif budget:
            # Величина против бюджета названа ЧИСЛОМ, а не выдана за соблюдение: 100 017
            # прочитанных байт при бюджете 8 192 — это ровно та цена, ради которой перечень
            # заведён, и слово «выдержкой» одно её не показывает. `rc` строка не меняет
            # (ADR-102 Д4): бюджет чтения — размерность, а не отказ прибора.
            over = total - int(budget)
            state = (f"выдержкой, {total} байт при бюджете {budget}"
                     + (f" — ПРЕВЫШЕНИЕ бюджета на {over}" if over > 0 else ""))
        else:
            state = f"выдержкой, {total} байт"
        weight_note = _weight_outcome(total, size)
        invalid_note = _invalid_budget_note(budget, size)
        out.append(f"  {rel}: {state}{tail}{weight_note}{invalid_note}")

    # Д4 ADR-114, пятый исход: файл ВНЕ перечня, чей оборот за сессию превысил 1× веса — НАЗВАН,
    # а не молчит и не сливается с «внесён, bytes: null» (AC-026). Строго `>`, не `>=`: ровно
    # 1,0× граница пятого исхода — «не превысил» (спутник §10, граничное условие QA-105).
    declared = {str(e.get("path", "")) for e in budgets}
    unlisted: dict[str, list] = {}
    for a in actors:
        for rel, slot in a["reads"].items():
            if rel in declared or not slot[0]:
                continue
            agg = unlisted.setdefault(rel, [0, 0, "", 0])
            agg[0] += slot[0]
            agg[3] += slot[3]
            if slot[1] > agg[1]:
                agg[1], agg[2] = slot[1], slot[2]
    for rel in sorted(unlisted):
        target = REPO_ROOT / rel
        if not target.is_file():
            continue
        size = target.stat().st_size
        total = unlisted[rel][0]
        if size and total > size:
            out.append(f"  {rel}: не в перечне управляемых файлов — оборот "
                       f"{total / size:.2f}× ({total} байт при весе {size})")
    return out


def dimensions_of(actors: list[dict]) -> dict[str, tuple[int, str]]:
    """Измеренное и ЕДИНИЦА каждой размерности §3. Единица — часть контракта размерности:
    та же величина, выраженная суммой размеров вместо доли, ограничивает не то (AC-8)."""
    main = actors[0]
    # Счёт вызовов гейтов и прогонов — по КООРДИНАТОРУ, не по всем акторам: переписанная
    # строка §7 спутника называет предметом порога «`pytest` + `check.sh` У КООРДИНАТОРА», и
    # база 23 на волну снята там же. Число, сложенное по пятнадцати акторам, сравнивалось бы
    # с базой, измеренной по одному.
    gate = sum(1 for names in main["classes"] if any(g in names for g in GATE_CLASSES))
    share = round(100 * main["weighted"] / main["read"]) if main["read"] else 0
    return {
        "coordinator-mean-context": (main["mean"], "tokens"),
        "coordinator-peak-context": (main["peak"], "tokens"),
        # Тоже по КООРДИНАТОРУ: база 361783 снята §1.3 спутника на нём, а порог наследован от
        # порога его пикового контекста. Строка §7 про «максимальную одиночную холодную запись
        # РОЛИ» с порогом 70 000 — ОТДЕЛЬНАЯ размерность, и в блоке §3 её нет; максимум по
        # ролям здесь не подмешивается, иначе он молча сравнивался бы с чужим порогом.
        "max-single-cold-write": (main["max_cold_write"], "tokens"),
        "test-and-gate-invocations-per-wave": (gate, "invocations"),
        "stage-brief-bytes": (max(a["brief"] for a in actors), "bytes"),
        "coordinator-tool-result-weighted-share": (share, "share-of-cache-reads"),
    }


def _kv(body: str) -> tuple[str, str, str]:
    if ":" not in body:
        raise BudgetError(f"строка `{body}` не пара «ключ: значение»")
    key, _, rest = body.partition(":")
    rest, comment = rest.strip(), ""
    m = re.search(r"(?:^|\s)#(.*)$", rest)
    if m:
        comment, rest = m.group(1).strip(), rest[:m.start()].strip()
    return key.strip(), rest, comment


def parse_budget(raw: str) -> dict | None:
    """Разбор ключа `sessionCostBudget` СВОИМИ РУКАМИ, а не библиотекой YAML, по одной
    причине: `base: null` законен ТОЛЬКО с комментарием-провенансом (§12 п. 8), а любой
    разборщик YAML комментарий выбрасывает — и «базы нет» стало бы неотличимо от «база
    объявлена»."""
    m = re.search(r"^sessionCostBudget:[^\n]*\n", raw, re.M)
    if not m:
        return None
    cfg: dict = {"comparisonBase": {}, "countingRule": {}, "dimensions": []}
    section, item = None, None
    for line in raw[m.end():].splitlines():
        if line.strip() and not line.startswith((" ", "\t")):
            break
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 2:
            if body.endswith(":") and not body.startswith("- "):
                section = body[:-1]
                if section not in cfg:
                    raise BudgetError(f"неизвестный подключ `{section}` — форма §3 спутника "
                                      "ADR-102: comparisonBase / countingRule / dimensions")
                item = None
                continue
            raise BudgetError(f"ожидалось отображение из трёх подключей, прочитано `{body}`")
        if section is None:
            raise BudgetError(f"строка `{body}` стоит вне подключа")
        if section == "dimensions":
            if body.startswith("- "):
                item = {"__c__": {}}
                cfg["dimensions"].append(item)
                body = body[2:]
            if item is None:
                raise BudgetError(f"поле `{body}` вне размерности")
            key, value, comment = _kv(body)
            item[key] = value
            item["__c__"][key] = comment
        else:
            key, value, _ = _kv(body)
            cfg[section][key] = value
    return cfg


def check_budget(cfg: dict, measured: dict[str, tuple[int, str]], pause: int) -> list[str]:
    """Семь исходов §3 таблицей. Отказ конфигурации называет НЕДОСТАЮЩЕЕ ПОЛЕ — иначе он
    невоспроизводим из собственного вывода."""
    for field in ("session", "measuredAt", "scope"):
        if not cfg["comparisonBase"].get(field):
            raise BudgetError(
                f"размерности объявлены без базы сравнения: в `comparisonBase` нет поля "
                f"`{field}`. Число цены сессии имеет смысл только против другой сессии, "
                f"измеренной так же (AC-17, ADR-086 Д2).")
    profile = {"unit": UNIT, "actorSet": ACTOR_SET, "bashClassifier": CLASSIFIER,
               "coldPauseSeconds": str(pause)}
    theirs = cfg["countingRule"]
    if any(theirs.get(k) != v for k, v in profile.items()):
        raise BudgetError(
            "ОТКАЗ СРАВНЕНИЯ: профиль правила счёта конфигурации не совпадает с профилем "
            "прибора — сравнивать нечего (ADR-102 Д1, спутник §3, строка 4 таблицы "
            "исходов).\n"
            "  прибор:       " + " ".join(f"{k}={v}" for k, v in profile.items()) + "\n"
            "  конфигурация: " + " ".join(f"{k}={theirs.get(k, '<нет>')}" for k in profile))
    lines, failed = [], False
    for dim in cfg["dimensions"]:
        name = dim.get("name", "")
        if name not in measured:
            raise BudgetError(f"размерность `{name}` прибором не измеряется — порог без "
                              f"измерения не проверяем")
        value, unit = measured[name]
        if dim.get("unit") != unit:
            raise BudgetError(
                f"размерность `{name}` выражена единицей `{dim.get('unit')}`, а измеряется в "
                f"`{unit}`: цена результата есть размер, умноженный на число последующих "
                f"обращений, поэтому сумма размеров ограничивает не ту величину (AC-8).")
        if "number" not in dim:
            raise BudgetError(f"размерность `{name}` не несёт поля `number`")
        if "base" not in dim:
            raise BudgetError(f"размерность `{name}` не несёт поля `base` — база сравнения "
                              f"обязательна (§3, строка 3 таблицы исходов)")
        base = dim["base"]
        if base in ("null", "~", ""):
            if not dim["__c__"].get("base"):
                raise BudgetError(
                    f"размерность `{name}`: `base: null` допускается ТОЛЬКО с комментарием-"
                    f"провенансом, называющим, почему числа базы нет (спутник §3). "
                    f"Правдоподобное число вместо null запрещено.")
            base = "не измерена"
        try:
            number = int(dim["number"])
        except ValueError:
            raise BudgetError(f"размерность `{name}`: `number` не число") from None
        bad = value > number
        failed = failed or bad
        # Знак вынесен из выражения f-строки НАМЕРЕННО, а не ради вкуса: экранирование
        # внутри выражения легально только с 3.12, а заголовок скрипта объявляет `>=3.11`.
        # Вложенный вызов (всякий прогон из сьюты) наследует интерпретатор внешнего `uv run`
        # и получал SyntaxError вместо замера — прибор был неисполним под объявленным полом.
        mark = "\u2717" if bad else "\u2713"
        lines.append(f"  {mark} {name}: измерено {value} / порог {number} / "
                     f"база {base}" + (" — превышение" if bad else ""))
    lines.append("  бюджет: превышения есть" if failed else "  бюджет: превышений нет")
    if failed:
        lines.append("__FAILED__")
    return lines


JOURNAL_INVALID = 1
JOURNAL_OK = 0


def _lesson_destiny_module():
    """`scripts/_validate_common.py` — соседний, НЕ хэшенный дефисом модуль, обычный `import`
    после вставки `scripts/` в `sys.path`. `И1…И5 (check_lesson_destiny)` не переписываются
    здесь (Д2 ADR-114 дословно) — читатель проекции РЕИСПОЛЬЗУЕТ существующий инвариант, а не
    заводит второй. Лениво: `measure()`/`main()` этого прибора в обычном режиме сессии его не
    трогают, и вызов, изолированный `uv run --script` (`dependencies = []`), не платит цену
    импорта `pyyaml`, которого в ЕГО песочнице нет — журнальный режим документированно зовётся
    ПЛОСКИМ `python3` (тот же приём, что тесты Лок 1/Лок 2 у `wave-brief.py`)."""
    import sys as _sys

    scripts_dir = str(pathlib.Path(__file__).resolve().parent)
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)
    import _validate_common
    return _validate_common


JOURNAL_OF_I1 = "content/lessons-learned.md"


def journal_projection(rel: str, budgets: list[dict], repo_root: pathlib.Path,
                       *, with_notes: bool = False) -> tuple[int, list[str]]:
    """Д2 ADR-114: журнал входит на путь чтения РЕЕСТРОМ судеб. Спрашивают реестр
    (`keyed-in`), из журнала берут НАЗВАННУЮ строку. Полнота индекса не предполагается —
    заперта существующим И1 (`check_lesson_destiny`): реестр, у которого живая строка
    журнала осталась без записи исхода, отказывает и называет sha ЭТОЙ строки, а не молча
    собирает проекцию поверх неполного индекса (документированная команда §3/§8 п.4
    спутника ADR-114, живьём воспроизведено QA-105 на обоих исходах)."""
    entry = next((e for e in budgets if str(e.get("path", "")) == rel), None)
    if entry is None:
        return JOURNAL_INVALID, [f"запись readBudgets для {rel!r} не найдена — {GATES.name}"]
    keyed_in = entry.get("keyed-in")
    if not keyed_in:
        return JOURNAL_INVALID, [f"запись {rel!r} не несёт `keyed-in` — проекция журнала "
                                 f"недоступна без объявленного реестра (Д2 ADR-114)"]
    registry_path = repo_root / str(keyed_in)
    if not registry_path.is_file():
        # ADR-031 Д3/ADR-088 Д1: реестра у потребителя нет и не будет — тихий проход, а не
        # отказ (тот же контракт, что несёт И1 сам по себе).
        return JOURNAL_OK, [f"реестр {keyed_in} не найден — проекция не построена (это не "
                            f"«журнал пуст», ADR-031 Д3)"]
    common = _lesson_destiny_module()
    # №10 ревью: И1 сверяет реестр с `content/lessons-learned.md` ЖЁСТКО
    # (`_validate_common.py`: `repo_root / "content" / "lessons-learned.md"`), а `rel` приходит
    # из записи `readBudgets`. Разойдись они — проверенный и прочитанный файлы стали бы разными
    # МОЛЧА. Отказ громкий, пока предмет И1 не станет параметром.
    if rel != JOURNAL_OF_I1:
        return JOURNAL_INVALID, [
            f"ОТКАЗ: И1 сверяет реестр с {JOURNAL_OF_I1!r} жёстко, а проекция запрошена для "
            f"{rel!r} — проверенный и прочитанный файл разошлись бы молча (Д2 ADR-114)"]
    issues = common.check_lesson_destiny(registry_path, repo_root)
    if issues:
        return JOURNAL_INVALID, [
            f"ОТКАЗ: реестр {keyed_in} неполон — проекция НЕ собрана поверх неполного индекса "
            f"(И1..И5, Д2 ADR-114):"
        ] + [f"  {i.message}" for i in issues]
    data = common.parse_yaml_file(registry_path)
    records = data.get("records") if isinstance(data, dict) else None
    records = records if isinstance(records, list) else []
    # Адрес строки собирается ИЗ ЖУРНАЛА по ключу `row-sha`, а не из поля `row` реестра. Поле
    # `row` не сверяется с журналом ни одним инвариантом И1..И5 — по ADR-088 Д1 оно адресует
    # запись ЧЕЛОВЕКУ и «ключом НЕ является». Замер на живом дереве: 21 запись из 57 с журналом
    # расходится, и ТРИ разных урока выходили в проекцию побайтово одинаковыми строками
    # (ревью NA-EPIC-56, находка №3). Ключ — единственное, что заперто И1, из него и строим;
    # первым полем идёт сам sha, поэтому две живые записи неразличимыми быть не могут.
    live = {common._lesson_row_sha12(l): l
            for l in common._lesson_table_rows(repo_root / rel)}
    lines = []
    for rec in records:
        if not isinstance(rec, dict) or rec.get("archived-in"):
            continue          # проекция — ТОЛЬКО живые записи (без archived-in), Д2 дословно
        sha = str(rec.get("row-sha", ""))
        row = live.get(sha)
        if row is None:
            continue          # запись не про живую строку — её судьбу разобрал И1 выше
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        addr = " | ".join(cells[:3])
        destiny = str(rec.get("destiny", ""))
        line = f"{sha} | {addr} | {destiny}"
        if with_notes and rec.get("note"):
            line += f" | {rec['note']}"
        lines.append(line)
    return JOURNAL_OK, lines or ["живых записей в реестре нет"]


def resolve(raw: str) -> tuple[str, pathlib.Path]:
    if raw.endswith(".jsonl") or "/" in raw:
        path = pathlib.Path(raw).expanduser()
        return path.stem, path
    base = os.environ.get("CLAUDE_PROJECTS_DIR")
    root = pathlib.Path(base).expanduser() if base else (
        pathlib.Path.home() / ".claude" / "projects" /
        str(pathlib.Path.cwd()).replace("/", "-"))
    return raw, root / f"{raw}.jsonl"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session_arg", nargs="?", metavar="session",
                    help="идентификатор сессии либо путь к файлу транскрипта")
    ap.add_argument("--session", dest="session_flag", help="то же самое флагом")
    ap.add_argument("--cold-pause", type=int, default=COLD_PAUSE,
                    help=f"длина паузы, выше которой обращение холодное (умолчание {COLD_PAUSE})")
    ap.add_argument("--journal-projection", metavar="<путь readBudgets>", default=None,
                    help="Д2 ADR-114: проекция журнала `row | destiny` по записи readBudgets, "
                         "несущей `keyed-in` — без сессии. Документированно зовётся плоским "
                         "`python3`, не `uv run` (дереву прибора не нужен pyyaml)")
    ap.add_argument("--with-notes", action="store_true",
                    help="проекция несёт поле `note` каждой записи (явный выбор — 0,27x "
                         "журнала, выше бюджета 8192, Д2 ADR-114)")
    args = ap.parse_args(argv)
    if args.journal_projection is not None:
        gates_raw = GATES.read_text(encoding="utf-8") if GATES.is_file() else ""
        try:
            budgets = parse_read_budgets(gates_raw)
        except BudgetError as exc:
            print(f"ОШИБКА КОНФИГУРАЦИИ {GATES}: {exc}", file=sys.stderr)
            return 1
        rc, lines = journal_projection(args.journal_projection, budgets, REPO_ROOT,
                                       with_notes=args.with_notes)
        stream = sys.stderr if rc else sys.stdout
        print("\n".join(lines), file=stream)
        return rc
    raw = args.session_arg or args.session_flag or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not raw:
        print("ОТКАЗ: сессия не названа. Ступени разрешения (§1.4 спутника ADR-102): аргумент "
              "`<session-id | путь>` либо `--session`, затем переменная окружения "
              "$CLAUDE_CODE_SESSION_ID. Обе пусты. Выбора «самый свежий файл по mtime» у "
              "прибора нет: это необъявленное правило счёта.", file=sys.stderr)
        return 1
    sid, path = resolve(raw)
    cfg = None
    budgets: list[dict] = []
    try:
        if GATES.is_file():
            gates_raw = GATES.read_text(encoding="utf-8")
            cfg = parse_budget(gates_raw)
            budgets = parse_read_budgets(gates_raw)
    except BudgetError as exc:
        print(f"ОШИБКА КОНФИГУРАЦИИ {GATES}: {exc}", file=sys.stderr)
        return 1
    if not path.is_file():
        print(f"{NOT_MEASURED} session={sid} looked-in={path.parent} — транскрипт не найден")
        print("Это состояние прогона, а не вердикт и не поломка инструмента (ADR-102 Д5, "
              "ADR-007 Д1): записи в дереве оно не заводит и порогов не касается.")
        return 0
    managed = tuple(str(e.get("path", "")) for e in budgets)
    actors = [measure("coordinator", path, args.cold_pause, managed)]
    sub = path.parent / path.stem / "subagents"
    if sub.is_dir():
        actors += [measure(f.stem, f, args.cold_pause, managed)
                   for f in sorted(sub.glob("*.jsonl"))]
    lines = report(actors, sid, args.cold_pause) + managed_lines(actors, budgets)
    rc = 0
    if cfg is None:
        lines.append("бюджет цены сессии не объявлен: ключа `sessionCostBudget` в "
                     f"{GATES.name} нет — тихий проход (ADR-031 Д3), отчёт выше остаётся "
                     "измерением.")
    else:
        try:
            verdict = check_budget(cfg, dimensions_of(actors), args.cold_pause)
        except BudgetError as exc:
            print("\n".join(lines))
            print(f"ОШИБКА КОНФИГУРАЦИИ {GATES}: {exc}", file=sys.stderr)
            return 1
        base = cfg["comparisonBase"]
        lines.append(f"бюджет цены сессии (база сравнения: session={base['session']}, "
                     f"measuredAt={base['measuredAt']}, охват {base['scope']}):")
        if "__FAILED__" in verdict:
            verdict.remove("__FAILED__")
            rc = 3      # ИЗМЕРИЛ и не сошлось — отдельный код от «не смог» (§13.2)
        lines += verdict
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
