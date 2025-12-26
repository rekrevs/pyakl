# Task: T-PARSE-01

**Status:** DONE
**Parent:** B-PARSE-01, B-PRINT-01
**Created:** 2025-12-04

---

## Objective

Implement a parser and printer for AKL terms, with the ability to parse real AKL source files including full clauses with operators.

---

## Acceptance Criteria

- [x] Parse atoms: `foo`, `'hello world'`, `[]`, operators
- [x] Parse numbers: `42`, `3.14`, `2'1111` (base notation), `0'A` (char codes)
- [x] Parse variables: `X`, `_`, `_Foo`
- [x] Parse structures: `foo(X, Y)`, `bar(1, baz(Z))`
- [x] Parse lists: `[]`, `[1,2,3]`, `[H|T]`, `[a,b|Rest]`
- [x] Ignore comments: `% line comment` and `/* block comment */`
- [x] Parse operator expressions with precedence (clauses, arithmetic, guards)
- [x] Handle AKL-specific operators: `:-`, `->`, `?`, `??`, `|`, `!`, `@`, etc.
- [x] Handle higher-order calls: `X(args)` -> `apply(X, [args])`
- [x] Print terms back to valid AKL syntax
- [x] Round-trip: `parse(print(t))` equals `t` structurally
- [x] Successfully parse ALL 45 AKL files in ../akl-agents/demos/ (1465 clauses)

---

## Context

- `docs/architecture.md` - Parser design
- `../akl-agents/doc/user.texi` - AKL syntax specification
- Real AKL files show: `->`, `?`, `??`, `!` guard operators, `:-` for clauses

---

## Implementation

### Files Changed

- `pyakl/parser.py` - Lexer (490 lines) and Parser
- `pyakl/printer.py` - Term printer (110 lines)
- `pyakl/__init__.py` - Export parse_term, print_term, ParseError
- `tests/test_parser.py` - 61 parser tests
- `tests/test_printer.py` - 36 printer tests
- `tests/test_akl_files.py` - 12 tests against real AKL files

### Key Features

**Lexer:**
- Line comments (`% ...`)
- Block comments (`/* ... */`)
- Atoms: simple, quoted, operators
- Numbers: integers, floats, base notation (2'1010), character codes (0'A)
- Variables: uppercase, underscore-prefixed
- Special tokens: `[]`, `{}`, `!`, `;`

**Parser:**
- Recursive descent
- Terms: atoms, variables, numbers, structures, lists
- Parenthesized terms
- Curly brace notation: `{X}` -> `{}(X)`
- String literals -> character code lists

**Printer:**
- Proper quoting for atoms that need it
- List notation for Cons chains
- Improper list support: `[a, b | T]`

---

## Testing

### Tests Added

- `tests/test_parser.py` - 61 tests:
  - TestLexer: 20 tests
  - TestParseAtoms: 7 tests
  - TestParseVariables: 4 tests
  - TestParseNumbers: 9 tests
  - TestParseStructures: 5 tests
  - TestParseLists: 6 tests
  - TestParseComments: 4 tests
  - TestParseErrors: 3 tests
  - TestParseTerms: 2 tests

- `tests/test_printer.py` - 36 tests:
  - TestPrintAtoms: 8 tests
  - TestPrintVariables: 3 tests
  - TestPrintNumbers: 4 tests
  - TestPrintStructures: 4 tests
  - TestPrintLists: 5 tests
  - TestRoundTrip: 12 tests

- `tests/test_akl_files.py` - 12 tests:
  - Lexer tests on real files (member.akl, lists.akl, queens.akl)
  - Parse tests for term types
  - All 45 demo files lexed successfully
  - 37,355 terms parsed from demo files with round-trip verification
  - Comment handling verification

### Test Results

```
============================= 178 passed in 0.21s ==============================
```

---

## Evidence

1. **Atoms parsed**: test_simple_atom, test_quoted_atom, test_operator_atom all pass
2. **Numbers parsed**: test_integer, test_float, test_binary, test_hex, test_char_code all pass
3. **Variables parsed**: test_simple_variable, test_anonymous_variable all pass
4. **Structures parsed**: test_simple_structure, test_nested_structure, test_empty_structure all pass
5. **Lists parsed**: test_empty_list, test_multiple_elements, test_list_with_tail all pass
6. **Comments ignored**: test_line_comment, test_block_comment all pass
7. **Round-trip works**: All 12 TestRoundTrip tests pass
8. **Operator parsing**: TestParseOperators tests all pass (clause, guard, arithmetic operators)
9. **Clause parsing**: TestParseClauses tests pass (facts, rules, multiple clauses)
10. **Real AKL files**: test_parse_all_demo_files parses ALL 45 files (1465 clauses)

---

## Obstacles

### Obstacle 1: `[]` lexed as LBRACKET instead of ATOM

**Observed:** `[]` was being split into `[` and `]` tokens
**Expected:** Single `ATOM` token with value `[]`
**Resolution:** Moved special `[]` check before punctuation check in lexer

### Obstacle 2: Empty structure `foo()` failed to parse

**Observed:** Parser expected at least one argument
**Expected:** Empty args tuple
**Resolution:** Added check for immediate RPAREN after LPAREN

### Obstacle 3: Operators not parsed as terms

**Observed:** `:-`, `->`, `?`, `??`, `|` were lexed but not parsed as operators
**Expected:** Full clause parsing like `member(X, [X|_]).`
**Resolution:** Implemented Pratt parser with operator precedence from AKL current_op.akl

### Obstacle 4: Minus lexed as part of negative number

**Observed:** `N-2` lexed as `N` followed by `-2` (negative number)
**Expected:** `N` `-` `2` (variable, operator, integer)
**Resolution:** Removed negative number handling from lexer; `-` is always operator

### Obstacle 5: Prefix operators as standalone atoms

**Observed:** `!, foo` failed because `!` tried to parse `,` as argument
**Expected:** `!` as cut atom, then `,` as conjunction
**Resolution:** Added `prefix_is_atom()` check based on AKL read.akl logic

### Obstacle 6: Higher-order calls `X(args)`

**Observed:** `Goal(An)` failed - variable followed by parentheses
**Expected:** Parse as `apply(Goal, [An])`
**Resolution:** Added special handling in parse_primary for variable followed by LPAREN

---

## Outcome

**Status:** DONE

**Summary:** Implemented complete term parser and printer with full AKL syntax support including operator precedence parsing. The parser handles all AKL operators (`:-, ->, ?, ??, |, !, @`, etc.) with correct precedence and associativity. Successfully parses all 45 AKL demo files (1465 clauses) from akl-agents.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-04 | Created |
| 2025-12-04 | Completed basic parsing - 168 tests passing |
| 2025-12-04 | Added operator precedence parsing - 178 tests, all 45 AKL files parse |
