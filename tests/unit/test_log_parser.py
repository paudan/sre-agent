"""Unit tests for GCP Log Parser and Severity Classifier."""

import json

from app.log_parser import classify_log_event
from app.sre_tools import parse_and_classify_gcp_logs


def test_parse_and_classify_gcp_logs():
    sample_logs = [
        {
            "insertId": "1",
            "timestamp": "2026-08-20T10:00:00Z",
            "severity": "INFO",
            "textPayload": "Server started successfully",
            "resource": {"type": "cloud_run_revision"},
        },
        {
            "insertId": "2",
            "timestamp": "2026-08-20T10:01:00Z",
            "severity": "WARNING",
            "jsonPayload": {"event": "quota_warning", "message": "Approaching rate limit: 429 Too Many Requests"},
            "resource": {"type": "pubsub_topic"},
        },
        {
            "insertId": "3",
            "timestamp": "2026-08-20T10:02:00Z",
            "severity": "ERROR",
            "jsonPayload": {"reason": "OOMKilled", "message": "Container killed due to Memory Cgroup Limit Exceeded"},
            "resource": {"type": "k8s_container"},
        },
        {
            "insertId": "4",
            "timestamp": "2026-08-20T10:03:00Z",
            "severity": "ERROR",
            "httpRequest": {"status": 503, "requestUrl": "/checkout"},
            "textPayload": "HTTP 503 Service Unavailable",
            "resource": {"type": "cloud_run_revision"},
        },
    ]

    log_json = json.dumps(sample_logs)
    result_str = parse_and_classify_gcp_logs(log_json)
    result = json.loads(result_str)

    assert result["total_log_entries"] == 4
    assert result["severity_summary"]["CRITICAL"] == 2  # OOMKilled and HTTP 503
    assert result["severity_summary"]["WARNING"] == 1   # 429 Rate limit
    assert result["severity_summary"]["INFO"] == 1      # Server started


def test_classify_log_event_critical_oom():
    entry = {
        "timestamp": "2026-08-20T10:02:00Z",
        "severity_gcp": "ERROR",
        "resource_type": "k8s_container",
        "message": "Container killed due to Memory Cgroup Limit Exceeded (OOMKilled)",
        "http_status": None,
    }
    classified = classify_log_event(entry)
    assert classified["classified_severity"] == "CRITICAL"
    assert classified["category"] == "resource_exhaustion_oom"
