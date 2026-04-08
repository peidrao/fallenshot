.PHONY: test

PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
PYTEST ?= $(PYTHON) -m pytest

test:
	$(PYTEST)
