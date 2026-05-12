#!/bin/bash

# Setup script for Intelligent Strategy Trading Platform
# This script sets up the development environment

set -e

echo "🚀 Setting up Intelligent Strategy Trading Platform..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or later."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "📦 Found Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

if [ -f "requirements-dev.txt" ]; then
    pip install -r requirements-dev.txt
fi

# Install package in development mode
echo "🔧 Installing package in development mode..."
pip install -e .

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data/raw
mkdir -p data/processed
mkdir -p logs
mkdir -p models
mkdir -p results

# Set up pre-commit hooks if available
if [ -f ".pre-commit-config.yaml" ]; then
    echo "🪝 Setting up pre-commit hooks..."
    pre-commit install
fi

# Run initial tests
echo "🧪 Running initial tests..."
python -m pytest tests/ -v --tb=short

echo "✅ Setup completed successfully!"
echo ""
echo "🎯 Next steps:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run the application: python -m src.ist.main"
echo "3. Run tests: pytest tests/"
echo ""
echo "📚 Documentation: docs/"
echo "🔧 Configuration: config/"
