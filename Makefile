# Makefile for Intelligent Strategy Trading Platform
# This file provides common development and deployment commands

.PHONY: help install dev test lint format clean build docker-build docker-run docker-stop docs

# Default target
help:
	@echo "Intelligent Strategy Trading Platform - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  install     Install dependencies and setup environment"
	@echo "  dev         Run development server"
	@echo "  test        Run all tests with coverage"
	@echo "  lint        Run code linting and formatting checks"
	@echo "  format      Format code with black and isort"
	@echo "  clean       Clean temporary files and directories"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build    Build Docker image"
	@echo "  docker-run      Run Docker container"
	@echo "  docker-stop     Stop Docker containers"
	@echo "  docker-dev      Run development environment with Docker"
	@echo ""
	@echo "Documentation:"
	@echo "  docs        Generate documentation"
	@echo "  docs-serve  Serve documentation locally"
	@echo ""
	@echo "Database:"
	@echo "  db-init     Initialize database"
	@echo "  db-migrate  Run database migrations"
	@echo "  db-backup   Backup database"
	@echo ""
	@echo "Deployment:"
	@echo "  build       Build package for distribution"
	@echo "  deploy      Deploy to production"

# Development setup
install:
	@echo "Setting up development environment..."
	python3 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r requirements.txt
	. venv/bin/activate && pip install -r requirements-dev.txt
	. venv/bin/activate && pip install -e .
	@echo "Creating necessary directories..."
	mkdir -p data/raw data/processed logs models results
	@echo "Setup completed successfully!"

# Development server
dev:
	@echo "Starting development server..."
	. venv/bin/activate && python -m uvicorn src.ist.api.main:app --host 0.0.0.0 --port 8000 --reload

# Testing
test:
	@echo "Running tests..."
	. venv/bin/activate && python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

test-fast:
	@echo "Running fast tests (unit tests only)..."
	. venv/bin/activate && python -m pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	. venv/bin/activate && python -m pytest tests/integration/ -v

# Code quality
lint:
	@echo "Running linting..."
	. venv/bin/activate && flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503
	. venv/bin/activate && mypy src/ --ignore-missing-imports
	. venv/bin/activate && bandit -r src/

format:
	@echo "Formatting code..."
	. venv/bin/activate && black src/ tests/
	. venv/bin/activate && isort src/ tests/

format-check:
	@echo "Checking code format..."
	. venv/bin/activate && black --check src/ tests/
	. venv/bin/activate && isort --check-only src/ tests/

# Security
security:
	@echo "Running security checks..."
	. venv/bin/activate && bandit -r src/ -f json -o security-report.json
	. venv/bin/activate && safety check --json --output safety-report.json

# Cleanup
clean:
	@echo "Cleaning temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	@echo "Clean completed!"

# Docker commands
docker-build:
	@echo "Building Docker image..."
	docker build -t intelligent-strategy-trading:latest .

docker-run:
	@echo "Running Docker container..."
	docker run -p 8000:8000 --name intelligent-trading intelligent-strategy-trading:latest

docker-stop:
	@echo "Stopping Docker containers..."
	docker stop intelligent-trading || true
	docker rm intelligent-trading || true

docker-dev:
	@echo "Starting development environment with Docker..."
	docker-compose -f docker-compose.dev.yml up -d

docker-dev-down:
	@echo "Stopping development environment..."
	docker-compose -f docker-compose.dev.yml down

docker-dev-logs:
	@echo "Showing development logs..."
	docker-compose -f docker-compose.dev.yml logs -f

# Database commands
db-init:
	@echo "Initializing database..."
	. venv/bin/activate && python -c "
from src.ist.core.database import init_database
init_database()
print('Database initialized successfully!')
"

db-migrate:
	@echo "Running database migrations..."
	. venv/bin/activate && alembic upgrade head

db-backup:
	@echo "Creating database backup..."
	@mkdir -p backups
	docker exec trading-postgres pg_dump -U trading_user trading_db > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql

# Documentation
docs:
	@echo "Generating documentation..."
	. venv/bin/activate && mkdocs build

docs-serve:
	@echo "Serving documentation..."
	. venv/bin/activate && mkdocs serve

docs-deploy:
	@echo "Deploying documentation..."
	. venv/bin/activate && mkdocs gh-deploy

# Build and distribution
build:
	@echo "Building package for distribution..."
	rm -rf dist/
	. venv/bin/activate && python setup.py sdist bdist_wheel

build-check:
	@echo "Checking built package..."
	. venv/bin/activate && twine check dist/*

# Version management
version-patch:
	@echo "Bumping patch version..."
	. venv/bin/activate && bump2version patch

version-minor:
	@echo "Bumping minor version..."
	. venv/bin/activate && bump2version minor

version-major:
	@echo "Bumping major version..."
	. venv/bin/activate && bump2version major

# Pre-commit
pre-commit-install:
	@echo "Installing pre-commit hooks..."
	. venv/bin/activate && pre-commit install

pre-commit-run:
	@echo "Running pre-commit hooks..."
	. venv/bin/activate && pre-commit run --all-files

# Performance
benchmark:
	@echo "Running performance benchmarks..."
	. venv/bin/activate && python -m pytest tests/performance/ -v --benchmark-only

profile:
	@echo "Running profiler..."
	. venv/bin/activate && python -m cProfile -o profile.stats src/ist/main.py

# Monitoring
monitor:
	@echo "Starting monitoring dashboard..."
	. venv/bin/activate && python src/ist/monitoring/dashboard.py

health-check:
	@echo "Running health checks..."
	. venv/bin/activate && python src/ist/health/check.py

# Deployment
deploy-staging:
	@echo "Deploying to staging..."
	. venv/bin/activate && ansible-playbook deploy/staging.yml

deploy-production:
	@echo "Deploying to production..."
	. venv/bin/activate && ansible-playbook deploy/production.yml

# Data management
data-download:
	@echo "Downloading market data..."
	. venv/bin/activate && python src/ist/data/download.py

data-process:
	@echo "Processing market data..."
	. venv/bin/activate && python src/ist/data/process.py

data-backup:
	@echo "Backing up data..."
	@mkdir -p backups/data
	tar -czf backups/data/data_backup_$(shell date +%Y%m%d_%H%M%S).tar.gz data/

# Development shortcuts
run: dev
check: lint test
all: clean install lint test docs

# CI/CD helpers
ci-test:
	@echo "Running CI tests..."
	. venv/bin/activate && python -m pytest tests/ --junitxml=test-results.xml --cov=src --cov-report=xml

ci-build:
	@echo "Running CI build..."
	$(MAKE) clean
	$(MAKE) install
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) security
	$(MAKE) build

# Quick commands
qtest: test-fast
qlint: flake8 src/ tests/
qclean: find . -name "*.pyc" -delete && find . -name "__pycache__" -type d -exec rm -rf {} +
