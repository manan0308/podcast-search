#!/bin/bash
set -e

echo "🎙️ Podcast Search Engine - Setup Script"
echo "========================================="

# Check dependencies
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ $1 is required but not installed."
        exit 1
    fi
    echo "✅ $1 found"
}

echo ""
echo "Checking dependencies..."
check_command docker
check_command docker-compose
check_command node
check_command npm

# Create .env if not exists
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys before starting"
fi

# Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/audio data/transcripts

# Start infrastructure
echo ""
echo "Starting PostgreSQL and Qdrant..."
docker-compose up -d postgres qdrant

# Wait for services
echo ""
echo "Waiting for services to be ready..."
sleep 5

# Check postgres
until docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done
echo "✅ PostgreSQL is ready"

# Check qdrant
until curl -s http://localhost:6333/readyz > /dev/null 2>&1; do
    echo "Waiting for Qdrant..."
    sleep 2
done
echo "✅ Qdrant is ready"

# Setup backend
echo ""
echo "Setting up backend..."
cd backend

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
echo ""
echo "Running database migrations..."
alembic upgrade head

cd ..

# Setup frontend
echo ""
echo "Setting up frontend..."
cd frontend
npm install
cd ..

echo ""
echo "========================================="
echo "✅ Setup complete!"
echo ""
echo "To start the development servers:"
echo ""
echo "  Backend:  cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
echo ""
echo "Or use Docker Compose:"
echo "  docker-compose up"
echo ""
echo "Don't forget to add your API keys to .env!"
