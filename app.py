"""practice-app: a small web app for practising Docker, Kubernetes and Jenkins.

Every value shown on the page comes from somewhere you can change:
  APP_VERSION          -> set by Jenkins (the build number)
  APP_MESSAGE/APP_COLOR/APP_ENV -> the ConfigMap (k8s/configmap.yaml)
  POD_NAME/NODE_NAME/POD_IP     -> Kubernetes itself (Downward API)
"""
import os
import platform
import re
import socket
import threading
import time

from flask import Flask, jsonify, render_template

app = Flask(__name__)

START_TIME = time.time()
_lock = threading.Lock()
_requests_served = 0

DEFAULT_COLOR = "#0f766e"
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def safe_color(value):
    """Only accept #RRGGBB so a bad ConfigMap value can't break the page."""
    return value if value and _HEX_COLOR.match(value) else DEFAULT_COLOR


def get_info():
    return {
        "app": "practice-app",
        "version": os.getenv("APP_VERSION", "dev"),
        "message": os.getenv("APP_MESSAGE", "Hello from practice-app!"),
        "color": safe_color(os.getenv("APP_COLOR")),
        "environment": os.getenv("APP_ENV", "local"),
        "pod": os.getenv("POD_NAME", socket.gethostname()),
        "node": os.getenv("NODE_NAME", "not in Kubernetes"),
        "pod_ip": os.getenv("POD_IP", "n/a"),
        "python": platform.python_version(),
        "uptime_seconds": int(time.time() - START_TIME),
        "requests_served": _requests_served,
    }


def count_request():
    global _requests_served
    with _lock:
        _requests_served += 1


@app.route("/")
def index():
    count_request()
    return render_template("index.html", info=get_info())


@app.route("/api/info")
def api_info():
    count_request()
    return jsonify(get_info())


@app.route("/healthz")
def healthz():
    """Liveness probe: is the process alive?"""
    return jsonify(status="ok")


@app.route("/readyz")
def readyz():
    """Readiness probe: can this pod take traffic?"""
    return jsonify(status="ready")


if __name__ == "__main__":
    # Local run only. In the container, gunicorn serves the app.
    app.run(host="0.0.0.0", port=8000)
