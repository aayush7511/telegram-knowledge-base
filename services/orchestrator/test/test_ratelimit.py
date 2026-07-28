"""RateLimiter enforces at most N acquisitions per window."""
import time

from summarize import RateLimiter


def test_first_n_acquire_immediately_then_sixth_blocks():
    rl = RateLimiter(max_calls=5, window=0.5)

    start = time.monotonic()
    for _ in range(5):
        rl.acquire()
    assert time.monotonic() - start < 0.3  # first 5 are ~instant

    rl.acquire()  # 6th must wait for the window to roll over
    assert time.monotonic() - start >= 0.5
