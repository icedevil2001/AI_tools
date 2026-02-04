#!/usr/bin/env bash

# Quick setup script for the AI Image Generator

echo "🎨 AI Image Generator Setup"
echo "=========================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp .env.example .env
    echo "✅ Created .env file from template"
    echo "🔑 Please edit .env and add your OpenAI API key:"
    echo "   OPENAI_API_KEY=your-openai-api-key-here"
    echo ""
fi

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ] && [ ! -d ".venv" ]; then
    echo "📦 Installing dependencies with UV..."
    uv sync
fi

echo "🚀 Starting the AI Image Generator..."
echo "📋 The app will open in your browser at http://localhost:7860"
echo "🔑 Make sure your OpenAI API key is set in the .env file"
echo ""

# Run the application
uv run python main.py
