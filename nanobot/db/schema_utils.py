"""Utilities for safely parsing SQL schema files into executable statements."""

from __future__ import annotations


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into top-level statements while respecting quoted sections.

    This handles:
    - single and double quoted strings
    - dollar-quoted PostgreSQL bodies (for functions/procedures)
    - line and block comments
    """

    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        if not in_single and not in_double and dollar_tag is None:
            if ch == "-" and nxt == "-":
                current.append(ch)
                current.append(nxt)
                i += 2
                in_line_comment = True
                continue
            if ch == "/" and nxt == "*":
                current.append(ch)
                current.append(nxt)
                i += 2
                in_block_comment = True
                continue

        if not in_double and dollar_tag is None and ch == "'":
            in_single = not in_single
            current.append(ch)
            i += 1
            continue

        if not in_single and dollar_tag is None and ch == '"':
            in_double = not in_double
            current.append(ch)
            i += 1
            continue

        if not in_single and not in_double:
            if dollar_tag is None and ch == "$":
                j = i + 1
                while j < n and (sql[j].isalnum() or sql[j] == "_"):
                    j += 1
                if j < n and sql[j] == "$":
                    tag = sql[i : j + 1]
                    dollar_tag = tag
                    current.append(tag)
                    i = j + 1
                    continue
            elif dollar_tag is not None and sql.startswith(dollar_tag, i):
                current.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue

        if ch == ";" and not in_single and not in_double and dollar_tag is None:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements
