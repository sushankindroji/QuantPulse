#include "order_book.hpp"

#include <algorithm>

namespace quantpulse {

OrderBook::OrderBook(std::string instrument) : instrument_(std::move(instrument)) {}

std::vector<Fill> OrderBook::match(Order& incoming) {
    std::vector<Fill> fills;
    const double EPS = 1e-12;

    if (incoming.side == Side::Buy) {
        auto it = asks_.begin();
        while (it != asks_.end() && incoming.quantity > EPS && it->first <= incoming.price) {
            auto& queue = it->second;
            while (!queue.empty() && incoming.quantity > EPS) {
                Order& resting = queue.front();
                double traded = std::min(incoming.quantity, resting.quantity);
                fills.push_back(Fill{resting.id, incoming.id, resting.price, traded, incoming.timestamp});
                incoming.quantity -= traded;
                resting.quantity -= traded;
                if (resting.quantity <= EPS) queue.pop_front();
            }
            if (queue.empty()) {
                it = asks_.erase(it);
            } else {
                ++it;
            }
        }
    } else {
        auto it = bids_.begin();
        while (it != bids_.end() && incoming.quantity > EPS && it->first >= incoming.price) {
            auto& queue = it->second;
            while (!queue.empty() && incoming.quantity > EPS) {
                Order& resting = queue.front();
                double traded = std::min(incoming.quantity, resting.quantity);
                fills.push_back(Fill{resting.id, incoming.id, resting.price, traded, incoming.timestamp});
                incoming.quantity -= traded;
                resting.quantity -= traded;
                if (resting.quantity <= EPS) queue.pop_front();
            }
            if (queue.empty()) {
                it = bids_.erase(it);
            } else {
                ++it;
            }
        }
    }
    return fills;
}

std::vector<Fill> OrderBook::add_limit_order(Order order) {
    std::vector<Fill> fills = match(order);
    const double EPS = 1e-12;
    if (order.quantity > EPS) {
        if (order.side == Side::Buy) {
            bids_[order.price].push_back(order);
        } else {
            asks_[order.price].push_back(order);
        }
    }
    return fills;
}

bool OrderBook::cancel_order(uint64_t order_id) {
    for (auto bit = bids_.begin(); bit != bids_.end(); ++bit) {
        auto& queue = bit->second;
        for (auto it = queue.begin(); it != queue.end(); ++it) {
            if (it->id == order_id) {
                queue.erase(it);
                if (queue.empty()) bids_.erase(bit);
                return true;
            }
        }
    }
    for (auto ait = asks_.begin(); ait != asks_.end(); ++ait) {
        auto& queue = ait->second;
        for (auto it = queue.begin(); it != queue.end(); ++it) {
            if (it->id == order_id) {
                queue.erase(it);
                if (queue.empty()) asks_.erase(ait);
                return true;
            }
        }
    }
    return false;
}

std::optional<double> OrderBook::best_bid() const {
    if (bids_.empty()) return std::nullopt;
    return bids_.begin()->first;
}

std::optional<double> OrderBook::best_ask() const {
    if (asks_.empty()) return std::nullopt;
    return asks_.begin()->first;
}

std::optional<double> OrderBook::mid_price() const {
    auto bid = best_bid();
    auto ask = best_ask();
    if (!bid || !ask) return std::nullopt;
    return (*bid + *ask) / 2.0;
}

double OrderBook::spread() const {
    auto bid = best_bid();
    auto ask = best_ask();
    if (!bid || !ask) return 0.0;
    return *ask - *bid;
}

double OrderBook::bid_depth_at(double price) const {
    auto it = bids_.find(price);
    if (it == bids_.end()) return 0.0;
    double total = 0.0;
    for (const auto& o : it->second) total += o.quantity;
    return total;
}

double OrderBook::ask_depth_at(double price) const {
    auto it = asks_.find(price);
    if (it == asks_.end()) return 0.0;
    double total = 0.0;
    for (const auto& o : it->second) total += o.quantity;
    return total;
}

double OrderBook::bid_depth(int levels) const {
    double total = 0.0;
    int i = 0;
    for (const auto& [price, queue] : bids_) {
        if (i++ >= levels) break;
        for (const auto& o : queue) total += o.quantity;
    }
    return total;
}

double OrderBook::ask_depth(int levels) const {
    double total = 0.0;
    int i = 0;
    for (const auto& [price, queue] : asks_) {
        if (i++ >= levels) break;
        for (const auto& o : queue) total += o.quantity;
    }
    return total;
}

size_t OrderBook::bid_order_count() const {
    size_t n = 0;
    for (const auto& [price, queue] : bids_) n += queue.size();
    return n;
}

size_t OrderBook::ask_order_count() const {
    size_t n = 0;
    for (const auto& [price, queue] : asks_) n += queue.size();
    return n;
}

}  // namespace quantpulse
