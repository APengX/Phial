"""Uniform JSON response helpers: {"success": bool, "data"|"error": ...}."""

from flask import jsonify


def ok(data=None, status: int = 200):
    return jsonify({"success": True, "data": data}), status


def fail(message: str, status: int = 400, **extra):
    body = {"success": False, "error": message}
    if extra:
        body.update(extra)
    return jsonify(body), status
