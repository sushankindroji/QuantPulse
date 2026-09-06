#pragma once
#include <cstdint>
#include <deque>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace quantpulse {

enum class Side { Buy, Sell };

struct Order {
    uint64_t id;
    Side side;
    double price;
    double quantity;      // remaining quantity
    uint64_t timestamp;   // used for FIFO queue priority within a price level
};

struct Fill {
    uint64_t resting_order_id;
    uint64_t aggressor_order_id;
    double price;
    double quantity;
    uint64_t timestamp;
};

// Deterministic price/time-priority limit order book with partial fills.
class OrderBook {
public:
    explicit OrderBook(std::string instrument);

    // Inserts a new limit order, matching against the opposite side first.
    // Returns any fills generated (may be empty, or may fully/partially
    // fill the incoming order). Any unfilled remainder rests on the book.
    std::vector<Fill> add_limit_order(Order order);

    // Cancels a resting order by id. Returns true if it was found & removed.
    bool cancel_order(uint64_t order_id);

    std::optional<double> best_bid() const;
    std::optional<double> best_ask() const;
    std::optional<double> mid_price() const;
    double spread() const;

    double bid_depth_at(double price) const;
    double ask_depth_at(double price) const;

    // Sum of resting quantity within `levels` price levels of the touch,
    // used for depth-imbalance microstructure features.
    double bid_depth(int levels) const;
    double ask_depth(int levels) const;

    size_t bid_order_count() const;
    size_t ask_order_count() const;

    const std::string& instrument() const { return instrument_; }

private:
    std::string instrument_;
    // Bids: highest price first. Asks: lowest price first.
    std::map<double, std::deque<Order>, std::greater<double>> bids_;
    std::map<double, std::deque<Order>, std::less<double>> asks_;

    std::vector<Fill> match(Order& incoming);
};

}  // namespace quantpulse
