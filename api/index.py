import os
import sys
from pathlib import Path

# Add project root to sys.path so 'app' package is discoverable by Vercel's Python runtime
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import the FastAPI application
from app.interfaces.main import app

# Expose app for ASGI/WSGI servers (e.g. Vercel Python runtime)
app = app
