"""Reproducible benchmark measuring BubbleStreamConsumer 15ms polling overhead and first-token latency.

Methodology:
- Idle wakeups & CPU: Measures total asyncio loop wakeups and process CPU time (user + kernel)
  over a fixed wall-clock observation window across 1, 10, and 50 concurrent consumers.
- First-token latency: Measures elapsed time from synchronous producer on_delta() enqueue
  until the consumer event-loop coroutine dequeues the item.
  Uses randomized phase arrival offsets (0.1ms to 16.0ms) relative to the 15ms polling cycle
  across 100 randomized trials to calculate Min, Mean, P50, P95, P99, and Max latency.
- Timer resolution awareness: Documents Windows default 15.625ms timer interrupt quantum.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

repo_root = str(Path(__file__).resolve().parent.parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from gateway.bubble_stream_consumer import BubbleStreamConsumer, _STREAM_END


class BenchmarkMockAdapter:
    def __init__(self):
        self.sent_messages = []

    async def send(self, chat_id: str, text: str, **kwargs):
        self.sent_messages.append({"chat_id": chat_id, "text": text})
        return {"ok": True, "id": "bench_msg_id"}

    async def send_typing(self, chat_id: str):
        pass


class InstrumentedConsumer(BubbleStreamConsumer):
    """Subclass of BubbleStreamConsumer tracking wakeup counts and token transit timestamps without altering production code."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.idle_wakeups = 0
        self.first_token_enqueued_at: Optional[float] = None
        self.first_token_dequeued_at: Optional[float] = None

    async def run(self) -> None:
        self._bubble_queue.start()

        while True:
            if not self._run_still_current():
                await self._bubble_queue.cancel(reason="turn_superseded")
                break

            try:
                item = self._inbound_queue.get_nowait()
                if self.first_token_enqueued_at is not None and self.first_token_dequeued_at is None:
                    self.first_token_dequeued_at = time.perf_counter()
            except Exception:
                self.idle_wakeups += 1
                await asyncio.sleep(0.015)
                continue

            if item is _STREAM_END:
                rem = self._parser.finish()
                for b in rem:
                    await self._bubble_queue.enqueue(b)
                await self._bubble_queue.finish_stream()
                try:
                    await self._bubble_queue.wait_finished(timeout=5.0)
                except Exception:
                    pass
                break

            if isinstance(item, str) and item:
                new_bubbles = self._parser.feed(item)
                for b in new_bubbles:
                    await self._bubble_queue.enqueue(b)


async def run_idle_benchmark(num_consumers: int, duration_s: float = 2.0):
    adapter = BenchmarkMockAdapter()
    consumers = [
        InstrumentedConsumer(chat_id=f"bench_chat_{i}", adapter=adapter)
        for i in range(num_consumers)
    ]

    tasks = [asyncio.create_task(c.run()) for c in consumers]
    await asyncio.sleep(0.05)

    for c in consumers:
        c.idle_wakeups = 0

    cpu_start = time.process_time()
    wall_start = time.perf_counter()

    await asyncio.sleep(duration_s)

    wall_elapsed = time.perf_counter() - wall_start
    cpu_elapsed = time.process_time() - cpu_start

    total_wakeups = sum(c.idle_wakeups for c in consumers)
    wakeups_per_sec = total_wakeups / wall_elapsed

    for c in consumers:
        c.finish()
    await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "num_consumers": num_consumers,
        "wall_duration_s": wall_elapsed,
        "cpu_time_s": cpu_elapsed,
        "cpu_utilization_pct": (cpu_elapsed / wall_elapsed) * 100.0,
        "total_wakeups": total_wakeups,
        "wakeups_per_sec": wakeups_per_sec,
        "wakeups_per_sec_per_consumer": wakeups_per_sec / num_consumers,
    }


