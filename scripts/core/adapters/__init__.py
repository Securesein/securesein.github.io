"""Benchmark ingestion adapters. Each one is independent and wrapped by
the benchmarks channel: a broken adapter logs a failure and the run
continues, so one dead scraper can never stop the Epoch pull landing."""
