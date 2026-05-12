#!/bin/bash

# Test runner script for Intelligent Strategy Trading Platform
# This script runs all tests with coverage reporting

set -e

echo "🧪 Running tests for Intelligent Strategy Trading Platform..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "🔄 Activating virtual environment..."
    source venv/bin/activate
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest is not installed. Installing..."
    pip install pytest pytest-cov pytest-mock
fi

# Run tests with coverage
echo "📊 Running tests with coverage..."
python -m pytest tests/ \
    -v \
    --tb=short \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    --cov-report=xml:coverage.xml \
    --junit-xml=test-results.xml

# Run linting if flake8 is available
if command -v flake8 &> /dev/null; then
    echo "🔍 Running linting..."
    flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503
fi

# Run type checking if mypy is available
if command -v mypy &> /dev/null; then
    echo "🔎 Running type checking..."
    mypy src/ --ignore-missing-imports
fi

echo "✅ Tests completed!"
echo ""
echo "📈 Coverage report: htmlcov/index.html"
echo "📄 Coverage XML: coverage.xml"
echo "🧪 Test results: test-results.xml"
