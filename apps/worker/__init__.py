"""APScheduler process: the maintenance jobs that must run exactly once.

Separate from ``apps/api`` on purpose. The API runs several uvicorn workers;
a scheduler inside it would run every job once per worker (W0 risk R3).
"""
