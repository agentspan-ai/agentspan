#!/bin/bash

echo "🚀 Starting OpenAI Chatbot..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js first."
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm first."
    exit 1
fi

echo "📦 Installing backend dependencies..."
cd "$(dirname "$0")"
npm install

echo "📦 Installing frontend dependencies..."
cd frontend
npm install

echo "✅ Dependencies installed successfully!"
echo ""
echo "🔧 To start the application:"
echo "1. Start the backend server:"
echo "   cd chatbot && npm start"
echo ""
echo "2. In a new terminal, start the frontend:"
echo "   cd chatbot/frontend && npm start"
echo ""
echo "3. Open http://localhost:3000 in your browser"
echo ""
echo "📝 Don't forget to have your OpenAI API key ready!"
