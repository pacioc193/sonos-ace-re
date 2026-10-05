cmake_minimum_required(VERSION 3.20)
project(ace_cli CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Portable protocol tests (build everywhere).
add_executable(ace_tests tests/test_core.cpp)
enable_testing()
add_test(NAME core COMMAND ace_tests)

if(WIN32)
  # Static CRT: the exe runs on a clean Windows without the VC++ redistributable.
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded")
  add_executable(ace app/ace_cli.cpp)
  # C++/WinRT needs the standard <coroutine> header (C++20); the core stays C++17-clean.
  set_target_properties(ace PROPERTIES CXX_STANDARD 20)
  target_compile_options(ace PRIVATE /W3 /EHsc /permissive- /utf-8)
  target_link_libraries(ace PRIVATE windowsapp)
  target_compile_definitions(ace PRIVATE NOMINMAX WIN32_LEAN_AND_MEAN _CRT_SECURE_NO_WARNINGS)
endif()
