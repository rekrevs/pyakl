"""
REPL (Read-Eval-Print Loop) for PyAKL.

This module provides the AKL REPL using qa.akl with reflection primitives.
"""

from __future__ import annotations
import sys
from pathlib import Path

from .parser import parse_term, ParseError
from .printer import print_term
from .program import Program, load_file
from .interpreter import Interpreter


def run_repl(program: Program | None = None) -> None:
    """
    Run the AKL REPL (qa.akl).

    This uses the reflection primitives to provide proper AKL semantics.
    """
    prog = program or Program()

    # Load the qa.akl REPL
    qa_path = Path(__file__).parent / "library" / "qa.akl"
    if not qa_path.exists():
        print(f"Error: qa.akl not found at {qa_path}", file=sys.stderr)
        sys.exit(1)

    try:
        load_file(qa_path, prog)
    except Exception as e:
        print(f"Error loading qa.akl: {e}", file=sys.stderr)
        sys.exit(1)

    # Run main/0
    interp = Interpreter(prog)
    goal = parse_term("main")

    try:
        # Execute main - it will handle all I/O
        for _ in interp.solve(goal):
            pass  # main/0 should handle everything
    except (EOFError, KeyboardInterrupt):
        print()
    except Exception as e:
        print(f"\nError in REPL: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def execute_query(query_str: str, program: Program, show_all: bool = False) -> None:
    """
    Execute a single query and print results.

    Args:
        query_str: The query string (without trailing period)
        program: The program to query against
        show_all: If True, show all solutions without prompting
    """
    try:
        goal = parse_term(query_str)
    except ParseError as e:
        print(f"Syntax error: {e}")
        return

    interp = Interpreter(program)
    solution_count = 0

    for solution in interp.solve(goal):
        solution_count += 1

        if solution_count == 1:
            print()

        if solution.bindings:
            bindings_list = list(solution.bindings.items())
            for i, (name, value) in enumerate(bindings_list):
                if i < len(bindings_list) - 1:
                    print(f"{name} = {print_term(value)},")
                else:
                    print(f"{name} = {print_term(value)}", end="")
        else:
            print("true", end="")

        if show_all:
            print(" ;")
            continue

        # Interactive: prompt for more
        try:
            response = input(" ? ").strip()
            if response != ";":
                break
        except (EOFError, KeyboardInterrupt):
            print()
            break

    print()
    if solution_count > 0:
        print("yes")
    else:
        print("no")


def main() -> None:
    """Main entry point for the REPL."""
    import argparse

    parser = argparse.ArgumentParser(description="PyAKL REPL")
    parser.add_argument(
        "files",
        nargs="*",
        help="AKL files to load"
    )
    parser.add_argument(
        "-e", "--execute",
        help="Execute query and exit"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all solutions without prompting"
    )

    args = parser.parse_args()

    # Create program
    program = Program()

    # Load any specified files first
    for filepath in args.files:
        try:
            load_file(filepath, program)
            print(f"% Loaded {filepath}")
        except Exception as e:
            print(f"Error loading {filepath}: {e}", file=sys.stderr)
            sys.exit(1)

    # Execute query if specified
    if args.execute:
        query_str = args.execute
        if query_str.endswith('.'):
            query_str = query_str[:-1]
        execute_query(query_str, program, show_all=args.all)
        return

    # Run REPL
    run_repl(program)


if __name__ == "__main__":
    main()
