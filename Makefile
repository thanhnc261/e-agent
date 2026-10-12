.DEFAULT_GOAL := help

BACKEND_PORT ?= 8787
FRONTEND_PORT ?= 5173
E2E_PORT ?= 8791
PROFILE ?= profiles/dev-ollama.json

export E_AGENT_DEV_BACKEND_PORT := $(BACKEND_PORT)
export E_AGENT_DEV_FRONTEND_PORT := $(FRONTEND_PORT)
export E_AGENT_DEV_PROFILE := $(PROFILE)
export E_AGENT_UI_PORT := $(E2E_PORT)

.PHONY: help setup browser-install ui-build dev backend frontend e2e

help:
	@echo "make setup           Install Python and frontend dependencies"
	@echo "make browser-install Install Playwright Chromium"
	@echo "make dev             Build UI assets and start backend + Vite frontend"
	@echo "make backend         Build UI assets and start only the backend"
	@echo "make frontend        Start only the Vite frontend (backend must be running)"
	@echo "make e2e             Build UI and run Playwright against its own fixture backend"
	@echo "Options: BACKEND_PORT=8787 FRONTEND_PORT=5173 E2E_PORT=8791 PROFILE=path.json"
	@echo "make dev uses the real Ollama agent (profiles/dev-ollama.json); PROFILE= gives the scripted fixture driver"

setup:
	uv sync --locked
	pnpm --dir ui install --frozen-lockfile

browser-install:
	pnpm --dir ui exec playwright install chromium

ui-build:
	pnpm --dir ui build

dev: ui-build
	uv run python scripts/dev/serve.py dev

backend: ui-build
	uv run python scripts/dev/serve.py backend

frontend:
	uv run python scripts/dev/serve.py frontend

e2e: ui-build
	pnpm --dir ui conformance
