"""
Quality Gate Runner — Story 3.3, Task 1.1

Config-driven quality check executor.
Loads gate definitions from YAML and runs checks in sequence.
Reports results to audit logger.
"""

import json
import logging
from pathlib import Path
from typing import Any

from shared.quality.checks import (  # type: ignore
    CheckStatus,
    Severity,
    fk_integrity_check,
    freshness_check,
    null_check,
    range_check,
    row_count_check,
    facteur_charge_check,
)

logger = logging.getLogger(__name__)

try:
    import yaml  # type: ignore
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class GateRunner:
    """
    Config-driven quality gate executor.

    AC #3: New checks can be added declaratively via YAML.
    """

    CHECK_DISPATCH = {
        "null_check": "_run_null_check",
        "range_check": "_run_range_check",
        "row_count": "_run_row_count_check",
        "freshness": "_run_freshness_check",
        "fk_exists": "_run_fk_check",
        "facteur_charge_range": "_run_facteur_charge_check",
    }

    def __init__(self, audit_logger: Any = None):
        self.audit = audit_logger
        self.results: list[dict] = []

    def run_from_config(
        self,
        config_path: str | Path,
        context: dict | None = None,
    ) -> list[dict]:
        """
        Run all gates defined in a YAML config file.

        AC #3: Config-driven, no code changes needed.

        Args:
            config_path: Path to quality_gates.yaml.
            context: Dict with runtime context (DataFrames, DB connections).
        """
        config_path = Path(config_path)
        if not config_path.exists():
            logger.error("Config file not found: %s", config_path)
            return []

        if HAS_YAML:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # type: ignore
        else:
            # Fallback: try JSON format
            config = json.loads(config_path.read_text(encoding="utf-8"))

        gates = config.get("gates", [])
        context = context or {}

        self.results = []
        for gate in gates:
            result = self._run_gate(gate, context)
            self.results.append(result)
            self._log_result(result, gate.get("severity", "INFO"))

        return self.results

    def run_checks(self, checks: list[dict], context: dict | None = None) -> list[dict]:
        """Run checks from a list of dicts (programmatic API)."""
        context = context or {}
        self.results = []
        for check in checks:
            result = self._run_gate(check, context)
            self.results.append(result)
            self._log_result(result, check.get("severity", "INFO"))
        return self.results

    def get_summary(self) -> dict:
        """Get summary of all check results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get("status") == CheckStatus.PASS.value)
        failed = sum(1 for r in self.results if r.get("status") == CheckStatus.FAIL.value)
        warned = sum(1 for r in self.results if r.get("status") == CheckStatus.WARN.value)

        has_critical_failure = any(
            r.get("status") == CheckStatus.FAIL.value and r.get("severity") == Severity.CRITICAL.value
            for r in self.results
        )

        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "warned": warned,
            "pipeline_should_halt": has_critical_failure,
        }

    def _run_gate(self, gate: dict, context: dict) -> dict:
        """Dispatch a single gate to its check implementation."""
        check_type = gate.get("check", "")
        handler_name = self.CHECK_DISPATCH.get(check_type)

        if not handler_name:
            return {
                "name": gate.get("name", "unknown"),
                "status": CheckStatus.FAIL.value,
                "severity": gate.get("severity", "INFO"),
                "details": {"error": f"Unknown check type: {check_type}"},
            }

        handler = getattr(self, handler_name)
        result = handler(gate, context)
        result["severity"] = gate.get("severity", "INFO")
        return result

    def _run_null_check(self, gate: dict, context: dict) -> dict:
        df = context.get(gate.get("table", ""), context.get("df"))
        if df is None:
            return {"name": gate["name"], "status": "FAIL", "details": {"error": "No DataFrame"}}
        return null_check(df, gate.get("columns", []), name=gate["name"])

    def _run_range_check(self, gate: dict, context: dict) -> dict:
        df = context.get(gate.get("table", ""), context.get("df"))
        if df is None:
            return {"name": gate["name"], "status": "FAIL", "details": {"error": "No DataFrame"}}
        return range_check(
            df, gate["column"], gate.get("min", 0), gate.get("max", 100000),
            name=gate["name"],
        )

    def _run_row_count_check(self, gate: dict, context: dict) -> dict:
        return row_count_check(
            actual=gate.get("actual", context.get("actual_count", 0)),
            expected=gate.get("expected", context.get("expected_count", 0)),
            tolerance_pct=gate.get("tolerance_pct", 5.0),
            name=gate["name"],
        )

    def _run_freshness_check(self, gate: dict, context: dict) -> dict:
        df = context.get(gate.get("table", ""), context.get("df"))
        if df is None:
            return {"name": gate["name"], "status": "FAIL", "details": {"error": "No DataFrame"}}
        return freshness_check(
            df, gate.get("time_column", "date_heure"),
            max_age_hours=gate.get("max_age_hours", 24),
            reference_time=context.get("reference_time"),
            name=gate["name"],
        )

    def _run_fk_check(self, gate: dict, context: dict) -> dict:
        conn = context.get("db")
        if conn is None:
            return {"name": gate["name"], "status": "FAIL", "details": {"error": "No DB connection"}}
        return fk_integrity_check(
            conn, gate.get("table", "FACT_ENERGY_FLOW"),
            gate.get("fk_columns", {}),
            name=gate["name"],
        )

    def _run_facteur_charge_check(self, gate: dict, context: dict) -> dict:
        conn = context.get("db")
        if conn is None:
            return {"name": gate["name"], "status": "FAIL", "details": {"error": "No DB connection"}}
        return facteur_charge_check(conn, name=gate["name"])

    def _log_result(self, result: dict, severity: str) -> None:
        """Log check result to audit logger."""
        status = result.get("status", "UNKNOWN")
        name = result.get("name", "unknown")

        if status == CheckStatus.FAIL.value:
            logger.warning("QUALITY GATE FAIL [%s] %s: %s", severity, name, result.get("details"))
            if self.audit:
                self.audit.log_failure(
                    error=f"Quality gate failed: {name}",
                    details=result,
                )
        elif status == CheckStatus.WARN.value:
            logger.info("QUALITY GATE WARN [%s] %s", severity, name)
        else:
            logger.debug("QUALITY GATE PASS [%s] %s", severity, name)
