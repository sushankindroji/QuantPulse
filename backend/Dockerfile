FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY cpp_engine/ /cpp_engine/

# Best-effort build of the optional C++/pybind11 execution engine.
# The Python service works fully without it (pure-Python execution model
# in app/domain/execution.py is the default path used by the API/backtests);
# this just makes the compiled quantpulse_cpp module importable if present.
RUN cd /cpp_engine && \
    mkdir -p build && cd build && \
    (cmake .. -DCMAKE_BUILD_TYPE=Release && make -j"$(nproc)") || \
    echo "C++ engine build skipped/failed - continuing with pure-Python execution model"

RUN mkdir -p /app/data/demo /app/data/raw /app/data/processed /app/experiments

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
