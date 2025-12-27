# Podcast Search - Makefile
# Quick commands for development

.PHONY: up down logs test migrate shell clean help

# Default target
help:
	@echo "Podcast Search - Available Commands"
	@echo "===================================="
	@echo "make up        - Start all services (docker-compose)"
	@echo "make down      - Stop all services"
	@echo "make logs      - View service logs"
	@echo "make test      - Run backend tests"
	@echo "make migrate   - Run database migrations"
	@echo "make shell     - Open backend shell"
	@echo "make clean     - Remove containers and volumes"
	@echo ""
	@echo "Development:"
	@echo "make dev-backend   - Run backend locally (no docker)"
	@echo "make dev-frontend  - Run frontend locally (no docker)"
	@echo "make infra         - Start only infra (postgres, redis, qdrant)"

# Start all services
up:
	docker-compose up -d
	@echo ""
	@echo "Services starting..."
	@echo "  Frontend: http://localhost:3000"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Qdrant:   http://localhost:6333"
	@echo ""
	@echo "Run 'make logs' to view logs"

# Stop all services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# Run tests
test:
	cd backend && python -m pytest tests/ -v

# Run database migrations
migrate:
	docker-compose exec backend alembic upgrade head

# Open backend shell
shell:
	docker-compose exec backend bash

# Clean up everything
clean:
	docker-compose down -v
	rm -rf data/postgres data/redis data/qdrant

# Start only infrastructure (for local development)
infra:
	docker-compose up -d postgres redis qdrant
	@echo ""
	@echo "Infrastructure ready:"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis:      localhost:6380"
	@echo "  Qdrant:     localhost:6333"

# Run backend locally (requires infra running)
dev-backend:
	cd backend && \
	source venv/bin/activate && \
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run frontend locally
dev-frontend:
	cd frontend && npm run dev

# Run E2E test
e2e-test:
	cd backend && python tests/e2e/run_nikhil_kamath_test.py

# Evaluate search quality
eval:
	cd backend && python -m tests.evaluation.golden_queries
