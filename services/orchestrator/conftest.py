"""Put the orchestrator package dir on sys.path so tests can `import main` etc.

The service is a flat module set (no package), matching how it runs under
uvicorn from its own directory.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
