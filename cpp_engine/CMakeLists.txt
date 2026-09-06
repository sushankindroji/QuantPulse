cmake_minimum_required(VERSION 3.16)
project(quantpulse_execution_engine CXX)

enable_testing()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

include_directories(include)

add_library(quantpulse_engine STATIC
    src/order_book.cpp
    src/execution_simulator.cpp
)

# Plain C++ test binary (no external test framework dependency required).
add_executable(run_cpp_tests tests/test_order_book.cpp)
target_link_libraries(run_cpp_tests PRIVATE quantpulse_engine)
add_test(NAME cpp_engine_tests COMMAND run_cpp_tests)

# Optional Python bindings via pybind11. Only built if pybind11 is found,
# so the C++ core (and its tests) still build in environments without it.
find_package(pybind11 QUIET)
if(pybind11_FOUND)
    pybind11_add_module(quantpulse_cpp bindings/pybind_module.cpp src/order_book.cpp src/execution_simulator.cpp)
    message(STATUS "pybind11 found -- building Python bindings (quantpulse_cpp)")
else()
    message(STATUS "pybind11 not found -- skipping Python bindings, C++ core still builds")
endif()
