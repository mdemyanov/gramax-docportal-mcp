# /// script
# requires-python = ">=3.11"
# ///
"""check-branch-discipline.py — читатель объявления дисциплины ветвления (ADR-081 Д2/Д7).

Предмет — ключ `branchDiscipline` в `.nauta-gates.yaml` (схема — §2 спутника ADR-081):

    branchDiscipline:
      profile: single            # single | team
      integrationBranchPrefix: epic-
      worktreeLocation: .claude/worktrees/

Гейт заводится потому, что объявление без читателя молчит: до него профиль репозитория
ВЫВОДИЛСЯ (по наличию remote, по привычке волны), а не объявлялся, и норма capability
`role-branch-discipline` «Where no declaration exists, the discipline SHALL signal
"undetermined" rather than assume either profile» не имела прибора вовсе.

Норма отсутствия — прецедент ADR-031 Д3 / ADR-071 Д1 дословно: файла или блока нет →
умолчание из кода, exit 0, провенанс `default (…)`; блок задан, а `profile` пуст или не из
перечня → ERROR, exit 2 (пустое значение при ЗАДАННОМ ключе есть отказ, ADR-072 Д6, и права
на умолчание не даёт — оно принадлежит только отсутствующему ключу).

Разбор — руками, без PyYAML: гейт обязан быть исполним голым `python3 <файл> <корень>`
(контракт вызова, заданный стабом QA-078 `test_ac02_absent_profile_declaration_is_printed_
not_silent`), а не только через `uv run` с зависимостями. Читается ровно один верхнеуровневый
блок плоских скалярных ключей — на этой форме YAML-парсер и построчный разбор совпадают.

Второй предмет — СТОРОЖ ШВА §4.4 (см. `_guard_branch_names`).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PROFILES = ("single", "team")
DEFAULT_INTEGRATION_PREFIX = "epic-"
DEFAULT_WORKTREE_LOCATION = ".claude/worktrees/"

#: Форма имени ветки роли: последний сегмент после `/` — адрес задачи (Д2, AC-058-10).
#: Одна форма на оба профиля: у голого `dev-130` разделителя нет, сегмент равен имени.
TASK_NUMBER_RE = re.compile(r"^[a-z][a-z0-9]*-\d{2,4}$")

#: Имя, которое ветке рабочей копии даёт САМА платформа (`isolation: "worktree"`).
#: Параметра, задающего это имя, у Agent-инструмента не замерено (§6 спутника ADR-081):
#: имя возвращается, а не задаётся, поэтому шов §4.4 — переименование первым действием роли.
PLATFORM_BRANCH_RE = re.compile(r"^worktree-agent-")

_EXIT_OK = 0
_EXIT_ERROR = 2

#: Путь носителя, печатаемый в тексте отказов сторожей #20/#23 (ADR-115 §Смягчения: «отказ
#: сторожа `check-branch-discipline.py` печатает путь носителя, чтобы указатель в промте не
#: был единственной дорогой к тексту» — ADR-115-carriers-for-the-four-wave-blockers.md).
CARRIER_SPEC_PATH = (
    "content/40-architecture/ADR-081-isolation-by-simultaneity-branch-per-role-task-spec.md")


def _read_block(text: str, name: str) -> dict[str, str] | None:
    """Верхнеуровневый блок как плоский словарь. None — блока в тексте нет.

    Ключ с пустым значением попадает в словарь пустой строкой: «ключ задан, значение пусто»
    и «ключа нет» обязаны быть РАЗЛИЧИМЫ (ADR-072 Д6) — иначе отказ выглядел бы умолчанием.
    """
    out: dict[str, str] = {}
    inside = False
    found = False
    for line in text.splitlines():
        if re.match(rf"^{re.escape(name)}\s*:\s*(?:#.*)?$", line):
            inside, found = True, True
            continue
        if inside:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            m = re.match(r"^\s+([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*(?:#.*)?$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip("\"'")
    return out if found else None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, timeout=120)


def _worktrees(root: Path) -> list[dict[str, str]]:
    proc = _git(root, "worktree", "list", "--porcelain")
    if proc.returncode != 0:
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        head, _, rest = line.partition(" ")
        current[head] = rest
    if current:
        entries.append(current)
    return entries


def _guard_branch_names(root: Path, prefix: str, profile: str) -> tuple[list[str], list[str]]:
    """Сторож шва §4.4: «роль переименовала свою ветку» — наблюдаемо, а не на честном слове.

    Вердикт владельца 2026-08-31 закрыл развилку §6 в пользу шва: имя ветки копии даёт
    ПЛАТФОРМА (`worktree-agent-<hash>`), и адресом задачи оно становится первым действием
    роли (`git branch -m <номер>`). Шов без сторожа неотличим от его отсутствия, поэтому
    здесь и живёт прибор, умеющий сказать «роль не переименовала ветку».

    `profile` (ADR-110 Д1, issue #18, довершает ADR-081 Д2 первым предложением — форма имени
    по профилю, а не переоткрывает его) судит ФОРМУ имени: `single` отказывает имени с `/`
    (форма несёт чужую, командную гарантию непересечения — AC-058-09 в профиле, который её не
    объявлял); `team` отказывает имени БЕЗ `/` (форма не несёт `<handle>/`, декларация `team`
    не защищает от коллизии AC-058-09). Судится наличие хотя бы одного `/`, не число сегментов
    — имя `alice/bob/dev-130` несёт `/` и формой `team` не отказывается, `rsplit("/", 1)[-1]`
    извлечения номера при этом не меняется (Д2 второй половины — «извлечение — одна форма» —
    не переоткрывается ни в одной ветке).

    Возвращает (отказы, предупреждения):

    * ОТКАЗ — имя ветки копии всё ещё несёт форму самой платформы. Условие узкое намеренно:
      такое имя ни один человек не выбирает, поэтому ложного отказа у потребителя быть не
      может; это ровно «первое действие роли не выполнено».
    * ПРЕДУПРЕЖДЕНИЕ — имя копии объявленной формы номера не даёт по любой другой причине.
      Отказом это не делается: отличить чужую рабочую ветку потребителя от невыполненного
      переименования нечем, а гейт, красящий на догадке, — хуже отсутствующего.

    Чего сторож НЕ ловит (названо, а не умолчано):
      1. **окно самого шва** — промежуток между созданием копии платформой и первым действием
         роли: пока гейт не запущен, имя никем не наблюдается. Сторож — прибор момента
         прогона, а не непрерывного надзора; цену этого окна владелец принял сознательно;
      2. **переименование в ЧУЖОЙ номер** — `git branch -m dev-999` в копии задачи DEV-130
         проходит: форма выполнена, а сверить номер с задачей нечем — пространство `task`
         в `.nauta-ids.yaml` объявлено с пустым `prefix`, `home: []`, `allocation: external`
         (находка QA-078), то есть номеров ролевых задач реестр не хранит;
      3. **копии вне корня дерева** — стенды прогонов и копии в других каталогах из суда
         исключены: иначе гейт краснел бы на мусоре чужого теста (тот же довод, что у
         `_stale_copies` стабов QA-078);
      4. **копию, уже удалённую** к моменту прогона, и работу роли, не создавшей копию вовсе
         (одиночный запуск — изоляции нет по Д1, ветка заводится в интеграционном дереве).
    """
    denials: list[str] = []
    warnings: list[str] = []
    entries = _worktrees(root)
    if not entries:
        return denials, warnings
    main = Path(entries[0].get("worktree", str(root)))
    for entry in entries[1:]:
        path_raw, branch = entry.get("worktree", ""), entry.get("branch", "")
        if not path_raw or not branch:
            continue                       # detached-копия ветки не держит — судить нечего
        path = Path(path_raw)
        try:
            path.relative_to(main)
        except ValueError:
            continue                       # копия вне корня дерева (граница 3 выше)
        name = branch.replace("refs/heads/", "")
        if name.startswith(prefix):
            continue                       # интеграционная ветка эпика — не ветка роли
        if PLATFORM_BRANCH_RE.match(name):
            denials.append(
                f"{path} — ветка `{name}`: имя выдано платформой и не переименовано. Первое "
                f"действие роли в своей копии — `git branch -m <номер>` (ADR-081 §4.4); пока "
                f"оно не выполнено, имя ветки адресом задачи не является (AC-058-10)."
            )
            continue
        has_slash = "/" in name
        if profile == "single" and has_slash:
            denials.append(
                f"{path} — ветка `{name}`: форма несёт разделение пространства имён профиля "
                f"`team` (`<handle>/<номер>`), а объявлен `single` (ADR-081 Д2, ADR-110 Д1, "
                f"AC-058-09)."
            )
        elif profile == "team" and not has_slash:
            denials.append(
                f"{path} — ветка `{name}`: имя не несёт `<handle>/`, декларация профиля "
                f"`team` не защищает от коллизии AC-058-09 (ADR-081 Д2, ADR-110 Д1)."
            )
        elif TASK_NUMBER_RE.match(name.rsplit("/", 1)[-1]) is None:
            warnings.append(
                f"{path} — ветка `{name}`: объявленной формой (последний сегмент после `/`) "
                f"номер задачи не извлекается."
            )
    return denials, warnings


def _guard_stale_copies(root: Path, prefix: str) -> list[str]:
    """Сторож #20 (ADR-115 Д4, область СУЖЕНА решением координатора 2026-09-24, DEV-478 Н-3):
    копия отстаёт от HEAD ветки эпика — ПРЕДУПРЕЖДЕНИЕ, не отказ.

    Проверяемое действие дословно из Д4: `git merge-base --is-ancestor <HEAD эпика> HEAD` в
    каждой копии. HEAD эпика — коммит главной рабочей копии (`_worktrees()[0]`, тот же
    источник, которым `_guard_branch_names` меряет корень). Копия РОВНО на HEAD эпика или
    впереди него — тишина (HEAD эпика остаётся её предком); копия на коммите, который HEAD
    эпика уже обогнал, — предупреждение: зелёный прогон в такой копии не доказывает
    актуальность, но само отставание — состояние НОРМАЛЬНОЕ и ожидаемое (координатор
    коммитит в ветку эпика по ходу волны, это ритуал, а не дефект). Отказом остаётся только
    расхождение ветвлением — см. `_guard_out_of_location_copies` (#23) и границу ниже.

    Границы (симметрично §6 спутника ADR-115): судятся только копии из `git worktree list` —
    `cp -R` в песочницу в перечне не значится и не судится. Копий ВНЕ корня дерева это не
    исключает намеренно: расхождение #20 — про отставание от ветки эпика, а не про адрес
    копии (тот довод принадлежит только #23, узкому по поправке владельца 2026-09-22).
    """
    warnings: list[str] = []
    entries = _worktrees(root)
    if not entries:
        return warnings
    epic_head = entries[0].get("HEAD", "")
    if not epic_head:
        return warnings
    for entry in entries[1:]:
        path_raw, branch, head = (entry.get("worktree", ""), entry.get("branch", ""),
                                  entry.get("HEAD", ""))
        if not path_raw or not branch or not head:
            continue                       # detached или неполная запись — судить нечем
        name = branch.replace("refs/heads/", "")
        if name.startswith(prefix):
            continue                       # интеграционная ветка эпика — не копия роли
        proc = _git(root, "merge-base", "--is-ancestor", epic_head, head)
        if proc.returncode != 0:
            warnings.append(
                f"{path_raw} — ветка `{name}`: копия отстаёт от HEAD ветки эпика "
                f"({epic_head[:12]}); зелёный прогон в ней не доказательство актуальности "
                f"(ADR-115 Д4, #20, область сужена координатором 2026-09-24). Обнови копию "
                f"(`git -C {path_raw} rebase {epic_head}` или пересоздай её). "
                f"Носитель: {CARRIER_SPEC_PATH}."
            )
    return warnings


def _guard_out_of_location_copies(root: Path, location: str, prefix: str,
                                  declared: bool) -> tuple[list[str], list[str]]:
    """Сторож #23 (ADR-115 Д4, СУЖЕННЫЙ поправкой владельца 2026-09-22, вариант (а)).

    Исходная формулировка Д4 («указатель копии разрешается ВНЕ `worktreeLocation`» без
    оговорки о корне) столкнулась с уже принятым `tests/test_dev130_branch_discipline_gate.py
    ::test_a_copy_outside_the_root_is_not_judged`, который для копии, зарегистрированной
    ЦЕЛИКОМ вне корня дерева, требует rc==0 дословным доводом: «копии вне корня — стенды чужих
    прогонов. Судить их значило бы краснеть на мусоре, который создал не этот репозиторий».
    Поправка сузила область: судится копия, чей указатель разрешается ВНУТРИ корня дерева, но
    вне объявленного `worktreeLocation`. Копия, зарегистрированная целиком вне корня, не
    судится этим сторожем — тот же довод, что уже несёт `_guard_branch_names` (граница 3 её
    докстроки), и он НЕ переоткрывается здесь.
    """
    denials: list[str] = []
    warnings: list[str] = []
    entries = _worktrees(root)
    if not entries:
        return denials, warnings
    main = Path(entries[0].get("worktree", str(root))).resolve()
    location_root = (main / location).resolve()
    for entry in entries[1:]:
        path_raw, branch = entry.get("worktree", ""), entry.get("branch", "")
        if not path_raw or not branch:
            continue
        path = Path(path_raw).resolve()
        try:
            path.relative_to(main)
        except ValueError:
            continue                       # копия вне корня дерева — не судится (поправка)
        name = branch.replace("refs/heads/", "")
        if name.startswith(prefix):
            continue                       # интеграционная ветка эпика — не копия роли
        try:
            path.relative_to(location_root)
        except ValueError:
            if declared:
                denials.append(
                    f"{path_raw} — ветка `{name}`: указатель копии разрешается внутри корня "
                    f"дерева, но вне ОБЪЯВЛЕННОГО тобой worktreeLocation ({location}) "
                    f"(ADR-115 Д4, #23, поправка владельца 2026-09-22). `git worktree repair` "
                    f"здесь не лечит — пересоздай копию внутри {location}. "
                    f"Носитель: {CARRIER_SPEC_PATH}."
                )
            else:
                warnings.append(
                    f"{path_raw} — ветка `{name}`: копия лежит вне {location}, но это место "
                    f"взято УМОЛЧАНИЕМ кода, а не твоим объявлением — отказа нет. Объяви своё "
                    f"место ключом branchDiscipline.worktreeLocation в .nauta-gates.yaml либо "
                    f"перенеси копию. Носитель: {CARRIER_SPEC_PATH}."
                )
    return denials, warnings


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else os.getcwd()).resolve()
    gates = root / ".nauta-gates.yaml"

    if not gates.is_file():
        block = None
        source = f"default (файла {gates.name} в дереве нет)"
    else:
        block = _read_block(gates.read_text(encoding="utf-8", errors="replace"),
                            "branchDiscipline")
        source = ("configured (.nauta-gates.yaml, блок branchDiscipline)" if block is not None
                  else f"default (блока branchDiscipline в {gates.name} нет)")

    profile = None if block is None else block.get("profile")
    prefix = ((block or {}).get("integrationBranchPrefix") or DEFAULT_INTEGRATION_PREFIX)
    location = ((block or {}).get("worktreeLocation") or DEFAULT_WORKTREE_LOCATION)

    if profile is not None and profile not in PROFILES:
        shown = repr(profile) if profile else "пустое значение"
        print("ERROR: branchDiscipline.profile — " + shown + ", вне перечня "
              + " | ".join(PROFILES), file=sys.stderr)
        print(f"  норма branchDiscipline: {source}", file=sys.stderr)
        print("  При ЗАДАННОМ ключе пустое или чужое значение есть отказ (ADR-072 Д6), а не", file=sys.stderr)
        print("  умолчание: право на умолчание принадлежит только ОТСУТСТВУЮЩЕМУ ключу.", file=sys.stderr)
        print("  Почини: впиши `profile: single` либо `profile: team`, либо убери ключ.", file=sys.stderr)
        return _EXIT_ERROR

    if profile is None:
        print("[INFO] профиль репозитория не объявлен — дисциплина ветвления undetermined "
              "(неопределена).")
        print(f"       норма branchDiscipline: {source}")
        print("       Это не «профиль single»: молчание разрешением ни одного профиля не")
        print("       является (capability role-branch-discipline). Объяви профиль ключом")
        print("       branchDiscipline.profile в .nauta-gates.yaml — single | team.")
        print("       Пока объявления нет, сторож имён веток рабочих копий не судит дерево.")
        return _EXIT_OK

    # Каждая группа сторожей несёт СВОЙ заголовок и СВОЮ строку «сторож не ловит» (DEV-478
    # Н-6): общий заголовок под тремя разными сторожами прятал бы, какой из них отказал и
    # где искать его слепые зоны.
    name_denials, name_warnings = _guard_branch_names(root, prefix, profile)
    stale_warnings = _guard_stale_copies(root, prefix)                    # #20 — ПРЕДУПРЕЖДЕНИЕ
    # #23 — отказ ТОЛЬКО против объявления самого потребителя. Место, взятое умолчанием
    # кода, даёт предупреждение: денить за раскладку, которой мы никогда не запрещали,
    # значило бы наказать человека ровно за тот шаг, который ему предлагает онбординг
    # (замер 2026-09-24 на дереве потребителя mail-plugin: копия в .worktrees/, профиль
    # не объявлен — сторож молчал; объявление профиля включило бы отказ на живой раскладке).
    location_declared = isinstance(block, dict) and block.get("worktreeLocation") is not None
    location_denials, location_warnings = _guard_out_of_location_copies(
        root, location, prefix, location_declared)
    warnings = name_warnings + stale_warnings + location_warnings
    denials = name_denials + location_denials
    # Строка вердикта печатается ПОСЛЕ опроса сторожа: иначе один прогон печатал бы «OK»
    # и «ERROR» разом, и читатель, глядящий на stdout, видел бы зелёное там, где отказ.
    head = "OK" if not denials else "[INFO]"
    print(f"{head}: профиль дисциплины ветвления — {profile}.")
    print(f"  норма branchDiscipline: {source}")
    print(f"  интеграционная ветка: префикс `{prefix}`; место копий: {location}")
    for line in warnings:
        print(f"  WARNING: {line}")
    if name_denials:
        print("ERROR: рабочая копия роли не переименовала свою ветку (шов ADR-081 §4.4)",
              file=sys.stderr)
        for line in name_denials:
            print(f"  {line}", file=sys.stderr)
        print("  Сторож не ловит: окно между созданием копии и первым действием роли, "
              "переименование", file=sys.stderr)
        print("  в чужой номер и копии вне корня дерева — см. докстроку "
              "_guard_branch_names.", file=sys.stderr)
    if location_denials:
        print("ERROR: указатель копии переписан вне объявленного worktreeLocation "
              "(ADR-115 Д4, #23)", file=sys.stderr)
        for line in location_denials:
            print(f"  {line}", file=sys.stderr)
        print("  Сторож не ловит: копии, чей указатель разрешается ЦЕЛИКОМ вне корня дерева "
              "(DEV-130), и указатель, перезаписанный `git worktree repair` уже ПОСЛЕ этого "
              "прогона — см. докстроку _guard_out_of_location_copies.", file=sys.stderr)
    if denials:
        return _EXIT_ERROR
    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
