"""
Parser for AKL terms.

Implements a Pratt parser (operator precedence) for AKL term syntax including:
- Atoms (simple, quoted, operator symbols)
- Numbers (integers with base notation, floats, character codes)
- Variables
- Structures (compound terms)
- Lists
- Operator expressions with precedence (e.g., clauses, arithmetic)

Comments (% line and /* block */) are handled by the lexer.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator, Optional
import re

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL, make_list


# Operator table: name -> (precedence, associativity)
# Associativity: 'xfx' (non-assoc infix), 'xfy' (right-assoc infix),
#                'yfx' (left-assoc infix), 'fx' (prefix), 'fy' (prefix),
#                'xf' (postfix), 'yf' (postfix)
#
# From AKL source:
#   :- op( 1200, xfx, [ :-, -->, := ]).
#   :- op( 1200,  fx, [ :-, ?- ]).
#   :- op( 1050, xfx, [ '|', ->, ?, ??, ! ]).
#   :- op( 1050,  fx, [ '|', ->, ?, ??, ! ]).
# Full operator table based on AKL current_op.akl
OPERATORS: dict[str, tuple[int, str]] = {
    # Clause operators
    ':-': (1200, 'xfx'),
    '-->': (1200, 'xfx'),
    ':=': (1200, 'xfx'),
    # Declarations
    'public': (1150, 'fx'),
    'class': (1150, 'fx'),
    'supers': (1150, 'fx'),
    # Disjunction
    ';': (1100, 'xfy'),
    # Module qualification
    ':': (1070, 'xfy'),
    # AKL guard operators (all at 1050)
    '->': (1050, 'xfx'),
    '?': (1050, 'xfx'),
    '??': (1050, 'xfx'),
    '|': (1050, 'xfx'),
    '!': (1050, 'xfx'),
    # Parallel conjunction
    '&': (1025, 'xfy'),
    # Conjunction
    ',': (1000, 'xfy'),
    # Accumulator syntax / message passing
    '@': (900, 'xfx'),
    '@@': (900, 'xfx'),
    # Negation as failure
    '\\+': (900, 'fy'),
    'spy': (900, 'fy'),
    'nospy': (900, 'fy'),
    # Comparison
    '=': (700, 'xfx'),
    '\\=': (700, 'xfx'),
    '==': (700, 'xfx'),
    '\\==': (700, 'xfx'),
    '@<': (700, 'xfx'),
    '@>': (700, 'xfx'),
    '@=<': (700, 'xfx'),
    '@>=': (700, 'xfx'),
    '=..': (700, 'xfx'),
    'is': (700, 'xfx'),
    '=:=': (700, 'xfx'),
    '=\\=': (700, 'xfx'),
    '<': (700, 'xfx'),
    '>': (700, 'xfx'),
    '=<': (700, 'xfx'),
    '>=': (700, 'xfx'),
    'in': (700, 'xfx'),
    # Range
    '..': (600, 'xfx'),
    # Arithmetic
    '+': (500, 'yfx'),
    '-': (500, 'yfx'),
    '#': (500, 'yfx'),
    '/\\': (500, 'yfx'),
    '\\/': (500, 'yfx'),
    # Lambda / set abstraction
    '\\': (500, 'xfx'),
    '\\\\': (500, 'xfx'),
    # Multiplication etc
    '*': (400, 'yfx'),
    '/': (400, 'yfx'),
    '//': (400, 'yfx'),
    '<<': (400, 'yfx'),
    '>>': (400, 'yfx'),
    '=>': (400, 'yfx'),
    # Modulo
    'mod': (300, 'xfx'),
    # Power
    '^': (200, 'xfy'),
    # Annotations
    '$': (100, 'yfx'),
}

# Prefix operators (fx, fy)
PREFIX_OPS: dict[str, tuple[int, str]] = {
    # Clause/query
    ':-': (1200, 'fx'),
    '?-': (1200, 'fx'),
    # Declarations
    'public': (1150, 'fx'),
    'class': (1150, 'fx'),
    'supers': (1150, 'fx'),
    # AKL guard operators as prefix
    '|': (1050, 'fx'),
    '->': (1050, 'fx'),
    '?': (1050, 'fx'),
    '??': (1050, 'fx'),
    '!': (1050, 'fx'),
    # Negation
    '\\+': (900, 'fy'),
    'spy': (900, 'fy'),
    'nospy': (900, 'fy'),
    # Unary arithmetic
    '+': (500, 'fx'),
    '-': (500, 'fx'),
    '#': (500, 'fx'),
}


def get_infix_op(name: str) -> Optional[tuple[int, str]]:
    """Get infix operator info if name is an infix operator."""
    if name in OPERATORS:
        prec, assoc = OPERATORS[name]
        if assoc in ('xfx', 'xfy', 'yfx'):
            return (prec, assoc)
    return None


def get_prefix_op(name: str) -> Optional[tuple[int, str]]:
    """Get prefix operator info if name is a prefix operator."""
    if name in PREFIX_OPS:
        return PREFIX_OPS[name]
    return None


class TokenType(Enum):
    """Token types for the lexer."""
    # Literals
    INTEGER = auto()
    FLOAT = auto()
    ATOM = auto()
    QUOTED_ATOM = auto()
    VARIABLE = auto()
    STRING = auto()

    # Punctuation
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]
    LBRACE = auto()      # {
    RBRACE = auto()      # }
    COMMA = auto()       # ,
    PIPE = auto()        # |
    DOT = auto()         # . (end of clause)

    # Operators (as atoms)
    OPERATOR = auto()

    # Special
    EOF = auto()


@dataclass
class Token:
    """A lexical token."""
    type: TokenType
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.col})"


class ParseError(Exception):
    """Error during parsing."""
    def __init__(self, message: str, line: int = 0, col: int = 0):
        self.line = line
        self.col = col
        super().__init__(f"{message} at line {line}, col {col}")


class Lexer:
    """
    Tokenizer for AKL source code.

    Handles:
    - Line comments (% ...)
    - Block comments (/* ... */)
    - All AKL token types
    """

    # Operator characters (can form multi-char operators)
    OPERATOR_CHARS = set('+-*/\\^<>=`~:.?@#$&')

    # Single-char tokens that are always separate
    PUNCTUATION = {
        '(': TokenType.LPAREN,
        ')': TokenType.RPAREN,
        '[': TokenType.LBRACKET,
        ']': TokenType.RBRACKET,
        '{': TokenType.LBRACE,
        '}': TokenType.RBRACE,
        ',': TokenType.COMMA,
        '|': TokenType.PIPE,
    }

    # Special atoms
    SPECIAL_ATOMS = {'!', ';'}

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.length = len(source)

    def peek(self, offset: int = 0) -> str:
        """Look at character at current position + offset."""
        pos = self.pos + offset
        if pos >= self.length:
            return ''
        return self.source[pos]

    def advance(self) -> str:
        """Consume and return current character."""
        if self.pos >= self.length:
            return ''
        ch = self.source[self.pos]
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def skip_whitespace_and_comments(self) -> None:
        """Skip whitespace and comments."""
        while self.pos < self.length:
            ch = self.peek()

            # Whitespace
            if ch.isspace():
                self.advance()
                continue

            # Line comment
            if ch == '%':
                while self.pos < self.length and self.peek() != '\n':
                    self.advance()
                continue

            # Block comment
            if ch == '/' and self.peek(1) == '*':
                self.advance()  # /
                self.advance()  # *
                while self.pos < self.length:
                    if self.peek() == '*' and self.peek(1) == '/':
                        self.advance()  # *
                        self.advance()  # /
                        break
                    self.advance()
                continue

            break

    def read_number(self) -> Token:
        """Read an integer or float (always positive, minus is an operator)."""
        start_line, start_col = self.line, self.col

        # Read initial digits
        digits = ''
        while self.peek().isdigit():
            digits += self.advance()

        # Check for base notation: N'digits or character code: 0'char
        if self.peek() == "'" and digits:
            base = int(digits)
            self.advance()  # consume '

            if base == 0:
                # Character code: 0'A
                ch = self.advance()
                value = ord(ch)
                return Token(TokenType.INTEGER, str(value), start_line, start_col)
            elif 2 <= base <= 36:
                # Base N integer
                base_digits = ''
                while self.pos < self.length:
                    ch = self.peek()
                    if ch.isalnum():
                        base_digits += self.advance()
                    else:
                        break
                try:
                    value = int(base_digits, base)
                    return Token(TokenType.INTEGER, str(value), start_line, start_col)
                except ValueError:
                    raise ParseError(f"Invalid base-{base} number: {base_digits}", start_line, start_col)

        # Check for float
        if self.peek() == '.' and self.peek(1).isdigit():
            digits += self.advance()  # .
            while self.peek().isdigit():
                digits += self.advance()

            # Exponent
            if self.peek() in 'eE':
                digits += self.advance()
                if self.peek() in '+-':
                    digits += self.advance()
                while self.peek().isdigit():
                    digits += self.advance()

            return Token(TokenType.FLOAT, str(float(digits)), start_line, start_col)

        # Plain integer
        if digits:
            return Token(TokenType.INTEGER, str(int(digits)), start_line, start_col)

        raise ParseError("Expected number", start_line, start_col)

    def read_quoted_atom(self) -> Token:
        """Read a quoted atom: 'text'"""
        start_line, start_col = self.line, self.col
        self.advance()  # opening quote

        value = ''
        while self.pos < self.length:
            ch = self.advance()
            if ch == "'":
                # Check for escaped quote ''
                if self.peek() == "'":
                    value += self.advance()
                else:
                    break
            else:
                value += ch

        return Token(TokenType.QUOTED_ATOM, value, start_line, start_col)

    def read_string(self) -> Token:
        """Read a double-quoted string: "text" """
        start_line, start_col = self.line, self.col
        self.advance()  # opening quote

        value = ''
        while self.pos < self.length:
            ch = self.advance()
            if ch == '"':
                break
            elif ch == '\\':
                # Escape sequences
                next_ch = self.advance()
                if next_ch == 'n':
                    value += '\n'
                elif next_ch == 't':
                    value += '\t'
                elif next_ch == '\\':
                    value += '\\'
                elif next_ch == '"':
                    value += '"'
                else:
                    value += next_ch
            else:
                value += ch

        return Token(TokenType.STRING, value, start_line, start_col)

    def read_atom_or_variable(self) -> Token:
        """Read an atom or variable starting with a letter."""
        start_line, start_col = self.line, self.col

        value = ''
        while self.pos < self.length:
            ch = self.peek()
            if ch.isalnum() or ch == '_':
                value += self.advance()
            else:
                break

        # Variable if starts with uppercase or underscore
        if value[0].isupper() or value[0] == '_':
            return Token(TokenType.VARIABLE, value, start_line, start_col)
        else:
            return Token(TokenType.ATOM, value, start_line, start_col)

    def read_operator(self) -> Token:
        """Read an operator sequence."""
        start_line, start_col = self.line, self.col

        value = ''
        while self.pos < self.length:
            ch = self.peek()
            if ch in self.OPERATOR_CHARS:
                value += self.advance()
            else:
                break

        # Special case: . at end of clause (followed by whitespace/EOF/comment)
        if value == '.':
            next_ch = self.peek()
            if not next_ch or next_ch.isspace() or next_ch == '%':
                return Token(TokenType.DOT, '.', start_line, start_col)

        return Token(TokenType.OPERATOR, value, start_line, start_col)

    def next_token(self) -> Token:
        """Get the next token."""
        self.skip_whitespace_and_comments()

        if self.pos >= self.length:
            return Token(TokenType.EOF, '', self.line, self.col)

        start_line, start_col = self.line, self.col
        ch = self.peek()

        # Special: [] as single atom (must check before punctuation)
        if ch == '[' and self.peek(1) == ']':
            self.advance()
            self.advance()
            return Token(TokenType.ATOM, '[]', start_line, start_col)

        # Special: {} as single atom (must check before punctuation)
        if ch == '{' and self.peek(1) == '}':
            self.advance()
            self.advance()
            return Token(TokenType.ATOM, '{}', start_line, start_col)

        # Punctuation
        if ch in self.PUNCTUATION:
            self.advance()
            return Token(self.PUNCTUATION[ch], ch, start_line, start_col)

        # Special atoms: ! ;
        if ch in self.SPECIAL_ATOMS:
            self.advance()
            return Token(TokenType.ATOM, ch, start_line, start_col)

        # Quoted atom
        if ch == "'":
            return self.read_quoted_atom()

        # String
        if ch == '"':
            return self.read_string()

        # Number (NOT negative - minus is always an operator, parser handles unary)
        if ch.isdigit():
            return self.read_number()

        # Atom or variable
        if ch.isalpha() or ch == '_':
            return self.read_atom_or_variable()

        # Operator
        if ch in self.OPERATOR_CHARS:
            return self.read_operator()

        raise ParseError(f"Unexpected character: {ch!r}", start_line, start_col)

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source."""
        tokens = []
        while True:
            token = self.next_token()
            tokens.append(token)
            if token.type == TokenType.EOF:
                break
        return tokens


