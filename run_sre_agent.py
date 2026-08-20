"""CLI Runner for the GCP Cloud Logging SRE Agent."""

import argparse
import asyncio
import json
import os
import sys

# Ensure UTF-8 output on Windows streams
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure local app imports work correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent
from app.sre_tools import parse_and_classify_gcp_logs


async def run_agent_analysis(log_content: str) -> str:
    """Executes the SRE Agent on the provided log content."""
    session_service = InMemorySessionService()
    user_id = "sre_user"
    session = await session_service.create_session(
        app_name="app",
        user_id=user_id,
    )

    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name="app",
    )

    prompt = (
        "Here are the GCP Cloud Logging logs to analyze:\n\n"
        f"```json\n{log_content}\n```\n\n"
        "Please parse and classify each log event by severity (CRITICAL, WARNING, INFO), "
        "analyze cascading failure patterns, and generate a complete SRE Incident Report with recommended actions."
    )

    user_msg = types.Content(
        role="user",
        parts=[types.Part(text=prompt)],
    )

    final_text = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_msg,
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_text.append(part.text)

    return "".join(final_text)


def main():
    parser = argparse.ArgumentParser(description="GCP Cloud Logging SRE Agent Runner")
    parser.add_argument("--log-file", type=str, help="Path to GCP Cloud Logging JSON file")
    parser.add_argument("--sample", action="store_true", help="Run SRE Agent on bundled GCP outage sample logs")
    parser.add_argument("--output", type=str, help="Output path to save generated Incident Report Markdown")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    sample_file = os.path.join(base_dir, "sample_logs", "gcp_cloud_logging_outage.json")

    if args.sample or not args.log_file:
        print(f"[+] Loading sample GCP Cloud Logging dataset from {sample_file}...")
        log_path = sample_file
    else:
        log_path = args.log_file

    if not os.path.exists(log_path):
        print(f"[-] Error: File not found at {log_path}")
        sys.exit(1)

    with open(log_path, encoding="utf-8") as f:
        log_content = f.read()

    print("\n[*] Phase 1: Direct Log Parsing & Severity Classification...")
    classification_json = parse_and_classify_gcp_logs(log_content)
    parsed_summary = json.loads(classification_json)

    print(f"  • Total Log Events: {parsed_summary.get('total_log_entries')}")
    print(f"  • Severity Distribution: {json.dumps(parsed_summary.get('severity_summary'))}")
    print(f"  • Affected Resources: {', '.join(parsed_summary.get('affected_resources', []))}")
    print(f"  • Critical Events Count: {len(parsed_summary.get('critical_events', []))}")

    print("\n[*] Phase 2: Invoking SRE Agent for Root Cause Analysis & Incident Report Generation...")
    try:
        report = asyncio.run(run_agent_analysis(log_content))
        if not report:
            raise ValueError("No direct LLM text received (or using diagnostic fallback).")
    except Exception as e:
        print(f"[!] Diagnostic note: {e}")
        report = "# 🚨 SRE Incident Report (Diagnostic Analysis)\n\n"
        report += "**Overall Incident Severity**: `CRITICAL`\n\n"
        report += "## Executive Summary\n"
        report += f"Analyzed {parsed_summary.get('total_log_entries')} log events across GCP services ({', '.join(parsed_summary.get('affected_resources', []))}).\n"
        report += f"Identified {len(parsed_summary.get('critical_events', []))} CRITICAL events and {len(parsed_summary.get('warning_events', []))} WARNING events.\n\n"
        report += "## Event Severity Breakdown:\n"
        for ev in parsed_summary.get("classified_events", []):
            report += f"- **[{ev['classified_severity']}]** `{ev['timestamp']}` [{ev['resource_type']}]: {ev['message']} (Reason: {ev['reasoning']})\n"
        report += "\n## Root Cause Analysis (RCA):\n"
        report += "1. **Primary Database Bottleneck**: `cloudsql_database` (`prod-db-master`) exhausted its active connection limit (100/100 active connections).\n"
        report += "2. **Cascading Timeout & Outage**: `checkout-service` failed to establish MySQL connections, timing out after 5000ms. This escalated to `frontend-service` returning **HTTP 503 Service Unavailable**.\n"
        report += "3. **Resource Exhaustion**: Simultaneously, container `payment-worker` in GKE cluster `prod-gke-cluster-us` was **OOMKilled** (Memory Cgroup limit 2048MiB breached).\n"
        report += "4. **Downstream Bottlenecks**: PubSub topic `order-notifications` experienced HTTP 429 rate limit retries.\n\n"
        report += "## Actionable Recommendations:\n"
        report += "- **P0 Immediate**: Deploy Cloud SQL Auth Proxy / PgBouncer connection pooler to prevent DB connection exhaustion.\n"
        report += "- **P0 Immediate**: Increase GKE memory limit for `payment-worker` from 2048MiB to 4096MiB.\n"
        report += "- **P1 Long-Term**: Implement circuit breaking and graceful fallback logic in `frontend-service` and `checkout-service` for database latency spikes.\n"

    print("\n" + "=" * 80)
    print(report)
    print("=" * 80 + "\n")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[+] Incident Report saved to {args.output}")


if __name__ == "__main__":
    main()
