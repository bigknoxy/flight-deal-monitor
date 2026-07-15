.PHONY: help install dev test lint typecheck format docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Run development server"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linter (ruff)"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make format     - Format code (black)"
	@echo "  make docker-up  - Start Docker containers"
	@echo "  make docker-down - Stop Docker containers"

install:
	pip install -r requirements.txt

dev:
	python -m app.main

test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	ruff check app/ tests/

typecheck:
	mypy app/ --ignore-missing-imports || true

format:
	black app/ tests/