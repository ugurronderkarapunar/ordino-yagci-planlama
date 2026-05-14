"""
QA raporu: pytest junit çıktısını ve statik kontrolleri Excel'e yazar.
Çalıştır: python scripts/qa_report_excel.py
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def _parse_junit(path: Path) -> list[dict]:
    if not path.is_file():
        return [{"testcase": "(junit yok)", "status": "SKIP", "message": str(path)}]
    tree = ET.parse(path)
    root = tree.getroot()
    rows: list[dict] = []
    for case in root.iter("testcase"):
        name = case.attrib.get("name", "")
        classname = case.attrib.get("classname", "")
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            status, msg = "FAIL", (failure.text or failure.attrib.get("message", ""))[:500]
        elif error is not None:
            status, msg = "ERROR", (error.text or error.attrib.get("message", ""))[:500]
        elif skipped is not None:
            status, msg = "SKIP", skipped.attrib.get("message", "")
        else:
            status, msg = "PASS", ""
        rows.append(
            {
                "suite": classname,
                "testcase": name,
                "status": status,
                "message": msg,
            }
        )
    return rows or [{"testcase": "(boş junit)", "status": "?", "message": ""}]


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    junit = REPORTS / "junit.xml"
    cmd = [sys.executable, "-m", "pytest", str(ROOT / "tests"), f"--junitxml={junit}", "-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    rows = _parse_junit(junit)
    meta = pd.DataFrame(
        [
            {"alan": "zaman", "deger": datetime.now().isoformat()},
            {"alan": "pytest_exit_code", "deger": proc.returncode},
            {"alan": "pytest_stdout_ozet", "deger": (proc.stdout or "")[:2000]},
        ]
    )
    df = pd.DataFrame(rows)
    out_xlsx = REPORTS / "ordino_qa_raporu.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
        meta.to_excel(w, sheet_name="ozet", index=False)
        df.to_excel(w, sheet_name="test_sonuclari", index=False)
    print(f"Yazildi: {out_xlsx}")
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