class Parser:
    """
    Pratt parser for AKL terms with operator precedence.

    Uses precedence climbing to handle operators like :-, ->, ?, ,, etc.
    Higher precedence numbers mean looser binding (Prolog convention).
    """

    def __init__(self, source: str):
        self.lexer = Lexer(source)
        self.current: Optional[Token] = None
        # Track variables by name to ensure same name -> same Var object
        self.var_map: dict[str, Var] = {}
        self.advance()

    def advance(self) -> Token:
        """Move to the next token."""
        prev = self.current
        self.current = self.lexer.next_token()
        return prev

    def expect(self, token_type: TokenType) -> Token:
        """Expect a specific token type."""
        if self.current.type != token_type:
            raise ParseError(
                f"Expected {token_type.name}, got {self.current.type.name}",
                self.current.line, self.current.col
            )
        return self.advance()

    def current_op_name(self) -> Optional[str]:
        """Get current token as operator name, if applicable."""
        if self.current.type == TokenType.OPERATOR:
            return self.current.value
        if self.current.type == TokenType.ATOM:
            # Some atoms are also operators (e.g., 'is', 'mod', '!')
            if self.current.value in OPERATORS:
                return self.current.value
        if self.current.type == TokenType.COMMA:
            return ','
        if self.current.type == TokenType.PIPE:
            # '|' as commit operator (not in list context - that's handled in parse_list)
            return '|'
        return None

    def parse_term(self, max_prec: int = 1200) -> Term:
        """
        Parse a term with operators up to max_prec precedence.

        Uses Pratt parsing / precedence climbing.
        """
        # Parse prefix operator or primary term
        left = self.parse_prefix_or_primary()

        # Parse infix operators
        while True:
            op_name = self.current_op_name()
            if op_name is None:
                break

            op_info = get_infix_op(op_name)
            if op_info is None:
                break

            prec, assoc = op_info

            # Check precedence
            if prec > max_prec:
                break

            # Consume operator
            self.advance()

            # Determine right-hand precedence based on associativity
            if assoc == 'xfy':  # right-associative
                right_prec = prec
            elif assoc == 'yfx':  # left-associative
                right_prec = prec - 1
            else:  # xfx - non-associative
                right_prec = prec - 1

            right = self.parse_term(right_prec)
            left = Struct(Atom(op_name), (left, right))

        return left

    def can_start_term(self) -> bool:
        """Check if current token can start a term/expression."""
        tok = self.current
        # These can definitely start terms
        if tok.type in (TokenType.VARIABLE, TokenType.INTEGER, TokenType.FLOAT,
                        TokenType.ATOM, TokenType.QUOTED_ATOM, TokenType.STRING,
                        TokenType.LBRACKET, TokenType.LPAREN, TokenType.LBRACE):
            return True
        # Operators can start terms if they're prefix ops
        if tok.type == TokenType.OPERATOR:
            return get_prefix_op(tok.value) is not None
        if tok.type == TokenType.PIPE:
            return get_prefix_op('|') is not None
        return False

    def prefix_is_atom(self, op_prec: int) -> bool:
        """
        Check if a prefix operator should be treated as an atom.

        A prefix operator is treated as an atom when what follows can't be
        its argument. This happens when:
        - The next token can't start a term at all (e.g., comma, closing brackets)
        - The next token is an infix op that would "take over" at higher precedence
        """
        # If next token can't start a term, prefix op is just an atom
        if not self.can_start_term():
            return True

        # Check for infix op that would take precedence
        # (the "peepop" logic from read.akl)
        op_name = self.current_op_name()
        if op_name:
            op_info = get_infix_op(op_name)
            if op_info:
                infix_prec, _ = op_info
                # If infix has >= precedence (looser binding), it takes over
                # and our prefix op is just an atom
                if infix_prec >= op_prec:
                    return True
        return False

    def parse_prefix_or_primary(self) -> Term:
        """Parse a prefix operator application or a primary term."""
        token = self.current

        # Get potential prefix operator name
        op_name = None
        if token.type == TokenType.OPERATOR:
            op_name = token.value
        elif token.type == TokenType.PIPE:
            op_name = '|'
        elif token.type == TokenType.ATOM and token.value in PREFIX_OPS:
            op_name = token.value

        # Check for prefix operator
        if op_name is not None:
            op_info = get_prefix_op(op_name)
            if op_info is not None:
                prec, assoc = op_info
                self.advance()

                # Check if this prefix op should be treated as just an atom
                # (e.g., "!, foo" - the ! is cut atom, not prefix application)
                if self.prefix_is_atom(prec):
                    return Atom(op_name)

                # For fy, allow same precedence; for fx, require lower
                arg_prec = prec if assoc == 'fy' else prec - 1
                arg = self.parse_term(arg_prec)
                return Struct(Atom(op_name), (arg,))

        return self.parse_primary()

    def parse_primary(self) -> Term:
        """Parse a primary (non-operator) term."""
        token = self.current

        # Variable (possibly higher-order call: Var(args) -> apply(Var, args))
        if token.type == TokenType.VARIABLE:
            self.advance()
            var_name = token.value
            # Anonymous variables (_) are always unique
            if var_name == "_":
                var = Var("_")
            elif var_name in self.var_map:
                var = self.var_map[var_name]
            else:
                var = Var(var_name)
                self.var_map[var_name] = var
            # Check for higher-order call: X(Args) -> apply(X, [Args])
            if self.current.type == TokenType.LPAREN:
                self.advance()
                if self.current.type == TokenType.RPAREN:
                    # X() -> apply(X, [])
                    self.advance()
                    return Struct(Atom('apply'), (var, NIL))
                args = self.parse_arg_list()
                self.expect(TokenType.RPAREN)
                return Struct(Atom('apply'), (var, make_list(args)))
            return var

        # Integer
        if token.type == TokenType.INTEGER:
            self.advance()
            return Integer(int(token.value))

        # Float
        if token.type == TokenType.FLOAT:
            self.advance()
            return Float(float(token.value))

        # Atom or structure
        if token.type in (TokenType.ATOM, TokenType.QUOTED_ATOM, TokenType.OPERATOR):
            return self.parse_atom_or_struct()

        # List
        if token.type == TokenType.LBRACKET:
            return self.parse_list()

        # Parenthesized term (resets precedence)
        if token.type == TokenType.LPAREN:
            self.advance()
            term = self.parse_term(1200)  # Reset to max precedence inside parens
            self.expect(TokenType.RPAREN)
            return term

        # Curly braces: {X} -> {}(X)
        if token.type == TokenType.LBRACE:
            self.advance()
            inner = self.parse_term(1200)
            self.expect(TokenType.RBRACE)
            return Struct(Atom('{}'), (inner,))

        # String -> list of character codes
        if token.type == TokenType.STRING:
            self.advance()
            char_codes = [Integer(ord(c)) for c in token.value]
            return make_list(char_codes)

        raise ParseError(
            f"Unexpected token: {token.type.name}",
            token.line, token.col
        )

    def parse_atom_or_struct(self) -> Term:
        """Parse an atom or structure (atom with arguments)."""
        token = self.current
        self.advance()

        atom_name = token.value
        atom = Atom(atom_name)

        # Check for arguments (must immediately follow atom, no space check needed
        # since lexer handles that)
        if self.current.type == TokenType.LPAREN:
            self.advance()
            # Empty args: foo()
            if self.current.type == TokenType.RPAREN:
                self.advance()
                return Struct(atom, ())
            args = self.parse_arg_list()
            self.expect(TokenType.RPAREN)
            return Struct(atom, tuple(args))

        return atom

    def parse_arg_list(self) -> list[Term]:
        """Parse comma-separated arguments inside parentheses."""
        # Inside parens, comma is argument separator, not operator
        # So we parse at precedence 999 (just below comma's 1000)
        args = [self.parse_term(999)]

        while self.current.type == TokenType.COMMA:
            self.advance()
            args.append(self.parse_term(999))

        return args

    def parse_list(self) -> Term:
        """Parse a list: [], [a,b,c], [H|T], [a,b|T]."""
        self.expect(TokenType.LBRACKET)

        # Empty list
        if self.current.type == TokenType.RBRACKET:
            self.advance()
            return NIL

        # Non-empty list - parse at precedence 999 (below comma)
        elements = [self.parse_term(999)]

        while self.current.type == TokenType.COMMA:
            self.advance()
            elements.append(self.parse_term(999))

        # Check for tail
        tail: Term = NIL
        if self.current.type == TokenType.PIPE:
            self.advance()
            tail = self.parse_term(999)

        self.expect(TokenType.RBRACKET)
        return make_list(elements, tail)


