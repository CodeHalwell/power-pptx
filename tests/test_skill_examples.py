"""The code examples in the shipped skill must stay in step with the library.

The skill is what coding agents read before they write against this API, so a
stale example is copied into real code. These checks are cheap and catch the
common ways an example rots: it stops parsing after an edit, it imports a name
that was renamed or removed, or it calls a function with arguments the function
no longer accepts.

Examples are allowed to be fragments: they may use names defined in an earlier
block (`slide`, `shape`, ...) and placeholder file names, so they are not
executed here. A block that is deliberately not Python belongs in a fence with
another language tag.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path
from typing import Iterator, NamedTuple

import pytest

from power_pptx.skill import skill_root

# -- a fence may sit inside a blockquote ("> ```python"); its lines then carry
# -- the same "> " prefix, which is stripped before parsing --
_FENCE = re.compile(r"^(?P<prefix>[ >]*)```python\n(?P<body>.*?)^(?P=prefix)```", re.DOTALL | re.M)


class _Example(NamedTuple):
    doc: str
    line: int
    source: str

    def __str__(self) -> str:
        return f"{self.doc}:{self.line}"


def _examples() -> Iterator[_Example]:
    root = skill_root()
    for path in [root / "SKILL.md", *sorted((root / "references").glob("*.md"))]:
        text = path.read_text(encoding="utf-8")
        for match in _FENCE.finditer(text):
            line = text[: match.start()].count("\n") + 2
            prefix = match.group("prefix")
            source = "".join(
                body_line[len(prefix) :] if body_line.startswith(prefix) else body_line
                for body_line in match.group("body").splitlines(keepends=True)
            )
            yield _Example(path.relative_to(root).as_posix(), line, source)


EXAMPLES = list(_examples())


def _is_power_pptx(module: str | None) -> bool:
    return (module or "").split(".")[0] == "power_pptx"


def _from_import_names(node: ast.ImportFrom) -> Iterator[tuple[int, str, str | None]]:
    """``from power_pptx.x import a, b`` -> (lineno, "power_pptx.x", "a"), ..."""
    if not _is_power_pptx(node.module):
        return
    for alias in node.names:
        yield node.lineno, node.module or "", None if alias.name == "*" else alias.name


def _import_names(node: ast.Import) -> Iterator[tuple[int, str, str | None]]:
    """``import power_pptx.x`` -> (lineno, "power_pptx.x", None)."""
    for alias in node.names:
        if _is_power_pptx(alias.name):
            yield node.lineno, alias.name, None


def _power_pptx_imports(tree: ast.AST) -> Iterator[tuple[int, str, str | None]]:
    """Yield (lineno, module, name) for each power_pptx import in *tree*."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            yield from _from_import_names(node)
        elif isinstance(node, ast.Import):
            yield from _import_names(node)


def _resolves(module: str, name: str | None) -> bool:
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return False
    if name is None or hasattr(mod, name):
        return True
    try:
        importlib.import_module(f"{module}.{name}")
    except ImportError:
        return False
    return True


def it_finds_the_examples():
    assert len(EXAMPLES) > 100


@pytest.mark.parametrize("example", EXAMPLES, ids=str)
def it_parses_every_python_example(example: _Example):
    try:
        ast.parse(example.source)
    except SyntaxError as exc:
        pytest.fail(f"{example.doc}:{example.line + (exc.lineno or 1) - 1}: {exc.msg}")


@pytest.mark.parametrize("example", EXAMPLES, ids=str)
def it_imports_only_names_that_exist(example: _Example):
    try:
        tree = ast.parse(example.source)
    except SyntaxError:
        pytest.skip("reported by it_parses_every_python_example")
    missing = [
        f"{example.doc}:{example.line + lineno - 1}: {module}{'.' + name if name else ''}"
        for lineno, module, name in _power_pptx_imports(tree)
        if not _resolves(module, name)
    ]
    assert missing == []


def _imported_callables(tree: ast.AST) -> dict[str, object]:
    """Map local name -> object for every power_pptx function or class imported."""
    found: dict[str, object] = {}
    for _, module, name in _power_pptx_imports(tree):
        if name is None:
            continue
        try:
            obj = getattr(importlib.import_module(module), name)
        except (ImportError, AttributeError):
            continue
        if callable(obj):
            found[name] = obj
    return found


def _signature_problem(func: object, call: ast.Call) -> str | None:
    """Return why *call* cannot bind to *func*, or None when it could."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        kw.arg is None for kw in call.keywords
    ):
        return None  # -- *args / **kwargs: cannot judge statically --
    try:
        signature = inspect.signature(func)  # pyright: ignore[reportArgumentType]
    except (TypeError, ValueError):
        return None
    placeholders = [object()] * len(call.args)
    keywords = {kw.arg: object() for kw in call.keywords if kw.arg}
    try:
        signature.bind(*placeholders, **keywords)
    except TypeError as exc:
        # -- Examples often leave arguments out for brevity; only flag a call
        # -- that passes something the signature cannot take.
        return None if "missing" in str(exc) else str(exc)
    return None


@pytest.mark.parametrize("example", EXAMPLES, ids=str)
def it_calls_imported_functions_with_arguments_they_accept(example: _Example):
    """Catch an example passing a keyword or extra argument the API dropped."""
    try:
        tree = ast.parse(example.source)
    except SyntaxError:
        pytest.skip("reported by it_parses_every_python_example")
    callables = _imported_callables(tree)
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func = callables.get(node.func.id)
            if func is None:
                continue
            problem = _signature_problem(func, node)
            if problem:
                problems.append(f"{example.doc}:{example.line + node.lineno - 1}: {problem}")
    assert problems == []


def it_reads_the_skill_from_the_installed_package():
    """The examples checked are the ones that ship, not a repository copy."""
    assert Path(skill_root(), "SKILL.md").is_file()
