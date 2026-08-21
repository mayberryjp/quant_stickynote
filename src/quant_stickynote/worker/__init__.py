"""Worker daemon entry point for supervisord.

Usage:
    python -m quant_stickynote.worker
"""
from worker import get_worker

if __name__ == "__main__":
    worker = get_worker()
    worker.run()
