#!/usr/bin/env bash
# Safe pytest runner — prevents memory blowup and runaway tests
# Usage: ./safe-test.sh [pytest-args...]
#
# macOS notes:
#   ulimit -m (RSS) is NOT supported on macOS — it accepts the flag but
#   silently ignores it.  We use ulimit -v (address space) instead, which
#   the kernel does enforce.

set -euo pipefail
cd "$(dirname "$0")"

export EXPORT_SYNC=1
export DEV_AUTO_TICK=0

# Address space limit in KB (14 GB = 14680064 KB, macOS pages 4KB).
# Leaves ~4GB for the system on a 16-24GB M4 Mac, preventing swap thrashing.
MAX_VMEM_KB=$((14 * 1024 * 1024))

# Timeout per pytest invocation (seconds)
TIMEOUT=600

echo "=== safe-test.sh ==="
echo "  max vmem:  $((MAX_VMEM_KB / 1024))MB"
echo "  timeout:   ${TIMEOUT}s"
echo "  args:      $*"
echo ""

# Enforce virtual-memory limit on macOS
ulimit -v "$MAX_VMEM_KB" 2>/dev/null && \
  echo "  ulimit -v $MAX_VMEM_KB KB  (OK)" || \
  echo "  [warn] ulimit -v not available"

# Run pytest with memory-safe defaults
# --tb=short / -p no:cacheprovider are in pyproject.toml addopts
exec timeout "$TIMEOUT" uv run python -m pytest "$@"
