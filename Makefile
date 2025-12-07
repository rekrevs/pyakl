# PyAKL Makefile

.PHONY: help flatten
.DEFAULT_GOAL := help

# Colors for terminal output
BLUE := \033[0;34m
NC := \033[0m

# Project paths
PROJECT_ROOT := $(shell pwd)

help:
	@echo "Available targets:"
	@echo "  make flatten              Concatenate all source files to stdout"

flatten:
	@echo "$(BLUE)Flattening all source files$(NC)"
	@find $(PROJECT_ROOT) -type f \( \
		-name "*.py" -o \
		-name "*.md" \
		\) \
		! -path "*/.git/*" \
		! -path "*/__pycache__/*" \
		! -path "*/pyakl.egg-info/*" \
		! -path "*/.pytest_cache/*" \
		! -path "*/venv/*" \
		! -path "*/dev-log/archive/*" \
		| sort | xargs flatten