def parse_term(source: str) -> Term:
    """
    Parse a string into a Term.

    Args:
        source: AKL term syntax

    Returns:
        The parsed Term

    Raises:
        ParseError: If parsing fails
    """
    parser = Parser(source)
    term = parser.parse_term()

    # Check that we consumed all input
    if parser.current.type != TokenType.EOF:
        raise ParseError(
            f"Unexpected token after term: {parser.current.type.name}",
            parser.current.line, parser.current.col
        )

    return term


def parse_clause(source: str) -> Term:
    """
    Parse a single clause (term followed by dot).

    Args:
        source: AKL clause syntax (e.g., "foo(X) :- bar(X).")

    Returns:
        The parsed Term

    Raises:
        ParseError: If parsing fails
    """
    parser = Parser(source)
    term = parser.parse_term()

    # Expect dot at end of clause
    if parser.current.type == TokenType.DOT:
        parser.advance()

    # Check that we consumed all input
    if parser.current.type != TokenType.EOF:
        raise ParseError(
            f"Unexpected token after clause: {parser.current.type.name}",
            parser.current.line, parser.current.col
        )

    return term


def parse_clauses(source: str) -> list[Term]:
    """
    Parse multiple clauses from AKL source.

    Each clause is a term followed by a dot.

    Args:
        source: AKL source with multiple clauses

    Returns:
        List of parsed Terms (one per clause)
    """
    parser = Parser(source)
    clauses = []

    while parser.current.type != TokenType.EOF:
        clause = parser.parse_term()
        clauses.append(clause)

        # Expect and consume dot
        if parser.current.type == TokenType.DOT:
            parser.advance()
        elif parser.current.type != TokenType.EOF:
            raise ParseError(
                f"Expected DOT or EOF, got {parser.current.type.name}",
                parser.current.line, parser.current.col
            )

    return clauses
