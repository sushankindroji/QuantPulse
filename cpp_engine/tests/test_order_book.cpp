#include <cassert>
#include <iostream>

#include "execution_simulator.hpp"
#include "order_book.hpp"

using namespace quantpulse;

static void test_basic_match() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Sell, 1.7010, 100, 1});
    book.add_limit_order(Order{2, Side::Sell, 1.7012, 50, 2});

    auto fills = book.add_limit_order(Order{3, Side::Buy, 1.7011, 120, 3});
    // Limit 1.7011 crosses the 1.7010 ask fully (100 units) but NOT the
    // 1.7012 ask (above the limit), so only one fill is generated and the
    // remaining 20 units rest on the bid side.
    assert(fills.size() == 1);
    assert(fills[0].price == 1.7010);
    assert(fills[0].quantity == 100);
    assert(book.bid_depth_at(1.7011) == 20);
    std::cout << "test_basic_match OK\n";
}

static void test_price_time_priority() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Buy, 1.7000, 10, 1});
    book.add_limit_order(Order{2, Side::Buy, 1.7000, 10, 2});  // same price, later -> queued 2nd

    auto fills = book.add_limit_order(Order{3, Side::Sell, 1.7000, 15, 3});
    assert(fills.size() == 2);
    assert(fills[0].resting_order_id == 1);  // FIFO: order 1 filled first
    assert(fills[0].quantity == 10);
    assert(fills[1].resting_order_id == 2);
    assert(fills[1].quantity == 5);
    std::cout << "test_price_time_priority OK\n";
}

static void test_partial_fill_rests_remainder() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Sell, 1.7000, 5, 1});
    auto fills = book.add_limit_order(Order{2, Side::Buy, 1.7000, 20, 2});
    assert(fills.size() == 1);
    assert(fills[0].quantity == 5);
    // Remaining 15 units of the buy order should now rest on the bid side.
    assert(book.best_bid().has_value());
    assert(*book.best_bid() == 1.7000);
    assert(book.bid_depth_at(1.7000) == 15);
    std::cout << "test_partial_fill_rests_remainder OK\n";
}

static void test_cancel_order() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Buy, 1.6990, 10, 1});
    assert(book.cancel_order(1) == true);
    assert(book.cancel_order(1) == false);  // already gone
    assert(!book.best_bid().has_value());
    std::cout << "test_cancel_order OK\n";
}

static void test_spread_and_mid() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Buy, 1.7000, 10, 1});
    book.add_limit_order(Order{2, Side::Sell, 1.7010, 10, 2});
    assert(book.spread() > 0.0009 && book.spread() < 0.0011);
    assert(book.mid_price().has_value());
    std::cout << "test_spread_and_mid OK\n";
}

static void test_execution_simulator_slippage() {
    OrderBook book("GBP_CAD");
    book.add_limit_order(Order{1, Side::Buy, 1.6995, 100, 1});
    book.add_limit_order(Order{2, Side::Sell, 1.7005, 50, 2});
    book.add_limit_order(Order{3, Side::Sell, 1.7008, 100, 3});

    ExecutionSimulator sim(book);
    ExecutionRequest req{Side::Buy, 80, std::nullopt, 1000, 10};
    auto report = sim.submit(req, 100);

    assert(report.filled_quantity == 80);
    assert(report.fully_filled);
    assert(report.slippage >= 0.0);  // buying should cost >= mid
    std::cout << "test_execution_simulator_slippage OK\n";
}

int main() {
    test_basic_match();
    test_price_time_priority();
    test_partial_fill_rests_remainder();
    test_cancel_order();
    test_spread_and_mid();
    test_execution_simulator_slippage();
    std::cout << "ALL C++ TESTS PASSED\n";
    return 0;
}
