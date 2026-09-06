#pragma once
#include <cstdint>
#include <optional>
#include <vector>

#include "order_book.hpp"

namespace quantpulse {

struct ExecutionRequest {
    Side side;
    double quantity;
    std::optional<double> limit_price;  // nullopt => marketable/aggressive order
    uint64_t latency_ns;                // simulated network+processing latency
    uint64_t submit_timestamp;
};

struct ExecutionReport {
    double filled_quantity;
    double remaining_quantity;
    double avg_fill_price;
    double slippage;              // vs. mid price at submit time
    uint64_t execution_timestamp; // submit_timestamp + latency_ns
    bool fully_filled;
};

// Simulates submitting an order to a given OrderBook after `latency_ns`,
// against the book state passed in (caller advances book state between
// calls to represent time passing / other participants acting).
class ExecutionSimulator {
public:
    explicit ExecutionSimulator(OrderBook& book);

    ExecutionReport submit(const ExecutionRequest& request, uint64_t next_order_id);

private:
    OrderBook& book_;
};

}  // namespace quantpulse
