"""Put the worker dir on sys.path so tests can `import app` (flat module, run by uvicorn from here)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