async def run_latency_benchmark(num_consumers: int, trials: int = 100):
    adapter = BenchmarkMockAdapter()
    latencies_ms = []

    for trial in range(trials):
        consumers = [
            InstrumentedConsumer(chat_id=f"bench_lat_{trial}_{i}", adapter=adapter)
            for i in range(num_consumers)
        ]
        tasks = [asyncio.create_task(c.run()) for c in consumers]

        # Settle into idle state
        await asyncio.sleep(0.020)

        # Inject randomized arrival phase offset relative to 15ms cycle (0.5ms to 16.0ms)
        arrival_offset_s = random.uniform(0.0005, 0.0160)
        await asyncio.sleep(arrival_offset_s)

        target = consumers[trial % num_consumers]
        target.first_token_enqueued_at = time.perf_counter()
        target.on_delta("<bubble>hello latency test</bubble>")

        deadline = time.perf_counter() + 0.5
        while target.first_token_dequeued_at is None and time.perf_counter() < deadline:
            await asyncio.sleep(0.0005)

        if target.first_token_dequeued_at is not None:
            lat_ms = (target.first_token_dequeued_at - target.first_token_enqueued_at) * 1000.0
            latencies_ms.append(lat_ms)

        for c in consumers:
            c.finish()
        await asyncio.gather(*tasks, return_exceptions=True)

    latencies_ms.sort()
    n = len(latencies_ms)
    avg_lat = sum(latencies_ms) / n if n else 0.0
    p50_lat = latencies_ms[int(n * 0.50)] if n else 0.0
    p95_lat = latencies_ms[int(n * 0.95)] if n else 0.0
    p99_lat = latencies_ms[min(n - 1, int(n * 0.99))] if n else 0.0
    max_lat = max(latencies_ms) if n else 0.0
    min_lat = min(latencies_ms) if n else 0.0

    return {
        "num_consumers": num_consumers,
        "trials": n,
        "min_ms": min_lat,
        "avg_ms": avg_lat,
        "p50_ms": p50_lat,
        "p95_ms": p95_lat,
        "p99_ms": p99_lat,
        "max_ms": max_lat,
    }


async def main():
    print("=" * 70, flush=True)
    print(" AirHermes Consumer 15ms Polling Performance Benchmark", flush=True)
    print("=" * 70, flush=True)
    print(f"OS: {os.name} | Python: {sys.version.split()[0]}", flush=True)
    print("Note on Windows Timer Resolution: Default OS timer resolution is 15.625ms", flush=True)
    print("(64 ticks/s). asyncio.sleep(0.015) is quantized to the nearest OS tick.", flush=True)
    print(flush=True)

    print("--- 1. Idle Wakeup & CPU Time Measurements (Duration: 2.0s) ---", flush=True)
    for n in (1, 10, 50):
        res = await run_idle_benchmark(n, duration_s=2.0)
        print(f"[{n:2d} Concurrent Consumers]", flush=True)
        print(f"    Wall-Clock Duration   : {res['wall_duration_s']:8.3f} s", flush=True)
        print(f"    Process CPU Time      : {res['cpu_time_s'] * 1000.0:8.2f} ms (User + Kernel)", flush=True)
        print(f"    CPU Core Utilization  : {res['cpu_utilization_pct']:8.2f} % of single core", flush=True)
        print(f"    Total Idle Wakeups    : {res['total_wakeups']:8d} wakeups", flush=True)
        print(f"    Wakeups/sec (Total)   : {res['wakeups_per_sec']:8.1f} wakeups/s", flush=True)
        print(f"    Wakeups/sec (Per-User): {res['wakeups_per_sec_per_consumer']:8.1f} wakeups/s", flush=True)

    print(flush=True)
    print("--- 2. First-Token Latency with Randomized Phase Offsets (100 Trials each) ---", flush=True)
    for n in (1, 10, 50):
        lat = await run_latency_benchmark(n, trials=100)
        print(
            f"[{n:2d} Consumers] "
            f"Min: {lat['min_ms']:5.2f}ms | "
            f"Avg: {lat['avg_ms']:5.2f}ms | "
            f"P50: {lat['p50_ms']:5.2f}ms | "
            f"P95: {lat['p95_ms']:5.2f}ms | "
            f"P99: {lat['p99_ms']:5.2f}ms | "
            f"Max: {lat['max_ms']:5.2f}ms",
            flush=True,
        )

    print(flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
