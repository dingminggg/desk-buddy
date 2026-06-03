import os

# Ensure Qt uses the offscreen platform during tests (no display needed).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
