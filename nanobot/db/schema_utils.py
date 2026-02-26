"""
Module Purpose: Safe SQL schema parsing for PostgreSQL initialization.

Responsibilities:
    - Split complex SQL schema files into individual executable statements
    - Preserve quoted strings and dollar-quoted function bodies (PostgreSQL-specific)
    - Respect line comments (--) and block comments (/* */)
    - Avoid splitting on semicolons inside quoted sections

Dependencies:
    - None (standard library only)

Why this module exists:
    Simple SQL splitting on semicolons fails on PostgreSQL function/procedure bodies,
    which use dollar-quoted strings ($$...$$) and contain semicolons internally.
    Without proper parsing, schema initialization would corrupt function definitions.
"""

from __future__ import annotations


# ---------- Public API ----------


def split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL into top-level statements while respecting quoted sections.

    This function implements a state machine to track context:
    - Are we inside a single-quoted string? ('...')
    - Are we inside a double-quoted string? ("...")
    - Are we inside a dollar-quoted PostgreSQL string? ($$...$$)
    - Are we inside a line comment? (--...)
    - Are we inside a block comment? (/*...*/)

    The function only splits on semicolons when we're NOT in any quoted/comment context,
    preventing corruption of function bodies or string literals.

    Args:
        sql: str - The complete SQL schema file content

    Returns:
        list[str] - Individual SQL statements ready for execution

    Complexity:
        This is a character-by-character parser because PostgreSQL's dollar-quoting
        creates contexts that regex or simple string splitting cannot handle correctly.
    """

    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)

    # ---------- Context Tracking Flags ----------
    # These flags track which "mode" the parser is in
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        # ---------- Line Comment Handling ----------
        # If inside a line comment (starts with --), consume until newline
        if in_line_comment:
            current.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        # ---------- Block Comment Handling ----------
        # If inside a block comment (/* ... */), consume until closing */
        if in_block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                i += 2
                in_block_comment = False
                continue
            i += 1
            continue

        # ---------- Line Comment Start Detection ----------
        # Line comments start with "--" (outside any quotes)
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

        # ---------- Single Quote Handling ----------
        # Toggle single-quote mode when encountering '
        if not in_double and dollar_tag is None and ch == "'":
            in_single = not in_single
            current.append(ch)
            i += 1
            continue

        # ---------- Double Quote Handling ----------
        # Toggle double-quote mode when encountering "
        if not in_single and dollar_tag is None and ch == '"':
            in_double = not in_double
            current.append(ch)
            i += 1
            continue

        # ---------- PostgreSQL Dollar-Quote Handling ----------
        # PostgreSQL uses $$...$$ for function bodies containing quotes
        # Example: $$function body with 'quotes';$$
        if not in_single and not in_double:
            if dollar_tag is None and ch == "$":
                # Consume entire tag: start $, then alphanumeric/underscore chars, end $
                j = i + 1
                while j < n and (sql[j].isalnum() or sql[j] == "_"):
                    j += 1
                if j < n and sql[j] == "$":
                    # Tag complete: capture it and set active
                    tag = sql[i : j + 1]
                    dollar_tag = tag
                    current.append(tag)
                    i = j + 1
                    continue
            elif dollar_tag is not None and sql.startswith(dollar_tag, i):
                # End of dollar-quoted section found: consume closing tag
                current.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue

        # ---------- Statement Boundary Detection ----------
        # Semicolons only split statements when NOT in any quoted/comment context
        if ch == ";" and not in_single and not in_double and dollar_tag is None:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            i += 1
            continue

        # ---------- Default: Accumulate Character ----------
        # No special handling needed, just track this character
        current.append(ch)
        i += 1

    # ---------- Handle Tail ----------
    # After loop, any remaining characters form the final statement
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements
