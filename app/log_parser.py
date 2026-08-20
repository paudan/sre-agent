"""GCP Cloud Logging Parser and Severity Classifier."""

import json
import os
from typing import Any


def parse_gcp_logs(log_input: str | list | dict) -> list[dict[str, Any]]:
    """Ingests raw GCP Cloud Logging data and normalizes entries.

    Accepts:
    - File path pointing to JSON or JSONL file
    - JSON string payload (array of LogEntries or single LogEntry)
    - Multiline text logs
    - Direct Python list or dict

    Returns a list of standardized dictionary records.
    """
    entries = []

    if isinstance(log_input, list):
        raw_items = log_input
    elif isinstance(log_input, dict):
        raw_items = [log_input]
    elif isinstance(log_input, str):
        cleaned_input = log_input.strip()
        # Check if log_input is a valid file path
        if os.path.exists(cleaned_input) and os.path.isfile(cleaned_input):
            with open(cleaned_input, encoding="utf-8") as f:
                content = f.read().strip()
                try:
                    parsed = json.loads(content)
                    raw_items = parsed if isinstance(parsed, list) else [parsed]
                except json.JSONDecodeError:
                    # Treat file lines as JSONL or text
                    raw_items = _parse_multiline_text(content)
        else:
            # Try to parse string as JSON
            try:
                parsed = json.loads(cleaned_input)
                raw_items = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                raw_items = _parse_multiline_text(cleaned_input)
    else:
        raw_items = []

    for item in raw_items:
        if isinstance(item, dict):
            entries.append(_normalize_log_entry(item))
        elif isinstance(item, str) and item.strip():
            entries.append({
                "timestamp": "UNKNOWN",
                "severity_gcp": "DEFAULT",
                "resource_type": "unknown",
                "resource_labels": {},
                "message": item.strip(),
                "http_status": None,
                "trace": None,
                "raw_entry": item,
            })

    return entries


def _parse_multiline_text(text: str) -> list[dict[str, Any]]:
    """Fallback parser for JSONL or plain text log lines."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                items.append(parsed)
            else:
                items.append({"message": line})
        except json.JSONDecodeError:
            items.append({"message": line})
    return items


def _normalize_log_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Extracts common GCP LogEntry attributes into a standard structure."""
    timestamp = entry.get("timestamp", entry.get("receiveTimestamp", "UNKNOWN"))
    severity_gcp = entry.get("severity", "DEFAULT").upper()

    resource = entry.get("resource", {})
    resource_type = resource.get("type", "unknown_resource") if isinstance(resource, dict) else "unknown_resource"
    resource_labels = resource.get("labels", {}) if isinstance(resource, dict) else {}

    # Payload extraction
    text_payload = entry.get("textPayload")
    json_payload = entry.get("jsonPayload")
    proto_payload = entry.get("protoPayload")

    message_parts = []
    if text_payload:
        message_parts.append(str(text_payload))
    if json_payload and isinstance(json_payload, dict):
        msg = json_payload.get("message") or json_payload.get("event") or json_payload.get("reason")
        if msg:
            message_parts.append(str(msg))
        else:
            message_parts.append(json.dumps(json_payload))
    if proto_payload and isinstance(proto_payload, dict):
        message_parts.append(json.dumps(proto_payload))

    full_message = " | ".join(message_parts) if message_parts else json.dumps(entry)

    # HTTP Request data
    http_req = entry.get("httpRequest", {})
    http_status = http_req.get("status") if isinstance(http_req, dict) else None

    trace = entry.get("trace")

    return {
        "insertId": entry.get("insertId"),
        "timestamp": timestamp,
        "severity_gcp": severity_gcp,
        "resource_type": resource_type,
        "resource_labels": resource_labels,
        "message": full_message,
        "http_status": http_status,
        "trace": trace,
        "raw_entry": entry,
    }


def classify_log_event(entry: dict[str, Any]) -> dict[str, Any]:
    """Classifies a normalized GCP log entry into CRITICAL, WARNING, or INFO severity.

    Also determines severity reasoning and root cause tags.
    """
    gcp_severity = entry.get("severity_gcp", "DEFAULT")
    message = entry.get("message", "").lower()
    http_status = entry.get("http_status")
    resource_type = entry.get("resource_type", "")

    # Define high-impact critical keywords
    critical_keywords = [
        "oomkilled",
        "memory cgroup limit exceeded",
        "connection_pool_exhausted",
        "too many connections",
        "fatal",
        "panic",
        "uncaught exception",
        "deadlock",
        "out of memory",
        "system crash",
        "service unavailable",
    ]

    warning_keywords = [
        "connection_pool_warning",
        "retry",
        "rate limit",
        "quota_warning",
        "deprecated",
        "latency spike",
        "429 too many requests",
        "timeout",
    ]

    classified_severity = "INFO"
    reasoning = []
    category = "general_operation"

    # 1. Evaluate Critical conditions
    if (
        gcp_severity in ["CRITICAL", "FATAL", "EMERGENCY", "ALERT"]
        or (http_status and http_status in [500, 502, 503, 504])
        or any(kw in message for kw in critical_keywords)
    ):
        classified_severity = "CRITICAL"
        category = "system_failure"

        if http_status in [500, 502, 503, 504]:
            reasoning.append(f"HTTP Status {http_status} (Server Error)")
        if gcp_severity in ["CRITICAL", "FATAL", "EMERGENCY", "ALERT"]:
            reasoning.append(f"Native GCP Severity: {gcp_severity}")
        for kw in critical_keywords:
            if kw in message:
                reasoning.append(f"Critical error keyword detected: '{kw}'")
                category = _map_keyword_category(kw)

    # 2. Evaluate Warning conditions
    elif (
        gcp_severity in ["WARNING", "WARN", "ERROR"]
        or (http_status and (400 <= http_status < 500))
        or any(kw in message for kw in warning_keywords)
    ):
        classified_severity = "WARNING"
        category = "degraded_performance"

        if gcp_severity in ["WARNING", "WARN", "ERROR"]:
            reasoning.append(f"Native GCP Severity: {gcp_severity}")
        if http_status and 400 <= http_status < 500:
            reasoning.append(f"HTTP Status {http_status} (Client Error/Rate Limit)")
        for kw in warning_keywords:
            if kw in message:
                reasoning.append(f"Warning keyword detected: '{kw}'")

    # 3. Info condition
    else:
        classified_severity = "INFO"
        reasoning.append(f"Routine log line with severity {gcp_severity}")

    return {
        "timestamp": entry.get("timestamp"),
        "resource_type": resource_type,
        "resource_labels": entry.get("resource_labels", {}),
        "classified_severity": classified_severity,
        "gcp_severity": gcp_severity,
        "category": category,
        "reasoning": "; ".join(reasoning),
        "message": entry.get("message"),
        "http_status": http_status,
        "trace": entry.get("trace"),
    }


def _map_keyword_category(keyword: str) -> str:
    if "oom" in keyword or "memory" in keyword:
        return "resource_exhaustion_oom"
    if "connection" in keyword or "db" in keyword or "mysql" in keyword:
        return "database_connection_exhaustion"
    if "panic" in keyword or "exception" in keyword:
        return "application_crash"
    return "service_outage"
