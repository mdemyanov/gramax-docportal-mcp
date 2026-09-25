#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0,<7.0"]
# ///
"""check-ratchet.py — храповик ВОЛНЫ: прибор сравнивает ЗАПИСИ ряда, а не измеряет дерево.

Предмет — агрегат ВОЛНЫ (ADR-106, спутник §3). Порогом метрики служит величина ПОСЛЕДНЕЙ
ЗАКРЫТОЙ волны, прочитанная из носителя `.nauta-ratchet.yaml`, а не рукописная константа и не
сегодняшнее измерение. Потолки ОТДЕЛЬНЫХ ФАЙЛОВ — другой механизм с другим носителем
(`sizeBudgetGrandfathered` в `.nauta-gates.yaml`), и вердикт одного не подменяет вердикт
другого: ключ-путь файла в ряду — отказ конфигурации, называющий правильный носитель.

ЧЕГО ПРИБОР НЕ ДЕЛАЕТ (границы, спутник §5).
  * Не ИСПОЛНЯЕТ объявленную команду (Д4). Исполнение произвольной строки конфигурации есть
    выполнение кода по правке YAML, а белый список нашил бы на прибор константы nauta и
    провалил условие (2) ADR-085 Д1. Предмет воспроизводимости занят `check-suite-cost-pin.py`.
  * Не ПИШЕТ ни в ряд, ни в стор, ни в `.nauta-gates.yaml`: строку в ряд кладёт роль на
    закрытии волны.
  * Не СУДИТ объём файлов и не знает ни одного имени метрики: набор размерностей читается из
    носителя, поэтому дерево потребителя получает ТОТ ЖЕ прибор со своим набором.

ЧЕТЫРЕ ПРЕДИКАТА С РАЗНЫМИ СУБЪЕКТАМИ (форма ADR-083 Д4 — не один прибор с двумя флагами):
  P0 форма         — носитель как конфигурация: набор объявлен, у каждой размерности команда
                     либо три поля объявленного отказа; строка, снятая с ЗАДАЧИ (поле `task`),
                     объявляет сопоставимость класса задач (`comparableClass`, ADR-107 Д8);
  P1 актуальность  — `openWave` против контура И (в режиме `--closing`);
  P2 сравнение     — пара волн (W, W−1) по каждой размерности;
  P3 неизменяемость — диф носителя против `--since`: строки закрытых волн не правятся.

КОДЫ (четвёрка ADR-102 Д2 в значениях ADR-106 Д6):
  0 — сравнено и не хуже; ЛИБО объявленный отказ; ЛИБО носителя в дереве нет (ГРОМКИЙ ноль:
      строка называет отсутствующий файл и что он даёт, ADR-085 Д1(3));
  1 — НЕ СМОГ ПРОВЕРИТЬ: нет строки прошлой волны, коммит не резолвится, две базы без
      `crossBase`, ряд разошёлся с контуром И, `bd` недоступен на предусловии;
  2 — использование и конфигурация: носитель назван и не читается, носитель не разбирается,
      размерность без команды, `absent` без трёх полей, ключ-путь файла в ряду;
  3 — НАРУШЕНИЕ РЯДА: хуже без записи об ухудшении, пустая причина записи, правка закрытой
      строки, расхождение профилей.
Мягким объявлен ТОЛЬКО код 3 и ТОЛЬКО у ступени (`run_gate_if_declared "check-ratchet" "3"`);
у предусловия `close_route` мягких кодов нет вовсе.

Usage: check-ratchet.py [--carrier <путь>] [--closing <epic>] [--since <ref>]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

RC_OK, RC_CANNOT, RC_USAGE, RC_VIOLATION = 0, 1, 2, 3

#: Старшинство кодов при слиянии вердиктов. Конфигурация старше нарушения: носитель, который
#: нельзя прочитать как объявлено, делает любой вердикт о ряде недоказанным.
_RANK = {RC_OK: 0, RC_CANNOT: 1, RC_VIOLATION: 2, RC_USAGE: 3}

CARRIER_NAME = ".nauta-ratchet.yaml"
GATES_NAME = ".nauta-gates.yaml"
CEILING_CARRIER = "sizeBudgetGrandfathered"

#: Ключ-путь файла: имя размерности, похожее на путь дерева. Предмет потолка файла живёт в
#: другом носителе, и молчаливый приём такой строки слил бы два механизма в один (AC-012).
_PATH_LIKE = re.compile(r"/|\.(?:py|sh|md|ya?ml|json|toml|groovy)$")

#: Три обязательных поля объявленного отказа (Д3): отказ обязан назвать, ЧТО и КОГДА его снимет.
ABSENT_FIELDS = ("reason", "expectedCarrier", "expectedWave")

#: Шесть полей самодостаточной строки ряда (§2 спутника; норма спеки говорит «пять» и
#: перечисляет шесть — расхождение названо, печатает прибор всё, что несёт строка).
ROW_FIELDS = ("metric", "value", "unit", "command", "commit", "profile")


class Report:
    """Накопитель строк и кодов. Печать здесь — предмет, а не оформление: вердикт без обеих
    величин и обеих команд недоказуем, а тихий ноль неотличим от «нечего проверять»."""

    def __init__(self) -> None:
        self.rc = RC_OK
        self.lines: list[str] = []

    def say(self, line: str) -> None:
        self.lines.append(line)

    def fail(self, rc: int, line: str) -> None:
        self.say(line)
        if _RANK[rc] > _RANK[self.rc]:
            self.rc = rc

    def flush(self) -> int:
        for line in self.lines:
            print(line)
        return self.rc


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, timeout=120)


def git_root(cwd: Path) -> Path | None:
    """Корень дерева git для cwd либо None. Дерево без своей истории (плоская копия
    `git archive HEAD | tar -x`) — законное состояние: «нечего проверять», не «не смог»."""
    if shutil.which("git") is None:
        return None
    try:
        out = _git(cwd, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None


def commit_resolves(cwd: Path, sha: str) -> bool:
    return _git(cwd, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def gates_dimensions(carrier: Path, cwd: Path) -> dict[str, object]:
    """Базы `sessionCostBudget` из `.nauta-gates.yaml` — ЧТЕНИЕ, и только оно (Д2: ключ ADR-102
    не переезжает и не правится). Ищется рядом с носителем, затем в корне дерева cwd."""
    for candidate in (carrier.parent / GATES_NAME, cwd / GATES_NAME):
        if not candidate.is_file():
            continue
        try:
            doc = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return {}
        dims = (doc.get("sessionCostBudget") or {}).get("dimensions") or []
        return {d.get("name"): d.get("base") for d in dims if isinstance(d, dict)}
    return {}


def check_form(doc: dict, rep: Report) -> dict[str, dict]:
    """P0 — носитель как КОНФИГУРАЦИЯ. Возвращает объявленный набор размерностей по имени."""
    declared: dict[str, dict] = {}
    for dim in doc.get("dimensions") or []:
        if not isinstance(dim, dict) or not dim.get("name"):
            rep.fail(RC_USAGE, "  ✗ размерность без имени — набор обязан быть объявлен поимённо")
            continue
        name = str(dim["name"])
        declared[name] = dim
        if _PATH_LIKE.search(name):
            rep.fail(RC_USAGE, f"  ✗ ключ-путь файла в ряду волн: {name!r}. Потолок ОТДЕЛЬНОГО "
                               f"ФАЙЛА живёт в `{CEILING_CARRIER}` (.nauta-gates.yaml, ADR-078 "
                               f"Д3/ADR-063 Д4) — предмет, каденция и происхождение порога у "
                               f"него другие. Ряд волн потолков файлов не несёт.")
            continue
        if dim.get("source") == "absent":
            missing = [f for f in ABSENT_FIELDS if not dim.get(f)]
            if missing:
                rep.fail(RC_USAGE, f"  ✗ размерность {name}: объявленный отказ без обязательных "
                                   f"полей {', '.join(missing)}. Отказ обязан назвать, ЧТО и "
                                   f"КОГДА его снимет, иначе забывчивость неотличима от отказа.")
            continue
        if not dim.get("command"):
            rep.fail(RC_USAGE, f"  ✗ размерность {name} не несёт команды, воспроизводящей "
                               f"величину: величина без прибора в закрытый набор не входит.")
        if not dim.get("direction"):
            rep.fail(RC_USAGE, f"  ✗ размерность {name} не объявляет direction — «лучше» и "
                               f"«хуже» у неё не определены.")
    if not declared:
        rep.fail(RC_USAGE, "  ✗ набор размерностей не объявлен: `dimensions` пуст или отсутствует")
    return declared


#: Адреса дерева внутри объявленной команды: путь файла и литерал, которым команда адресует
#: место В НЁМ. Прибор команду НЕ ИСПОЛНЯЕТ и исполнять не начинает (Д4 — решение принято):
#: он проверяет РАЗРЕШИМОСТЬ адреса — файл существует, литерал в нём встречается. Дефект, за
#: который заведено: `check_form` требовала строку `command` ПРИСУТСТВОВАТЬ и только это, и
#: уехавший якорь (переименование блока, смена числительного) давал `grep -c` = 0 — «0 ≤ 3»
#: читалось как достижение цели, покраснеть было некому (ADR-113-spec §4, DEV-470).
_CMD_PATH_RE = re.compile(r"(?:[\w.-]+/)*[\w.-]+\.(?:py|sh|md|ya?ml)\b")
_CMD_ANCHOR_RE = re.compile(r"(?:sed -n|grep(?:\s+-\w+)*)\s+'([^']*)'")
#: Части адреса sed с метасимволами (`/^   ```$/`) пропускаются: их разрешимость подстрокой не
#: проверить, а выдуманный вердикт хуже молчания. Молчание здесь ОБЪЯВЛЕНО, а не случайно.
_RE_META = set("^$*+?[]\\|()")
ANCHOR_REFUSAL = "якорь команды не найден"


def check_tree_anchors(carrier: Path, declared: dict[str, dict], rep: Report) -> None:
    """P0, вторая половина: команда размерности `source: tree` обязана быть РАЗРЕШИМОЙ."""
    base = carrier.resolve().parent
    for name, dim in declared.items():
        command = str(dim.get("command") or "")
        if dim.get("source") != "tree" or not command:
            continue
        anchors: list[str] = []
        for quoted in _CMD_ANCHOR_RE.findall(command):
            parts = quoted.split("/")[1:] if quoted.startswith("/") else [quoted]
            anchors += [s for s in parts if len(s) >= 8 and not set(s) & _RE_META]
        if not anchors:
            continue
        # Пути ищутся в команде БЕЗ процитированных якорей: `grep -c 'bin/store.sh'` — это
        # ОБРАЗЕЦ ПОИСКА, а не файл, который обязан лежать рядом с носителем.
        paths = dict.fromkeys(_CMD_PATH_RE.findall(_CMD_ANCHOR_RE.sub(" ", command)))
        texts = {rel: (base / rel).read_text(encoding="utf-8", errors="replace")
                 for rel in paths if (base / rel).is_file()}
        if not texts:
            # Носитель, прочитанный ИЗВНЕ своего дерева (`--carrier` на стенде), адресатов
            # рядом не имеет. Это «не проверял», и оно ОБЪЯВЛЯЕТСЯ: отказом здесь прибор судил
            # бы чужое дерево, а молчанием — повторил бы ровно тот дефект, что чинит.
            rep.say(f"  [INFO] {name}: разрешимость якорей команды НЕ проверена — рядом с "
                    f"носителем нет ни одного адресата {list(paths) or '[]'}.")
            continue
        for part in anchors:
            if not any(part in body for body in texts.values()):
                rep.fail(RC_USAGE, f"  ✗ {name}: {ANCHOR_REFUSAL} ни в одном из "
                                   f"{sorted(texts)} — {part!r}. Команда напечатает ноль, и "
                                   f"«0 ≤ target» прочтётся как достижение цели.")


def check_degradations(doc: dict, rep: Report) -> dict[tuple[str, str], dict]:
    """Записи об ухудшении: форма проверяется ДО сравнения — пустая причина есть молчание."""
    out: dict[tuple[str, str], dict] = {}
    for rec in doc.get("degradations") or []:
        if not isinstance(rec, dict):
            rep.fail(RC_USAGE, "  ✗ запись об ухудшении не является записью")
            continue
        metric, wave = str(rec.get("metric") or ""), str(rec.get("wave") or "")
        if not metric or not wave:
            rep.fail(RC_USAGE, "  ✗ запись об ухудшении без имени метрики или без волны")
            continue
        if not str(rec.get("reason") or "").strip():
            rep.fail(RC_VIOLATION, f"  ✗ запись об ухудшении {metric} (волна {wave}) без причины: "
                                   f"пустая причина — это молчание, а не объявление.")
        if "carriesThresholdForward" not in rec:
            rep.fail(RC_USAGE, f"  ✗ запись об ухудшении {metric} (волна {wave}) без поля "
                               f"carriesThresholdForward: умолчания у поля НЕТ — переносится "
                               f"порог следующей волне или нет, обязана сказать запись.")
        out[(wave, metric)] = rec
    return out


def split_series(doc: dict, declared: dict, rep: Report) -> list[dict]:
    """Ряд как список блоков волн; строки с именем вне закрытого набора названы, а не пропущены
    молча — молчаливый пропуск сделал бы волну «сравнённой»."""
    blocks: list[dict] = []
    for block in doc.get("series") or []:
        if not isinstance(block, dict) or not block.get("wave"):
            rep.fail(RC_USAGE, "  ✗ блок ряда без ключа `wave`")
            continue
        rows = [r for r in (block.get("values") or []) if isinstance(r, dict)]
        for row in rows:
            name = str(row.get("metric") or "")
            if name not in declared:
                rep.fail(RC_USAGE, f"  ✗ строка ряда волны {block['wave']} называет метрику "
                                   f"{name!r}, которой нет в объявленном наборе размерностей.")
            if "task" in row and "comparableClass" not in row:
                rep.fail(RC_USAGE, f"  ✗ строка ряда волны {block['wave']}, метрика {name!r}: "
                                   f"величина снята с ЗАДАЧИ {row.get('task')!r} и не объявляет "
                                   f"comparableClass — умолчания у поля НЕТ (ADR-107 Д8). "
                                   f"Сопоставима ли задача по КЛАССУ с базой, обязана сказать "
                                   f"запись: иначе задача меньшего класса подтверждает "
                                   f"удешевление тем, что мерила другое.")
        block["_rows"] = rows
        blocks.append(block)
    return blocks


def row_of(block: dict, metric: str) -> dict | None:
    for row in block.get("_rows") or []:
        if str(row.get("metric") or "") == metric:
            return row
    return None


def describe(carrier: Path, block: dict, row: dict, when: str) -> str:
    label = f" ({block['label']})" if block.get("label") else ""
    return (f"  {when} {block['wave']}{label}: {row['metric']} = {row.get('value')} "
            f"{row.get('unit')}, commit {str(row.get('commit'))[:7]}, "
            f"команда `{row.get('command')}`")


def row_usable(carrier: Path, block: dict, row: dict, rep: Report, root: Path | None) -> bool:
    """Строка самодостаточна? Отсутствие коммита и неразрешимый коммит — «НЕ СМОГ ПРОВЕРИТЬ»
    (код 1), а не нарушение ряда: величина без коммита невоспроизводима."""
    missing = [f for f in ROW_FIELDS if row.get(f) in (None, "")]
    if missing:
        rep.fail(RC_CANNOT, f"  ✗ {row.get('metric')} (волна {block['wave']}): строка ряда не "
                            f"самодостаточна — нет полей {', '.join(missing)}. Величина без "
                            f"коммита невоспроизводима, и это НЕ СМОГ ПРОВЕРИТЬ, а не «чисто».")
        return False
    sha = str(row["commit"])
    if root is None:
        rep.say(f"  [INFO] {row['metric']} (волна {block['wave']}): коммит {sha[:7]} НЕ проверен "
                f"— у дерева нет своей истории git. Это «нечего проверять», не «не смог».")
        return True
    if not commit_resolves(root, sha):
        rep.fail(RC_CANNOT, f"  ✗ {row['metric']} (волна {block['wave']}): коммит {sha} строки "
                            f"ряда в дереве не разрешается — величина невоспроизводима.")
        return False
    return True


def compare_metric(carrier: Path, name: str, dim: dict, base_block: dict | None,
                   base_row: dict | None, cur_block: dict | None, cur_row: dict | None,
                   degradations: dict, rep: Report, root: Path | None) -> None:
    """P2 — сравнение ПАРЫ ЗАПИСЕЙ. Порог берётся из ряда ДО всякого сегодняшнего измерения,
    потому что сегодняшнего измерения прибор не снимает вовсе."""
    if dim.get("source") == "absent":
        rep.say(f"  [INFO] {name}: объявленный отказ — {dim.get('reason')} "
                f"(носитель: {dim.get('expectedCarrier')}, волна: {dim.get('expectedWave')})")
        return
    if base_row is not None and base_row.get("status") == "not-measured":
        rep.say(f"  [INFO] {name}: база волны {base_block['wave']} объявлена неснятой — "
                f"{base_row.get('reason')} (ожидается: {base_row.get('expectedCarrier')}, "
                f"волна {base_row.get('expectedWave')})")
        return
    if base_row is None:
        rep.fail(RC_CANNOT, f"  ✗ {name}: размерность объявлена, но строки НИ ОДНОЙ закрытой "
                            f"волны по ней в ряду нет. Отсутствие базы — это НЕ СМОГ ПРОВЕРИТЬ, "
                            f"а не «нечего проверять» (ADR-007 Д1).")
        return
    if not row_usable(carrier, base_block, base_row, rep, root):
        return
    rep.say(describe(carrier, base_block, base_row, "база   "))
    if cur_row is None:
        # Имя волны НЕ подставляется плейсхолдером: «волна ? открыта» — выдуманное значение,
        # а прибор обязан называть состояние, а не заполнять пропуск знаком (ADR-007 Д1).
        where = (f"волна {cur_block['wave']} открыта, строки пишутся на закрытии"
                 if cur_block else "открытой волны нет — сравнивать базу не с чем")
        rep.say(f"  ✓ {name}: база принята, сегодняшнего измерения в ряду ещё нет — {where}.")
        return
    if not row_usable(carrier, cur_block, cur_row, rep, root):
        return
    rep.say(describe(carrier, cur_block, cur_row, "сегодня"))
    if str(base_row.get("profile")) != str(cur_row.get("profile")):
        rep.fail(RC_VIOLATION, f"  ✗ {name}: ПРАВИЛА СЧЁТА РАЗОШЛИСЬ — величины между собой НЕ "
                               f"сравниваются.\n"
                               f"      правило базы:    {base_row.get('profile')}\n"
                               f"      правило сегодня: {cur_row.get('profile')}")
        return
    prev, cur = base_row.get("value"), cur_row.get("value")
    worse = cur > prev if dim.get("direction") == "lower-is-better" else cur < prev
    if not worse:
        rep.say(f"  ✓ {name}: {cur} не хуже {prev} {base_row.get('unit')} "
                f"(цель выпуска: {dim.get('target')}) — ряд держит.")
        return
    rec = degradations.get((str(cur_block["wave"]), name))
    if rec is not None and str(rec.get("reason") or "").strip():
        rep.say(f"  ✓ {name}: ухудшение {prev} → {cur} объявлено НАМЕРЕННЫМ записью волны "
                f"{rec.get('wave')}; причина: {rec.get('reason')}; "
                f"carriesThresholdForward: {rec.get('carriesThresholdForward')}")
        return
    rep.fail(RC_VIOLATION, f"  ✗ НАРУШЕНИЕ РЯДА {name}: {cur} хуже {prev} "
                           f"{base_row.get('unit')} и записи об ухудшении с причиной нет. "
                           f"Попадание в цель выпуска ({dim.get('target')}) нарушения ряда не "
                           f"гасит: цель — обязательство релиза, порог — прошлое измерение.")


def check_crossbase(carrier: Path, declared: dict, gates: dict, rep: Report) -> None:
    """Одна размерность с двумя базами в двух носителях: расхождение обязано быть ОБЪЯВЛЕНО
    ссылкой `crossBase`, иначе прибор не вправе выбрать одну из баз втихую."""
    for name, dim in declared.items():
        if name not in gates or dim.get("crossBase"):
            continue
        rep.fail(RC_CANNOT, f"  ✗ {name}: две базы в двух носителях и ни одна не названа другой. "
                            f"{carrier} — база ряда волн; {GATES_NAME} → "
                            f"sessionCostBudget.dimensions[{name}].base = {gates[name]}. "
                            f"Объяви ссылку crossBase в строке размерности.")


def check_open_wave(doc: dict, blocks: list[dict], closing: str | None, rep: Report) -> None:
    """P1 — указатель открытой волны против контура И. Механический зуб предусловия: волна,
    закрытая в сторе без строк в ряду, даёт код 1, а не память роли."""
    raw = doc.get("openWave", "__missing__")
    # Между закрытием волны и открытием следующей ОТКРЫТОЙ ВОЛНЫ НЕТ, и это состояние обязано
    # быть выразимо: иначе сразу после `close_route` носитель не может быть одновременно верным
    # и принятым (найдено DEV-459 последним шагом волны NA-EPIC-53 на самом себе). Отличаем
    # объявленное отсутствие от забывчивости тем же приёмом, что и везде в этом приборе:
    # ключ ЕСТЬ со значением `null` — объявление; ключа НЕТ вовсе — отказ.
    if raw is None:
        rep.say("  [INFO] P1: открытой волны нет — `openWave: null` объявлен явно. Ряд сверять "
                "не с чем, и это НЕ пропуск: ключ присутствует. Следующая волна ставит сюда "
                "свой эпик тем же коммитом, что открывает бид.")
        return
    open_wave = str(raw or "") if raw != "__missing__" else ""
    if not open_wave:
        rep.fail(RC_CANNOT, "  ✗ носитель не объявляет openWave — сверить ряд с контуром И нечем. "
                            "Открытой волны нет? Напиши `openWave: null` — объявленное "
                            "отсутствие, а не отсутствие ключа.")
        return
    block = next((b for b in blocks if str(b["wave"]) == open_wave), None)
    if block is not None and block.get("closed") is True:
        rep.fail(RC_CANNOT, f"  ✗ ряд разошёлся с контуром И: openWave называет {open_wave}, а "
                            f"строка этой волны в ряду помечена closed: true.")
    if closing is None:
        rep.say(f"  [INFO] P1: контур И не опрашивается вне предусловия `close_route` — "
                f"открытой волной объявлена {open_wave}.")
        return
    if shutil.which("bd") is None:
        rep.fail(RC_CANNOT, "  ✗ бинарь bd не найден — контур И недоступен, а предусловие "
                            "`close_route` без него не проверяется. Это НЕ СМОГ ПРОВЕРИТЬ.")
        return
    try:
        out = subprocess.run(["bd", "list", "--status", "open"], capture_output=True,
                             text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        rep.fail(RC_CANNOT, "  ✗ bd не ответил — состояние контура И НЕ прочитано")
        return
    if out.returncode != 0:
        rep.fail(RC_CANNOT, f"  ✗ bd вернул {out.returncode} — состояние контура И НЕ прочитано")
        return
    closing_block = next((b for b in blocks if str(b["wave"]) == closing), None)
    if closing not in out.stdout and not (closing_block or {}).get("_rows"):
        rep.fail(RC_CANNOT, f"  ✗ волна {closing} закрыта в сторе, а строк по ней в ряду нет — "
                            f"ряд разошёлся с контуром И.")


def check_immutability(carrier: Path, doc: dict, since: str | None, rep: Report,
                       root: Path | None) -> None:
    """P3 — неизменяемость закрытых строк. Правка прошлой строки есть подгонка порога под
    измеренное; новая величина порогом не становится."""
    if since is None:
        rep.say("  [INFO] P3 (неизменяемость закрытых строк) не исполнен: база дифа не названа "
                "(--since <ref>). Это объявленный пропуск, а не проверка.")
        return
    if root is None:
        rep.say("  [INFO] P3 (неизменяемость закрытых строк) не исполнен: у дерева нет своей "
                "истории git — источника разрешения нет, значит нет и предмета.")
        return
    rel = os.path.relpath(carrier.resolve(), root.resolve())
    shown = _git(root, "show", f"{since}:{rel}")
    if shown.returncode != 0:
        rep.say(f"  [INFO] P3 не исполнен: носителя {rel} в {since} нет — сравнивать не с чем.")
        return
    try:
        old = yaml.safe_load(shown.stdout) or {}
    except yaml.YAMLError:
        rep.say(f"  [INFO] P3 не исполнен: носитель в {since} не разбирается как YAML.")
        return
    old_rows = {
        (str(b.get("wave")), str(r.get("metric"))): r.get("value")
        for b in (old.get("series") or []) if isinstance(b, dict) and b.get("closed") is True
        for r in (b.get("values") or []) if isinstance(r, dict)
    }
    for block in doc.get("series") or []:
        if not isinstance(block, dict) or block.get("closed") is not True:
            continue
        for row in block.get("values") or []:
            key = (str(block.get("wave")), str(row.get("metric")))
            if key in old_rows and old_rows[key] != row.get("value"):
                rep.fail(RC_VIOLATION, f"  ✗ ПРАВКА ЗАКРЫТОЙ СТРОКИ: волна {key[0]}, метрика "
                                       f"{key[1]} — {old_rows[key]} в {since}, {row.get('value')} "
                                       f"сегодня. Новая величина порогом НЕ становится.")


_UPGRADE_COST_SECTION_RE = re.compile(r"^###\s*Цена обновления\s*$", re.MULTILINE)
_RELEASE_HEADING_RE = re.compile(r"^##\s*\[([^\]]+)\]", re.MULTILINE)
_DIM_INVOCATIONS_RE = re.compile(r"upgrade-invocations-per-tree:\s*(\d+)")
_DIM_MINUTES_RE = re.compile(r"upgrade-minutes-per-tree:\s*(\d+)")
_DIM_TRAPS_RE = re.compile(r"upgrade-manual-traps-and-regressions:\s*(\d+)/(\d+)")


def _release_block(changelog_text: str, release: str) -> str | None:
    """Возвращает текст блока ОДНОГО релиза (`## [release]` … до следующего `## [` или конца
    файла) — секция «Цена обновления» BA-078 обязана называть числа ИМЕННО этого выпуска, не
    произвольного интервала (Requirement AC-019/020)."""
    headings = list(_RELEASE_HEADING_RE.finditer(changelog_text))
    for i, m in enumerate(headings):
        if m.group(1) != release:
            continue
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(changelog_text)
        return changelog_text[start:end]
    return None


def _upgrade_cost_section(block_text: str) -> str | None:
    m = _UPGRADE_COST_SECTION_RE.search(block_text)
    if not m:
        return None
    rest = block_text[m.end():]
    next_heading = re.search(r"^##", rest, re.MULTILINE)
    return rest[: next_heading.start()] if next_heading else rest


def _parse_three_dims(text: str) -> dict[str, str] | None:
    inv = _DIM_INVOCATIONS_RE.search(text)
    minutes = _DIM_MINUTES_RE.search(text)
    traps = _DIM_TRAPS_RE.search(text)
    if not (inv and minutes and traps):
        return None
    return {
        "invocations": inv.group(1),
        "minutes": minutes.group(1),
        "traps": traps.group(1),
        "regressions": traps.group(2),
    }


def check_changelog_upgrade_cost_section(changelog: Path, release: str | None,
                                          census_root: str | None) -> int:
    """AC-019/020 (BA-078, ADR-109-spec §5): секция «Цена обновления» — единственный
    источник, из которого храповик читает три размерности подъёма ЗА ЭТОТ выпуск. Молчание
    (секция отсутствует) SHALL быть явным отказом, не подстановкой прошлого значения
    (AC-019); расхождение чисел секции с `fleet-census.sh` на коммите тега SHALL считаться
    нарушением, не альтернативным источником истины (AC-020). Инструмент назван требованием
    (BA-078 таблица AC-019: `check-ratchet.py`), не выбран этим Dev-решением (at-design §5.3)."""
    if release is None:
        print("ОШИБКА: --release не назван — секцию какого выпуска сравнивать, неизвестно.",
              file=sys.stderr)
        return RC_USAGE
    if not changelog.is_file():
        print(f"ОШИБКА: {changelog} не читается.", file=sys.stderr)
        return RC_USAGE
    text = changelog.read_text(encoding="utf-8")
    block = _release_block(text, release)
    if block is None:
        print(f"ОШИБКА: CHANGELOG не несёт выпуск [{release}] — секцию «Цена обновления» "
              f"сравнивать не с чем.", file=sys.stderr)
        return RC_USAGE
    section = _upgrade_cost_section(block)
    if section is None:
        print(f"ОШИБКА: выпуск {release} не несёт секцию «Цена обновления» — нет источника "
              f"для трёх размерностей подъёма этого выпуска (AC-019). Прошлое значение ряда "
              f"НЕ подставляется.", file=sys.stderr)
        return RC_USAGE
    declared = _parse_three_dims(section)
    if declared is None:
        print(f"ОШИБКА: секция «Цена обновления» выпуска {release} не несёт все три "
              f"размерности в распознаваемом формате.", file=sys.stderr)
        return RC_USAGE
    print(f"Секция «Цена обновления» выпуска {release}: invocations={declared['invocations']} "
          f"minutes={declared['minutes']} traps/regressions={declared['traps']}/"
          f"{declared['regressions']}")
    if census_root is None:
        return RC_OK
    fleet_census = Path(__file__).resolve().parent / "fleet-census.sh"
    try:
        proc = subprocess.run(["bash", str(fleet_census), census_root],
                               capture_output=True, text=True, timeout=120)
    except OSError as exc:
        print(f"ОШИБКА: не смог запустить {fleet_census}: {exc}", file=sys.stderr)
        return RC_USAGE
    measured = _parse_three_dims(proc.stdout)
    if measured is None or measured != declared:
        print(f"НАРУШЕНИЕ (расход чисел): секция «Цена обновления» ({declared}) не совпадает "
              f"с выводом fleet-census.sh на census-root ({measured}) — это нарушение, не "
              f"альтернативный источник истины (AC-020).", file=sys.stderr)
        return RC_VIOLATION
    print("OK: секция «Цена обновления» совпадает с fleet-census.sh.")
    return RC_OK


def resolve_carrier(named: str | None, cwd: Path, root: Path | None) -> tuple[Path | None, int]:
    """Носитель, НАЗВАННЫЙ вызывающим и не читаемый, — код 2, а не тихий откат к умолчанию:
    откат напечатал бы ЧУЖОЙ вердикт под видом запрошенного."""
    if named is not None:
        path = Path(named)
        if not path.is_file():
            print(f"ОШИБКА: носитель назван вызывающим и не читается — {path}. Отката к "
                  f"умолчанию {CARRIER_NAME} НЕТ: чужой вердикт под видом запрошенного "
                  f"неотличим от проверки.", file=sys.stderr)
            return None, RC_USAGE
        return path, RC_OK
    path = (root or cwd) / CARRIER_NAME
    if not path.is_file():
        print(f"[INFO] храповик волны: носителя {CARRIER_NAME} в этом дереве нет — сравнивать "
              f"нечего, exit-код не меняется (громкий ноль, ADR-085 Д1(3)).")
        print(f"       Носитель несёт ряд «волна → величина» по объявленному набору метрик: "
              f"порогом служит ПРОШЛОЕ измерение ряда, а не рукописная константа. Заведите "
              f"{CARRIER_NAME} в корне дерева, и проверка начнёт работать на ваших волнах.")
        return None, RC_OK
    return path, RC_OK


def main() -> int:
    ap = argparse.ArgumentParser(description="храповик волны: ряд записей, а не потолок")
    ap.add_argument("--carrier", default=None, help=f"носитель ряда (умолчание — {CARRIER_NAME})")
    ap.add_argument("--closing", default=None, help="режим предусловия close_route: эпик волны")
    ap.add_argument("--since", default=None, help="база дифа для предиката неизменяемости")
    ap.add_argument("--changelog", default=None,
                     help="путь к CHANGELOG.md — проверка секции «Цена обновления» "
                          "(AC-019/020, BA-078), режим не связан с --carrier/--closing")
    ap.add_argument("--release", default=None,
                     help="версия выпуска, чья секция «Цена обновления» проверяется")
    ap.add_argument("--census-root", default=None,
                     help="корень для сверки чисел секции с fleet-census.sh (AC-020)")
    args = ap.parse_args()

    if args.changelog is not None:
        return check_changelog_upgrade_cost_section(
            Path(args.changelog), args.release, args.census_root)

    cwd = Path.cwd()
    root = git_root(cwd)
    carrier, rc = resolve_carrier(args.carrier, cwd, root)
    if carrier is None:
        return rc

    try:
        doc = yaml.safe_load(carrier.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        print(f"ОШИБКА: носитель {carrier} не разбирается как YAML: {exc}", file=sys.stderr)
        return RC_USAGE
    if not isinstance(doc, dict):
        print(f"ОШИБКА: носитель {carrier} не является записью верхнего уровня", file=sys.stderr)
        return RC_USAGE

    rep = Report()
    rep.say(f"▸ храповик волны — носитель {carrier}")
    declared = check_form(doc, rep)
    check_tree_anchors(carrier, declared, rep)
    degradations = check_degradations(doc, rep)
    blocks = split_series(doc, declared, rep)
    check_crossbase(carrier, declared, gates_dimensions(carrier, cwd), rep)
    check_open_wave(doc, blocks, args.closing, rep)

    current = args.closing or str(doc.get("openWave") or "")
    cur_block = next((b for b in blocks if str(b["wave"]) == current), None)
    base_blocks = [b for b in blocks if b.get("closed") is True and str(b["wave"]) != current]
    for name, dim in declared.items():
        if _PATH_LIKE.search(name):
            continue
        base_block = next((b for b in reversed(base_blocks) if row_of(b, name)), None)
        compare_metric(carrier, name, dim, base_block,
                       row_of(base_block, name) if base_block else None,
                       cur_block, row_of(cur_block, name) if cur_block else None,
                       degradations, rep, root)
    check_immutability(carrier, doc, args.since, rep, root)
    return rep.flush()


if __name__ == "__main__":
    raise SystemExit(main())
