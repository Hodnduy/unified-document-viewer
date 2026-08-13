.PHONY: clean install run run-stop test test-cov test-api

# Install dependencies using uv
install:
	uv sync

# Run all servers (Main API, Sales Mock, Service Mock)
run:
	./scripts/run_all.sh

# Stop all servers
run-stop:
	./scripts/run_all.sh --stop

# Run unit tests
test:
	uv run pytest

# Run unit tests with coverage
test-cov:
	uv run pytest --cov=src --cov-report=term-missing

# Run API smoke tests (requires servers to be running)
test-api:
	./scripts/test_api.sh

# Clean up cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
