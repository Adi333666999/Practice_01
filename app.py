import os
import shutil
import time
from datetime import datetime, timezone
import psutil
from flask import Flask, jsonify, request

app = Flask(__name__)

# Configurable thresholds via environment variables (default: 90.0%)
CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "90.0"))
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", "90.0"))
DISK_THRESHOLD = float(os.getenv("DISK_THRESHOLD", "90.0"))
DISK_PATH = os.getenv("DISK_PATH", "/")

# Simulated failure flag for testing UNHEALTHY state in Kubernetes/CI
SIMULATE_FAILURE = os.getenv("SIMULATE_FAILURE", "false").lower() == "true"
START_TIME = time.time()


def check_application_health():
    """
    Checks internal application dependencies or simulated failure state.
    Returns (is_healthy: bool, error_message: str | None)
    """
    if SIMULATE_FAILURE or request.args.get("fail", "false").lower() == "true":
        return False, "Simulated critical application failure"
    return True, None


def get_system_metrics():
    """Collects CPU, Memory, and Disk utilization percentages."""
    cpu_percent = psutil.cpu_percent(interval=0.2)
    memory_percent = psutil.virtual_memory().percent
    total, used, _ = shutil.disk_usage(DISK_PATH)
    disk_percent = round((used / total) * 100, 2)

    return {
        "cpu_percent": round(cpu_percent, 2),
        "memory_percent": round(memory_percent, 2),
        "disk_percent": disk_percent,
    }


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "healthcheck-api",
        "endpoints": ["/health"]
    }), 200


@app.route("/health", methods=["GET"])
def health_check():
    timestamp = datetime.now(timezone.utc).isoformat()
    uptime_seconds = round(time.time() - START_TIME, 2)

    try:
        # 1. Priority 1: Check for application failure -> UNHEALTHY (503)
        app_ok, error_msg = check_application_health()
        if not app_ok:
            return jsonify({
                "status": "UNHEALTHY",
                "timestamp": timestamp,
                "uptime_seconds": uptime_seconds,
                "error": error_msg
            }), 503

        # 2. Collect system metrics
        metrics = get_system_metrics()
        warnings = []

        # Rule: >= 90.0% triggers DEGRADED
        if metrics["cpu_percent"] >= CPU_THRESHOLD:
            warnings.append(
                f"CPU usage ({metrics['cpu_percent']}%) reached/exceeded threshold ({CPU_THRESHOLD}%)"
            )
        if metrics["memory_percent"] >= MEMORY_THRESHOLD:
            warnings.append(
                f"Memory usage ({metrics['memory_percent']}%) reached/exceeded threshold ({MEMORY_THRESHOLD}%)"
            )
        if metrics["disk_percent"] >= DISK_THRESHOLD:
            warnings.append(
                f"Disk usage ({metrics['disk_percent']}%) reached/exceeded threshold ({DISK_THRESHOLD}%)"
            )

        # 3. Priority 2: Check resource thresholds -> DEGRADED (200)
        if warnings:
            return jsonify({
                "status": "DEGRADED",
                "timestamp": timestamp,
                "uptime_seconds": uptime_seconds,
                "thresholds": {
                    "cpu_percent": CPU_THRESHOLD,
                    "memory_percent": MEMORY_THRESHOLD,
                    "disk_percent": DISK_THRESHOLD,
                },
                "metrics": metrics,
                "warnings": warnings,
            }), 200

        # 4. Priority 3: Normal operation -> HEALTHY (200)
        return jsonify({
            "status": "HEALTHY",
            "timestamp": timestamp,
            "uptime_seconds": uptime_seconds,
            "thresholds": {
                "cpu_percent": CPU_THRESHOLD,
                "memory_percent": MEMORY_THRESHOLD,
                "disk_percent": DISK_THRESHOLD,
            },
            "metrics": metrics,
            "warnings": [],
        }), 200

    except Exception as exc:
        # Catch-all for unexpected runtime exceptions -> UNHEALTHY (503)
        return jsonify({
            "status": "UNHEALTHY",
            "timestamp": timestamp,
            "uptime_seconds": uptime_seconds,
            "error": f"Internal health check failure: {str(exc)}"
        }), 503


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
