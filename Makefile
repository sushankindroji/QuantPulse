.PHONY: demo up down build test test-python test-cpp lint download-data validate-data prepare-data run-research clean

# ---- Demo mode: zero setup, zero data, zero cost ----
demo: up
	@echo "QuantPulse demo running: frontend http://localhost:3000  backend http://localhost:8000/docs"

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

# ---- Testing ----
test: test-python test-cpp

test-python:
	cd backend && PYTHONPATH=. python3 -m pytest tests/ -v

test-cpp:
	cd cpp_engine && mkdir -p build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$$(nproc) && ./run_cpp_tests

lint:
	cd backend && python3 -m pyflakes app || true

# ---- Real data pipeline (all zero-cost) ----
download-data:
	@echo "Estimating storage and downloading real historical data (see docs/DATA_ACQUISITION.md)"
	cd backend && PYTHONPATH=. python3 scripts/download_data.py --instrument GBP_CAD --timeframe 1h

validate-data:
	cd backend && PYTHONPATH=. python3 scripts/validate_data.py --instrument GBP_CAD --timeframe 1h

prepare-data:
	cd backend && PYTHONPATH=. python3 scripts/prepare_data.py --instrument GBP_CAD --timeframe 1h

run-research:
	cd backend && PYTHONPATH=. python3 scripts/run_research.py --instrument GBP_CAD --timeframe 1h --data-mode demo

clean:
	rm -rf backend/__pycache__ backend/app/**/__pycache__ backend/.pytest_cache cpp_engine/build frontend/.next frontend/node_modules
