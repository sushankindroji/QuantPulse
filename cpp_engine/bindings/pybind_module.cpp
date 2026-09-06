#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "execution_simulator.hpp"
#include "order_book.hpp"

namespace py = pybind11;
using namespace quantpulse;

PYBIND11_MODULE(quantpulse_cpp, m) {
    m.doc() = "QuantPulse C++17 order book & execution simulator (pybind11 bindings)";

    py::enum_<Side>(m, "Side")
        .value("Buy", Side::Buy)
        .value("Sell", Side::Sell);

    py::class_<Order>(m, "Order")
        .def(py::init<>())
        .def(py::init([](uint64_t id, Side side, double price, double qty, uint64_t ts) {
            return Order{id, side, price, qty, ts};
        }))
        .def_readwrite("id", &Order::id)
        .def_readwrite("side", &Order::side)
        .def_readwrite("price", &Order::price)
        .def_readwrite("quantity", &Order::quantity)
        .def_readwrite("timestamp", &Order::timestamp);

    py::class_<Fill>(m, "Fill")
        .def_readonly("resting_order_id", &Fill::resting_order_id)
        .def_readonly("aggressor_order_id", &Fill::aggressor_order_id)
        .def_readonly("price", &Fill::price)
        .def_readonly("quantity", &Fill::quantity)
        .def_readonly("timestamp", &Fill::timestamp);

    py::class_<OrderBook>(m, "OrderBook")
        .def(py::init<std::string>())
        .def("add_limit_order", &OrderBook::add_limit_order)
        .def("cancel_order", &OrderBook::cancel_order)
        .def("best_bid", &OrderBook::best_bid)
        .def("best_ask", &OrderBook::best_ask)
        .def("mid_price", &OrderBook::mid_price)
        .def("spread", &OrderBook::spread)
        .def("bid_depth", &OrderBook::bid_depth)
        .def("ask_depth", &OrderBook::ask_depth)
        .def("bid_order_count", &OrderBook::bid_order_count)
        .def("ask_order_count", &OrderBook::ask_order_count)
        .def("instrument", &OrderBook::instrument);

    py::class_<ExecutionRequest>(m, "ExecutionRequest")
        .def(py::init([](Side side, double qty, py::object limit_price, uint64_t latency_ns, uint64_t ts) {
            std::optional<double> lp = std::nullopt;
            if (!limit_price.is_none()) lp = limit_price.cast<double>();
            return ExecutionRequest{side, qty, lp, latency_ns, ts};
        }));

    py::class_<ExecutionReport>(m, "ExecutionReport")
        .def_readonly("filled_quantity", &ExecutionReport::filled_quantity)
        .def_readonly("remaining_quantity", &ExecutionReport::remaining_quantity)
        .def_readonly("avg_fill_price", &ExecutionReport::avg_fill_price)
        .def_readonly("slippage", &ExecutionReport::slippage)
        .def_readonly("execution_timestamp", &ExecutionReport::execution_timestamp)
        .def_readonly("fully_filled", &ExecutionReport::fully_filled);

    py::class_<ExecutionSimulator>(m, "ExecutionSimulator")
        .def(py::init<OrderBook&>())
        .def("submit", &ExecutionSimulator::submit);
}
