#!/usr/bin/env python3
"""Assert that structural-logic modules contain no engine-specific literals.

Enforces SKILL.md §7: opcode values, callee IDs, field offsets, window constants
and text-classification regexes belong in the declarative dialect, not in the
code that consumes it. When they leak into code, dialect values stop being
traceable to evidence, classification rules cannot be counted or tested in
isolation, and porting to another game means copying the whole module.

Uses AST analysis, not text matching, so comments and docstrings are exempt and
`0x` inside strings is not confused with a numeric literal.

Exit code 0 = clean, 1 = violations found. Never mutates any input.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

# Small integers with no engine meaning: widths, alignments, indices, bit counts.
ALLOWED_INTS = set(range(-2, 65)) | {
    0x7F, 0xFF, 0xFFFF, 0xFFFFFFFF,   # generic masks
    100, 128, 256, 512, 1000, 1024, 4096, 8192, 65536,
    1024 * 1024, 64 * 1024 * 1024,
}

# Hex spelling gets a much tighter allowlist than the decimal one above. Opcodes,
# sub-opcodes and callee IDs are usually small (0x10, 0x2A), so exempting
# everything under 65 would let the most common engine constants through -- the
# exact class §7 names first. Writing a value in hex is a deliberate signal that
# it is a machine-level constant, so only generic masks are exempt.
HEX_GENERIC = {0x7F, 0xFF, 0xFFFF, 0xFFFFFF, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF}  # dialect-literal-ok: 门禁自身的通用掩码白名单

# Byte strings of three or more bytes in structural logic are almost always
# container signatures (b"PSB\x00", b"RIFF"). Genuinely generic constants are
# listed here; anything else needs `dialect-literal-ok` with a reason.
GENERIC_BYTES = {b"\xef\xbb\xbf"}  # UTF-8 BOM

# Regex features that indicate text-shape classification rather than parsing.
CLASSIFY_HINTS = re.compile(
    r"\\u[0-9a-fA-F]{4}"          # unicode ranges, e.g. hiragana blocks  dialect-literal-ok
    r"|\[\^?[^\]]*\\u"            # char class with unicode escapes
    r"|[぀-ヿ一-鿿]"  # literal CJK in a pattern
)

# `split` 故意不在此列：`str.split(":")` 比 `re.split` 常见得多，把它算作正则会产生大量
# 假阳性。只有明确带 re. 前缀的 split 才计入（见 _is_regex_call）。
REGEX_CALLS = {"compile", "match", "fullmatch", "search", "sub", "subn",
               "findall", "finditer"}

# 这些正则解析的是**工具自己的产物格式**（译文文件、ASM、报告），不是引擎方言，因此不该
# 被要求移入 dialect。判据是模式里出现自有格式的结构标记。
# 解析**自有产物格式**（译文文件、ASM、报告）或**完全通用**的模式，不属引擎方言，
# 因此不要求移入 dialect。判据：出现自有格式标记，或模式中不含任何引擎特定字面量。
OWN_FORMAT_HINTS = re.compile(
    r"idx=|sha256=|tag=|off=|inst=|src_sha256|source_encoding|dsat|TEXT/|"
    r"psbscn|###|"
    r"[○●]|"           # 双行文本的 ○ ● 标记
    r"\?\{\?\{")           # 占位符 {{XX}}

#: 内联正则中只有出现**非 ASCII 字面量**（CJK 字符类等）才是语言或引擎特定的文本形态判断。
#: 纯语法构成的模式（如 (\w+)=(\S+)）是通用解析，报它只会淹没真正的问题。
LANG_SPECIFIC_PATTERN = re.compile(r"[^\x00-\x7f]")

# §7's hard rule names hex literals, ID tables and regexes. A bare decimal cannot
# be classified automatically -- 500 may be an undocumented scan window (§1.6)
# while 80 is a harmless preview length -- so decimals are advisory only and do
# not fail the gate.
HARD_CODES = {"ENGINE_MAGIC", "ENGINE_ID_TABLE", "TEXT_SHAPE_REGEX",
              "INLINE_REGEX", "SYNTAX_ERROR"}


class Finding:
    __slots__ = ("path", "line", "col", "code", "detail")

    def __init__(self, path: Path, node: ast.AST, code: str, detail: str) -> None:
        self.path = path
        self.line = getattr(node, "lineno", 0)
        self.col = getattr(node, "col_offset", 0)
        self.code = code
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {"file": str(self.path), "line": self.line, "col": self.col,
                "code": self.code, "detail": self.detail}


class Visitor(ast.NodeVisitor):
    def __init__(self, path: Path, source: str, allow_lines: set[int]) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.allow_lines = allow_lines
        self.findings: list[Finding] = []
        self._in_annotation = 0

    # -- helpers ------------------------------------------------------------
    def _allowed(self, node: ast.AST) -> bool:
        return getattr(node, "lineno", 0) in self.allow_lines

    def _src(self, node: ast.AST) -> str:
        i = getattr(node, "lineno", 0) - 1
        return self.lines[i].strip() if 0 <= i < len(self.lines) else ""

    # -- numeric literals ---------------------------------------------------
    def visit_Constant(self, node: ast.Constant) -> None:
        if self._allowed(node):
            return
        if isinstance(node.value, bool):
            return
        if isinstance(node.value, int):
            src = self._src(node)
            # Hex spelling is the strongest signal of an engine constant, so it is
            # judged against HEX_GENERIC rather than the permissive decimal set.
            is_hex = self._spelled_hex(node, src)
            if is_hex:
                if node.value not in HEX_GENERIC:
                    self.findings.append(Finding(
                        self.path, node, "ENGINE_MAGIC",
                        f"十六进制字面量 {hex(node.value)} 出现在结构逻辑中；"
                        f"opcode/子码/调用 ID 应移入 dialect 声明并附 evidence_refs"
                        f"（§7）｜{src[:70]}"))
            elif node.value not in ALLOWED_INTS:
                self.findings.append(Finding(
                    self.path, node, "UNEXPLAINED_INT",
                    f"字面量 {node.value} 出现在结构逻辑中"
                    f"；应移入 dialect 声明并附 evidence_refs（§7）｜{src[:70]}"))
        elif isinstance(node.value, bytes):
            if len(node.value) >= 3 and node.value not in GENERIC_BYTES:
                self.findings.append(Finding(
                    self.path, node, "ENGINE_MAGIC",
                    f"字节串字面量 {node.value!r} 出现在结构逻辑中；容器签名应移入 "
                    f"dialect 的 applies_when/magic 声明（§7）｜{self._src(node)[:70]}"))
        self.generic_visit(node)

    def _spelled_hex(self, node: ast.AST, src: str) -> bool:
        """True when this literal is written in hex in the source.

        Scans only the literal's own column span, so a `0x%08X` format string
        elsewhere on the line does not make an unrelated decimal look hex.
        """
        col = getattr(node, "col_offset", None)
        end = getattr(node, "end_col_offset", None)
        i = getattr(node, "lineno", 0) - 1
        if col is None or end is None or not (0 <= i < len(self.lines)):
            return bool(re.search(r"0[xX][0-9a-fA-F]+", src))
        return bool(re.match(r"0[xX][0-9a-fA-F]+", self.lines[i][col:end]))

    # -- opcode / id containers --------------------------------------------
    def visit_Set(self, node: ast.Set) -> None:
        self._check_container(node, node.elts, "set")
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self._check_container(node, node.elts, "list")
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        keys = [k for k in node.keys if k is not None]
        self._check_container(node, keys, "dict 键")
        self.generic_visit(node)

    def _check_container(self, node: ast.AST, elts: list[ast.expr], kind: str) -> None:
        if self._allowed(node):
            return
        ints = [e.value for e in elts
                if isinstance(e, ast.Constant) and isinstance(e.value, int)
                and not isinstance(e.value, bool)]
        if len(ints) >= 3 and any(v not in ALLOWED_INTS for v in ints):
            preview = ", ".join(hex(v) for v in ints[:4])
            self.findings.append(Finding(
                self.path, node, "ENGINE_ID_TABLE",
                f"{kind} 中有 {len(ints)} 个整数字面量（{preview}…）"
                f"；opcode/调用 ID 集合属于 dialect，不属于代码（§7）"))

    # -- regex literals -----------------------------------------------------
    @staticmethod
    def _is_regex_call(func: ast.expr) -> bool:
        """只认 re 模块的调用，或从 re 导入的同名函数。

        `str.split(":")`、`text.startswith("#")` 这类不是正则；把它们算进来会淹没真正的
        问题。判据：`re.xxx(...)` 形式，或调用名在 REGEX_CALLS 且不是常见字符串方法。
        """
        if isinstance(func, ast.Attribute):
            base = func.value
            if isinstance(base, ast.Name) and base.id == "re":
                return func.attr in REGEX_CALLS | {"split"}
            return False                       # obj.match(...) 之类，无法确定是 re
        if isinstance(func, ast.Name):
            return func.id in REGEX_CALLS
        return False

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_regex_call(node.func):
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if self._allowed(arg):
                        continue
                    pat = arg.value
                    if OWN_FORMAT_HINTS.search(pat):
                        continue               # 解析自有产物格式，不是引擎方言
                    if not LANG_SPECIFIC_PATTERN.search(pat):
                        continue               # 纯语法模式，无语言/引擎特定字面量
                    code = ("TEXT_SHAPE_REGEX" if CLASSIFY_HINTS.search(pat)
                            else "INLINE_REGEX")
                    self.findings.append(Finding(
                        self.path, arg, code,
                        f"内联正则 {pat[:48]!r}"
                        + ("（含字符形态判断，属于 text_rules）" if code == "TEXT_SHAPE_REGEX"
                           else "（应移入 dialect 以便审阅与统计）") + "（§7）"))
        self.generic_visit(node)


def scan(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        f = Finding(path, ast.Module(), "SYNTAX_ERROR", f"无法解析：{exc}")
        f.line = exc.lineno or 0
        return [f]

    allow_lines = {
        i for i, line in enumerate(source.splitlines(), 1)
        if "dialect-literal-ok" in line
    }
    v = Visitor(path, source, allow_lines)
    v.visit(tree)
    return v.findings


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", type=Path, nargs="+",
                    help="结构逻辑模块或目录（不要传 opcodelist.py）")
    ap.add_argument("--exclude", action="append", default=[],
                    help="跳过匹配该子串的路径，可重复；方言文件应在此列")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)

    # The dialect module is where literals belong; never flag it.
    excludes = list(args.exclude) + ["opcodelist", "dialect", "test_"]

    files: list[Path] = []
    for t in args.targets:
        files.extend(sorted(t.rglob("*.py")) if t.is_dir() else [t])
    files = [f for f in files if not any(x in f.as_posix() for x in excludes)]

    findings: list[Finding] = []
    unreadable: list[dict[str, str]] = []
    for f in files:
        try:
            findings.extend(scan(f))
        except OSError as exc:
            unreadable.append({"file": str(f), "error": str(exc)})

    # 「没扫到东西」与「扫过且干净」必须区分：路径写错时若返回 ok，门禁形同虚设。
    if not files:
        _emit({"ok": False, "scanned_files": 0, "violations": 0,
               "errors": [{"code": "NO_INPUT",
                           "detail": "没有匹配到任何 .py 文件；请检查路径与 --exclude"}]},
              args.report)
        return 1
    if unreadable:
        _emit({"ok": False, "scanned_files": len(files) - len(unreadable),
               "violations": 0, "unreadable": unreadable,
               "errors": [{"code": "UNREADABLE_INPUT",
                           "detail": f"{len(unreadable)} 个文件无法读取，结果不可信"}]},
              args.report)
        return 1

    by_code: dict[str, int] = {}
    for f in findings:
        by_code[f.code] = by_code.get(f.code, 0) + 1

    hard = [f for f in findings if f.code in HARD_CODES]
    advisory = [f for f in findings if f.code not in HARD_CODES]

    result = {
        "ok": not hard,
        "scanned_files": len(files),
        "violations": len(hard),
        "advisory": len(advisory),
        "by_code": by_code,
        "findings": [f.as_dict() for f in hard[:200]],
        "advisory_findings": [f.as_dict() for f in advisory[:50]],
        "note": ("violations 会导致门禁失败；advisory 是十进制字面量，需人工判断是否为"
                 "未申报的窗口常量（§1.6）。单行豁免：在该行加注释 dialect-literal-ok"),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    write_stdout(text)
    return 0 if result["ok"] else 1



def _emit(result: dict, report) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2,
                      sort_keys=True) + chr(10)
    if report:
        report.write_text(text, encoding="utf-8")
    write_stdout(text)

def write_stdout(text: str) -> None:
    """Write UTF-8 regardless of the console code page.

    Scanned sources may contain CJK, which a GBK/CP932 console cannot encode.
    Reconfigure rather than dropping characters, so diagnostics stay readable.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", "replace"))


if __name__ == "__main__":
    raise SystemExit(main())
