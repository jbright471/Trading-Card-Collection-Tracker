"""Entry point — kept for compatibility with the existing cron job.

The actual logic lives in the `tcg/` package.
"""
from tcg.main import run

if __name__ == '__main__':
    run()
