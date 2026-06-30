import multiprocessing

# gevent workers: non-blocking I/O — while one connection waits for the device
# to finish sending its body, the worker serves other connections.
# This is the core fix for WORKER TIMEOUT on /api/heartbeats/ caused by slow
# or concurrent device TCP connections exhausting all 4 sync workers at once.
#
# Requires:  pip install gevent
worker_class       = "gevent"
worker_connections = 1000   # concurrent connections per worker

# 1 worker per CPU core is correct for gevent (it's not sync, so more workers
# don't help and just waste RAM).
workers = multiprocessing.cpu_count()

# Fallback if gevent is not available: switch to gthread (no extra packages needed).
# Change the two lines above to:
#   worker_class = "gthread"
#   threads      = 4
# and keep workers = multiprocessing.cpu_count()

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout         = 120   # seconds before killing a stuck worker
graceful_timeout = 30
keepalive        = 5

# ── Bind / logging ───────────────────────────────────────────────────────────
bind      = "0.0.0.0:8000"
accesslog = "-"
errorlog  = "-"
loglevel  = "warning"

proc_name = "afdd-gunicorn"
