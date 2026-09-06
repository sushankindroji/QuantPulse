#include "execution_simulator.hpp"

#include <limits>

namespace quantpulse {

ExecutionSimulator::ExecutionSimulator(OrderBook& book) : book_(book) {}

ExecutionReport ExecutionSimulator::submit(const ExecutionRequest& request, uint64_t next_order_id) {
    auto mid_before = book_.mid_price();

    double limit_price;
    if (request.limit_price.has_value()) {
        limit_price = *request.limit_price;
    } else {
        // Marketable order: cross the book aggressively.
        limit_price = (request.side == Side::Buy)
                          ? std::numeric_limits<double>::max()
                          : -std::numeric_limits<double>::max();
    }

    Order order{next_order_id, request.side, limit_price, request.quantity, request.submit_timestamp + request.latency_ns};
    std::vector<Fill> fills = book_.add_limit_order(order);

    double filled_qty = 0.0;
    double notional = 0.0;
    for (const auto& f : fills) {
        filled_qty += f.quantity;
        notional += f.quantity * f.price;
    }

    double avg_price = filled_qty > 0 ? notional / filled_qty : 0.0;
    double remaining = request.quantity - filled_qty;

    double slippage = 0.0;
    if (mid_before.has_value() && filled_qty > 0) {
        double direction = (request.side == Side::Buy) ? 1.0 : -1.0;
        slippage = direction * (avg_price - *mid_before);
    }

    return ExecutionReport{
        filled_qty,
        remaining,
        avg_price,
        slippage,
        request.submit_timestamp + request.latency_ns,
        remaining <= 1e-12,
    };
}

}  // namespace quantpulse
