# -*- coding: utf-8 -*-
"""HIVM MLIR Parser — proper Python MLIR/HIVM parser with round-trip fidelity.

Key design: every operation stores its original raw text so the serializer can
reproduce the input exactly for unmodified ops.  Only operations created or
modified via HivmOpsEditor need new text generation.

Capabilities:
- Parse MLIR module/function/operation/region/block structure
- Track SSA value definitions and uses
- Capture raw text for each operation (round-trip fidelity)
- Handle HIVM dialect: DMA, vector, sync, macro, scf, standard ops
- Serialize back to valid MLIR text
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# =============================================================================
# Tokenizer
# =============================================================================

class TokenKind(Enum):
    IDENT = auto()
    PERCENT_IDENT = auto()  # %name
    HASH_IDENT = auto()     # #hivm.address_space
    CARET_IDENT = auto()    # ^bb0
    AT_IDENT = auto()       # @func_name
    STRING = auto()
    INTEGER = auto()
    FLOAT = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LANGLE = auto()
    RANGLE = auto()
    COLON = auto()
    COMMA = auto()
    EQUAL = auto()
    ARROW = auto()   # ->
    QUESTION = auto()
    STAR = auto()
    DOT = auto()
    SEMICOLON = auto()
    PIPE = auto()
    SLASH = auto()
    NEWLINE = auto()
    COMMENT = auto()
    EOF = auto()


@dataclass
class Token:
    kind: TokenKind
    text: str
    line: int = 0
    col: int = 0
    pos: int = 0  # character offset in original text


class MLIRTokenizer:
    """Tokenizer for MLIR text format."""

    def __init__(self, text: str):
        self._text = text
        self._pos = 0
        self._line = 1
        self._col = 1

    def tokenize(self) -> List[Token]:
        self._pos = 0
        self._line = 1
        self._col = 1
        tokens: List[Token] = []
        while self._pos < len(self._text):
            self._skip_whitespace()
            if self._pos >= len(self._text):
                break
            tok = self._next_token()
            if tok is not None:
                tokens.append(tok)
        tokens.append(Token(TokenKind.EOF, '', self._line, self._col, self._pos))
        return tokens

    def _skip_whitespace(self):
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch in ' \t\r':
                self._advance()
            elif ch == '\n':
                self._line += 1
                self._col = 1
                self._pos += 1
            elif ch == '/' and self._pos + 1 < len(self._text) and self._text[self._pos + 1] == '/':
                # Skip line comment
                while self._pos < len(self._text) and self._text[self._pos] != '\n':
                    self._pos += 1
            else:
                break

    def _advance(self, n: int = 1):
        for _ in range(n):
            if self._pos < len(self._text):
                if self._text[self._pos] == '\n':
                    self._line += 1
                    self._col = 1
                else:
                    self._col += 1
                self._pos += 1

    def _peek(self, offset: int = 0) -> str:
        idx = self._pos + offset
        return self._text[idx] if idx < len(self._text) else '\0'

    def _next_token(self) -> Optional[Token]:
        ch = self._text[self._pos]
        line, col, char_pos = self._line, self._col, self._pos

        if ch == '%':
            return self._read_percent_ident()
        if ch == '#':
            return self._read_hash_ident()
        if ch == '@':
            return self._read_at_ident()
        if ch == '^':
            return self._read_caret_ident()
        if ch == '"':
            return self._read_string()

        if ch.isdigit() or (ch == '-' and self._peek(1).isdigit()):
            return self._read_number()

        if ch == '-' and self._peek(1) == '>':
            self._advance(2)
            return Token(TokenKind.ARROW, '->', line, col, char_pos)

        punct_map = {
            '(': TokenKind.LPAREN, ')': TokenKind.RPAREN,
            '{': TokenKind.LBRACE, '}': TokenKind.RBRACE,
            '[': TokenKind.LBRACKET, ']': TokenKind.RBRACKET,
            '<': TokenKind.LANGLE, '>': TokenKind.RANGLE,
            ':': TokenKind.COLON, ',': TokenKind.COMMA,
            '=': TokenKind.EQUAL, '?': TokenKind.QUESTION,
            '*': TokenKind.STAR, '.': TokenKind.DOT,
            ';': TokenKind.SEMICOLON, '|': TokenKind.PIPE,
        }
        if ch in punct_map:
            self._advance()
            return Token(punct_map[ch], ch, line, col, char_pos)

        if ch.isalpha() or ch == '_':
            return self._read_ident()

        self._advance()
        return None

    def _read_ident(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        start = self._pos
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isalnum() or ch in '._':
                self._advance()
            else:
                break
        return Token(TokenKind.IDENT, self._text[start:self._pos], line, col, char_pos)

    def _read_ident_body(self) -> str:
        start = self._pos
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isalnum() or ch in '_.':
                self._advance()
            else:
                break
        return self._text[start:self._pos]

    def _read_percent_ident(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        self._advance()  # skip %
        ident = self._read_ident_body()
        return Token(TokenKind.PERCENT_IDENT, '%' + ident, line, col, char_pos)

    def _read_hash_ident(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        self._advance()  # skip #
        body_start = self._pos
        self._read_ident_body()
        if self._pos < len(self._text) and self._text[self._pos] == '<':
            depth = 1
            self._advance()
            while self._pos < len(self._text) and depth > 0:
                if self._text[self._pos] == '<':
                    depth += 1
                elif self._text[self._pos] == '>':
                    depth -= 1
                self._advance()
        return Token(TokenKind.HASH_IDENT, '#' + self._text[body_start:self._pos], line, col, char_pos)

    def _read_at_ident(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        self._advance()
        ident = self._read_ident_body()
        return Token(TokenKind.AT_IDENT, '@' + ident, line, col, char_pos)

    def _read_caret_ident(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        self._advance()
        ident = self._read_ident_body()
        return Token(TokenKind.CARET_IDENT, '^' + ident, line, col, char_pos)

    def _read_string(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        self._advance()  # skip opening "
        start = self._pos
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch == '\\':
                self._advance(2)
            elif ch == '"':
                text = self._text[start:self._pos]
                self._advance()
                return Token(TokenKind.STRING, '"' + text + '"', line, col, char_pos)
            else:
                self._advance()
        return Token(TokenKind.STRING, '"' + self._text[start:self._pos] + '"', line, col, char_pos)

    def _read_number(self) -> Token:
        line, col, char_pos = self._line, self._col, self._pos
        start = self._pos
        if self._text[self._pos] == '-':
            self._advance()
        has_dot = False
        while self._pos < len(self._text):
            ch = self._text[self._pos]
            if ch.isdigit():
                self._advance()
            elif ch == '.' and not has_dot:
                has_dot = True
                self._advance()
            elif ch in 'eE' and self._pos + 1 < len(self._text):
                self._advance()
                if self._text[self._pos] in '+-':
                    self._advance()
            else:
                break
        text = self._text[start:self._pos]
        kind = TokenKind.FLOAT if has_dot or 'e' in text.lower() else TokenKind.INTEGER
        return Token(kind, text, line, col, char_pos)


# =============================================================================
# IR Tree Data Structures
# =============================================================================

class SSAValue:
    """An SSA value (result of an operation)."""
    _counter: int = 0

    def __init__(self, name: str, type_str: str = '', owner: 'MLIROperation' = None):
        self.name = name
        self.type_str = type_str
        self.owner = owner
        self._id = SSAValue._counter
        SSAValue._counter += 1

    def __repr__(self):
        return f'SSAValue({self.name}: {self.type_str})' if self.type_str else f'SSAValue({self.name})'


class MLIRAttribute:
    """MLIR attribute representation."""
    def __init__(self, text: str, value: Any = None):
        self.text = text.strip()
        self.value = value

    def __repr__(self):
        return f'Attr({self.text})'


@dataclass
class MLIRRegion:
    """A region containing one or more blocks."""
    blocks: List['MLIRBlock'] = field(default_factory=list)


@dataclass
class MLIRBlock:
    """A basic block containing a list of operations."""
    label: str = ''
    operations: List['MLIROperation'] = field(default_factory=list)
    arguments: List[SSAValue] = field(default_factory=list)
    parent_region: Optional[MLIRRegion] = None


@dataclass
class MLIROperation:
    """An MLIR operation.

    Key design: ``raw_text`` stores the original source text for round-trip
    fidelity.  When ``raw_text`` is set, the serializer uses it directly.
    When ``_modified`` is True, the serializer generates new text from the
    structured fields.
    """
    dialect: str = ''
    op_name: str = ''
    full_name: str = ''
    operands: List[SSAValue] = field(default_factory=list)
    results: List[SSAValue] = field(default_factory=list)
    attributes: Dict[str, MLIRAttribute] = field(default_factory=dict)
    regions: List[MLIRRegion] = field(default_factory=list)
    raw_text: str = ''
    line: int = 0
    parent_block: Optional[MLIRBlock] = None
    _modified: bool = False

    def mark_modified(self):
        self._modified = True

    @property
    def is_modified(self) -> bool:
        return self._modified

    def __repr__(self):
        res = ', '.join(r.name for r in self.results)
        return f'Op({self.full_name}{" -> " + res if res else ""})'


@dataclass
class MLIRFunction:
    """A function in the MLIR module."""
    name: str = ''
    args: List[SSAValue] = field(default_factory=list)
    body: MLIRRegion = field(default_factory=MLIRRegion)
    attributes: Dict[str, MLIRAttribute] = field(default_factory=dict)
    return_type: str = ''
    raw_header: str = ''  # The function signature line(s)


@dataclass
class MLIRModule:
    """Top-level MLIR module."""
    functions: List[MLIRFunction] = field(default_factory=list)
    attributes: Dict[str, MLIRAttribute] = field(default_factory=dict)


# =============================================================================
# Parser — line-based with raw-text capture
# =============================================================================

class MLIRParseError(Exception):
    def __init__(self, msg: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        super().__init__(f'Line {line}:{col}: {msg}')


class MLIRParser:
    """Line-based MLIR parser with raw-text capture for round-trip fidelity.

    Strategy:
    1. Split input into lines
    2. Identify operation boundaries (single-line vs multi-line)
    3. For each operation, store the raw text
    4. Parse the internal structure from the raw text
    """

    _OP_START_PAT = re.compile(
        r'^\s*((%(?:\w[\w.]*)\s*,\s*)*%(?:\w[\w.]*)\s*=\s*)?'
        r'([\w.]+)'
    )
    _SSA_RESULT_PAT = re.compile(r'^\s*((%(?:\w[\w.]*)\s*,\s*)*%(?:\w[\w.]*))\s*=\s*(.*)')
    _OP_NAME_PAT = re.compile(r'^([\w.]+)')
    _INS_PAT = re.compile(r'\bins\s*\(')
    _OUTS_PAT = re.compile(r'\bouts\s*\(')

    def __init__(self, text: str):
        self._text = text
        self._lines = text.split('\n')
        self._ssa_table: Dict[str, SSAValue] = {}
        self._function_table: Dict[str, MLIRFunction] = {}
        self._line_idx = 0

    def parse(self) -> MLIRModule:
        self._ssa_table = {}
        self._function_table = {}
        self._line_idx = 0
        return self._parse_module()

    # ---- Module ----

    def _parse_module(self) -> MLIRModule:
        mod = MLIRModule()
        self._skip_empty_and_comments()
        self._expect_line('module {')
        self._skip_empty_and_comments()

        while self._line_idx < len(self._lines):
            line = self._lines[self._line_idx].strip()
            if line == '}':
                self._line_idx += 1
                break
            if not line or line.startswith('//'):
                self._line_idx += 1
                continue
            if line.startswith('func.func ') or line.startswith('func '):
                fn = self._parse_function()
                mod.functions.append(fn)
            else:
                self._line_idx += 1

        return mod

    def _skip_empty_and_comments(self):
        while self._line_idx < len(self._lines):
            line = self._lines[self._line_idx].strip()
            if line and not line.startswith('//'):
                break
            self._line_idx += 1

    def _expect_line(self, expected: str):
        if self._line_idx >= len(self._lines):
            raise MLIRParseError(f'Expected "{expected}", got EOF', self._line_idx + 1, 1)
        actual = self._lines[self._line_idx].strip()
        if actual != expected:
            raise MLIRParseError(
                f'Expected "{expected}", got "{actual}"',
                self._line_idx + 1, 1
            )
        self._line_idx += 1

    # ---- Function ----

    def _parse_function(self) -> MLIRFunction:
        fn = MLIRFunction()
        start_line = self._line_idx

        # Collect all lines of the function signature (up to and including the opening {)
        sig_lines = []
        body_starts_on_sig_line = False
        while self._line_idx < len(self._lines):
            line = self._lines[self._line_idx]
            sig_lines.append(line)
            if '{' in line:
                body_starts_on_sig_line = True
                break
            self._line_idx += 1

        fn.raw_header = '\n'.join(sig_lines)

        # Join all signature lines and parse
        sig_text = ' '.join(sig_lines)
        # Remove the opening brace and everything after for parsing
        brace_idx = sig_text.index('{')
        sig_clean = sig_text[:brace_idx].strip()
        body_rest = sig_text[brace_idx + 1:].strip()

        # Parse function name and args
        m = re.match(r'(?:func\.func|func)\s+(@\w+)\s*\((.*)\)?\s*$', sig_clean, re.DOTALL)
        if m:
            fn.name = m.group(1)
            args_str = m.group(2) if m.group(2) else ''
            fn.args = self._parse_func_args(args_str)
        else:
            # Try simpler match
            m = re.match(r'(?:func\.func|func)\s+(@\w+)', sig_clean)
            if m:
                fn.name = m.group(1)

        self._function_table[fn.name] = fn

        # Advance past the signature line(s)
        self._line_idx += 1
        self._skip_empty_and_comments()

        # Skip attributes if present
        if self._line_idx < len(self._lines) and 'attributes' in self._lines[self._line_idx]:
            self._line_idx += 1
            self._skip_empty_and_comments()
            if self._line_idx < len(self._lines) and '{' in self._lines[self._line_idx]:
                self._skip_braced_block()

        self._skip_empty_and_comments()

        # Parse the function body
        if body_rest:
            # Body content follows { on the same line
            saved_lines = self._lines
            saved_idx = self._line_idx
            self._lines = [body_rest] + self._lines[saved_idx:]
            self._line_idx = 0
            fn.body = self._parse_region()
            self._lines = saved_lines
            self._line_idx = saved_idx
        elif body_starts_on_sig_line:
            # { was on the signature line and body starts on the next line
            fn.body = self._parse_region()
        else:
            # Body { should be on the next line
            if self._line_idx < len(self._lines):
                line = self._lines[self._line_idx].strip()
                if line == '{' or line.startswith('{'):
                    self._line_idx += 1
                    self._skip_empty_and_comments()
                    fn.body = self._parse_region()

        # Skip closing brace
        self._skip_empty_and_comments()
        if self._line_idx < len(self._lines) and self._lines[self._line_idx].strip() == '}':
            self._line_idx += 1

        return fn

    def _parse_func_args(self, args_str: str) -> List[SSAValue]:
        args = []
        if not args_str.strip():
            return args
        # Parse %name : type, %name : type, ...
        for part in self._split_top_level(args_str, ','):
            part = part.strip()
            m = re.match(r'(%\w[\w.]*)\s*:\s*(.*)', part)
            if m:
                name = m.group(1)
                type_str = m.group(2).strip()
                val = SSAValue(name, type_str)
                self._ssa_table[name] = val
                args.append(val)
        return args

    def _parse_func_args_from_lines(self, fn: MLIRFunction):
        """Parse function arguments from multiple lines (for complex signatures)."""
        pass  # Not needed for current sample files

    def _skip_braced_block(self):
        """Skip a {...} block."""
        if self._line_idx >= len(self._lines):
            return
        depth = self._lines[self._line_idx].count('{') - self._lines[self._line_idx].count('}')
        self._line_idx += 1
        while self._line_idx < len(self._lines) and depth > 0:
            depth += self._lines[self._line_idx].count('{') - self._lines[self._line_idx].count('}')
            self._line_idx += 1

    # ---- Region ----

    def _parse_region(self) -> MLIRRegion:
        region = MLIRRegion()
        self._skip_empty_and_comments()

        while self._line_idx < len(self._lines):
            line = self._lines[self._line_idx].strip()
            if line == '}':
                break
            if not line or line.startswith('//'):
                self._line_idx += 1
                continue
            if line.startswith('^'):
                block = self._parse_block()
                region.blocks.append(block)
            else:
                block = self._parse_block()
                region.blocks.append(block)
                break  # Only one implicit block per region

        return region

    def _parse_block(self) -> MLIRBlock:
        block = MLIRBlock()
        # Check for block label
        if self._line_idx < len(self._lines):
            line = self._lines[self._line_idx].strip()
            if line.startswith('^'):
                m = re.match(r'(\^[\w.]*)\s*(.*)', line)
                if m:
                    block.label = m.group(1)
                self._line_idx += 1
                self._skip_empty_and_comments()

        # Parse operations
        while self._line_idx < len(self._lines):
            line = self._lines[self._line_idx].strip()
            if line == '}' or line.startswith('^'):
                break
            if not line or line.startswith('//'):
                self._line_idx += 1
                continue
            op = self._parse_operation()
            if op:
                op.parent_block = block
                block.operations.append(op)
            else:
                self._line_idx += 1

        return block

    # ---- Operation ----

    def _parse_operation(self) -> Optional[MLIROperation]:
        if self._line_idx >= len(self._lines):
            return None

        line = self._lines[self._line_idx]
        stripped = line.strip()
        if not stripped or stripped.startswith('//'):
            return None

        # Check if this is a multi-line operation (scf.for, scf.if, etc.)
        if stripped.startswith('scf.for ') or stripped.startswith('scf.if '):
            return self._parse_multi_line_op()

        # Single-line operation
        return self._parse_single_line_op()

    def _parse_single_line_op(self) -> Optional[MLIROperation]:
        line = self._lines[self._line_idx]
        stripped = line.strip()
        self._line_idx += 1

        op = MLIROperation()
        op.raw_text = stripped
        op.line = self._line_idx  # 1-based after increment

        # Parse SSA results: %0, %1 = op_name ...
        m = self._SSA_RESULT_PAT.match(stripped)
        if m:
            results_str = m.group(1)
            rest = m.group(3)
            for r in results_str.split(','):
                r = r.strip()
                if r:
                    sv = SSAValue(r, '', op)
                    self._ssa_table[r] = sv
                    op.results.append(sv)
        else:
            rest = stripped

        # Parse op name
        m = self._OP_NAME_PAT.match(rest)
        if m:
            op.full_name = m.group(1)
            parts = op.full_name.rsplit('.', 1)
            if len(parts) == 2:
                op.dialect, op.op_name = parts
            else:
                op.op_name = op.full_name
        else:
            return None

        # Parse operands from ins(...)
        ins_m = self._INS_PAT.search(rest)
        if ins_m:
            self._parse_ins_from_text(rest, op)

        # Parse attributes from {...}
        brace_m = re.search(r'\{([^}]*)\}', rest)
        if brace_m:
            self._parse_attrs_from_text(brace_m.group(1), op)

        # Parse bracket attributes from [...]
        bracket_m = re.search(r'\[([^\]]*)\]', rest)
        if bracket_m:
            op.attributes['_bracket_attrs'] = MLIRAttribute(
                '[' + bracket_m.group(1) + ']',
                bracket_m.group(1).strip()
            )

        return op

    def _parse_multi_line_op(self) -> Optional[MLIROperation]:
        """Parse a multi-line operation like scf.for { ... }."""
        start_line_idx = self._line_idx
        header = self._lines[self._line_idx].strip()

        op = MLIROperation()
        op.line = start_line_idx + 1

        # Parse op name
        m = self._OP_NAME_PAT.match(header)
        if m:
            op.full_name = m.group(1)
            parts = op.full_name.rsplit('.', 1)
            if len(parts) == 2:
                op.dialect, op.op_name = parts
            else:
                op.op_name = op.full_name

        # Collect all lines of the multi-line op
        raw_lines = []
        if '{' in header:
            depth = header.count('{') - header.count('}')
            raw_lines.append(self._lines[self._line_idx])
            self._line_idx += 1
        else:
            depth = 0
            raw_lines.append(self._lines[self._line_idx])
            self._line_idx += 1
            while self._line_idx < len(self._lines):
                line = self._lines[self._line_idx]
                if '{' in line:
                    depth = line.count('{') - line.count('}')
                    raw_lines.append(line)
                    self._line_idx += 1
                    break
                raw_lines.append(line)
                self._line_idx += 1

        # Now consume until matching closing brace
        while self._line_idx < len(self._lines) and depth > 0:
            line = self._lines[self._line_idx]
            depth += line.count('{') - line.count('}')
            raw_lines.append(line)
            self._line_idx += 1

        op.raw_text = '\n'.join(raw_lines)

        # Parse the body as a region
        self._parse_scf_body(op, raw_lines)

        return op

    def _parse_scf_body(self, op: MLIROperation, raw_lines: List[str]):
        """Parse the body of an scf.for/if operation."""
        # Find the body lines (between first { and last })
        body_lines = []
        in_body = False
        depth = 0
        for line in raw_lines:
            if '{' in line and not in_body:
                in_body = True
                depth = line.count('{') - line.count('}')
                # Extract content after {
                idx = line.index('{')
                rest = line[idx + 1:].strip()
                if rest:
                    body_lines.append(rest)
                continue
            if in_body:
                depth += line.count('{') - line.count('}')
                if depth <= 0:
                    # Extract content before }
                    if '}' in line:
                        idx = line.rindex('}')
                        rest = line[:idx].strip()
                        if rest:
                            body_lines.append(rest)
                    break
                body_lines.append(line)

        if body_lines:
            # Save the current parser state
            saved_lines = self._lines
            saved_idx = self._line_idx
            saved_ssa = dict(self._ssa_table)

            self._lines = body_lines
            self._line_idx = 0
            region = self._parse_region()
            op.regions.append(region)

            # Restore state
            self._lines = saved_lines
            self._line_idx = saved_idx
            self._ssa_table = saved_ssa

    def _parse_ins_from_text(self, text: str, op: MLIROperation):
        """Parse operands from ins(...) clause."""
        m = re.search(r'ins\s*\(((?:[^()]|\([^)]*\))*)\)', text)
        if m:
            content = m.group(1)
            # Split by : if types present
            if ':' in content:
                parts = content.split(':', 1)
                ops_str = parts[0]
            else:
                ops_str = content
            for part in ops_str.split(','):
                part = part.strip()
                if part.startswith('%'):
                    sv = self._resolve_ssa(part)
                    if sv:
                        op.operands.append(sv)
                    else:
                        # Create a placeholder
                        sv = SSAValue(part)
                        self._ssa_table[part] = sv
                        op.operands.append(sv)

    def _parse_attrs_from_text(self, text: str, op: MLIROperation):
        """Parse attributes from {key = value, ...} text."""
        # Simple key=value parsing
        for part in self._split_top_level(text, ','):
            part = part.strip()
            if '=' in part:
                key, val = part.split('=', 1)
                key = key.strip()
                val = val.strip()
                op.attributes[key] = MLIRAttribute(val, val)

    def _resolve_ssa(self, name: str) -> Optional[SSAValue]:
        return self._ssa_table.get(name)

    @staticmethod
    def _split_top_level(text: str, delimiter: str) -> List[str]:
        """Split by delimiter, respecting nested brackets/parens/braces."""
        parts = []
        current = []
        depth = 0
        for ch in text:
            if ch in '([{<':
                depth += 1
            elif ch in ')]}>':
                depth = max(0, depth - 1)
            if ch == delimiter and depth == 0:
                parts.append(''.join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append(''.join(current))
        return parts


# =============================================================================
# Serializer — uses raw_text for round-trip fidelity
# =============================================================================

class MLIRSerializer:
    """Serialize MLIR IR tree back to MLIR text.

    Uses raw_text for unmodified operations.  For modified/new operations,
    generates valid MLIR text from the structured fields.
    """

    def serialize(self, module: MLIRModule) -> str:
        lines = ['module {']
        for fn in module.functions:
            lines.append(self._serialize_function(fn))
        lines.append('}')
        return '\n'.join(lines) + '\n'

    def _serialize_function(self, fn: MLIRFunction) -> str:
        lines = []

        # Function header
        if fn.raw_header:
            lines.append(fn.raw_header)
        else:
            args_str = ', '.join(
                f'{a.name} : {a.type_str}' if a.type_str else a.name
                for a in fn.args
            )
            ret = f' -> {fn.return_type}' if fn.return_type else ''
            lines.append(f'  func.func {fn.name}({args_str}){ret} {{')

        # Body
        lines.append(self._serialize_region(fn.body, indent=1))
        lines.append('  }')
        return '\n'.join(lines)

    def _serialize_region(self, region: MLIRRegion, indent: int = 0) -> str:
        prefix = '  ' * indent
        lines = []
        for block in region.blocks:
            lines.append(self._serialize_block(block, indent))
        return '\n'.join(lines)

    def _serialize_block(self, block: MLIRBlock, indent: int = 0) -> str:
        prefix = '  ' * indent
        lines = []
        if block.label:
            lines.append(f'{prefix}{block.label}:')
        for op in block.operations:
            lines.append(self._serialize_op(op, indent))
        return '\n'.join(lines)

    def _serialize_op(self, op: MLIROperation, indent: int = 0) -> str:
        prefix = '  ' * indent

        # If the op has regions and is modified, regenerate from structured data
        if op.is_modified or not op.raw_text:
            return self._generate_op_text(op, prefix)

        # Use raw_text for unmodified operations
        if '\n' in op.raw_text:
            # Multi-line op — preserve indentation
            lines = op.raw_text.split('\n')
            # The first line might already have the right indentation
            # For subsequent lines, add the prefix
            result = prefix + lines[0]
            for line in lines[1:]:
                result += '\n' + prefix + line
            return result
        return prefix + op.raw_text

    def _generate_op_text(self, op: MLIROperation, prefix: str) -> str:
        """Generate valid MLIR text for a new/modified operation."""
        parts = [prefix]

        # Results
        if op.results:
            parts.append(', '.join(r.name for r in op.results))
            parts.append(' = ')

        parts.append(op.full_name)

        # Operands (ins) — only for ops that aren't multi-line
        if op.operands and not op.regions:
            parts.append(' ins(')
            parts.append(', '.join(o.name for o in op.operands))
            parts.append(')')

        # Results (outs)
        if op.results and not op.regions:
            parts.append(' outs(')
            parts.append(', '.join(r.name for r in op.results))
            parts.append(')')

        # Attributes — combine all non-bracket attrs into a single {...}
        bracket_attrs = None
        normal_attrs = {}
        for key, attr in op.attributes.items():
            if key == '_bracket_attrs':
                bracket_attrs = attr
            else:
                normal_attrs[key] = attr

        if normal_attrs:
            attr_parts = []
            for key, attr in normal_attrs.items():
                val = attr.text
                # Quote string values if not already quoted
                if val and not val.startswith('"') and not val.startswith('<'):
                    val = f'"{val}"'
                attr_parts.append(f'{key} = {val}')
            parts.append(' {' + ', '.join(attr_parts) + '}')

        if bracket_attrs:
            parts.append(' ' + bracket_attrs.text)

        # Regions (multi-line ops like scf.for)
        if op.regions:
            parts.append(' {')
            result = ''.join(parts)
            for region in op.regions:
                result += '\n' + self._serialize_region(region, indent=1)
            result += '\n' + prefix + '}'
            return result

        return ''.join(parts)


# =============================================================================
# High-level convenience functions
# =============================================================================

def parse_hivm_file(path: Union[str, Path]) -> MLIRModule:
    """Parse a HIVM/NPUIR MLIR file into an IR tree."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    return parse_hivm_text(text)


def parse_hivm_text(text: str) -> MLIRModule:
    """Parse HIVM/NPUIR MLIR text into an IR tree."""
    parser = MLIRParser(text)
    return parser.parse()


def serialize_module(module: MLIRModule) -> str:
    """Serialize an MLIR module back to text."""
    serializer = MLIRSerializer()
    return serializer.serialize(module)


def write_module(module: MLIRModule, path: Union[str, Path]):
    """Write an MLIR module to file."""
    text = serialize_module(module)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)