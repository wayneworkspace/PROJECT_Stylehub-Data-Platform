"""Ask Jev typed judgments about review findings; Claude writes the report.

Usage: uv run python include/scripts/jev_review.py <findings.json>
Each finding: {"id", "kind": "optimization" | "vulnerability" | "expansion", "file", "text"}.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Noul, Score, TypeSafeClient

ROOT = Path(__file__).resolve().parents[2]
IMPACT = ["no real effect", "small cleanup", "clear win in speed, cost or size", "large win"]
SEVERITY = ["cosmetic", "low: minor exposure", "medium: data or access exposure", "high: takeover"]
VALUE = ["little value", "useful for one team", "clear business value", "high business value"]


def questions_for(findings: list[dict]) -> dict[str, Noul | Score]:
    """One or two judgments per finding; ids are finding id plus judgment name."""
    questions: dict[str, Noul | Score] = {}
    for f in findings:
        ref = f"the finding with id `{f['id']}` in `findings`"
        match f["kind"]:
            case "optimization":
                questions[f"{f['id']}.impact"] = Score(
                    instructions=f"How much does applying {ref} improve the code?", criteria=IMPACT
                )
            case "vulnerability":
                questions[f"{f['id']}.exploitable"] = Noul(
                    instructions=f"Can an attacker realistically exploit {ref} in this setup?"
                )
                questions[f"{f['id']}.severity"] = Score(
                    instructions=f"How severe is {ref} if exploited?", criteria=SEVERITY
                )
            case "expansion":
                questions[f"{f['id']}.value"] = Score(
                    instructions=f"How much business value does {ref} add?", criteria=VALUE
                )
    return questions


def main() -> None:
    findings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    load_dotenv(ROOT / "secrets" / ".env")
    # The user's TypeSafe key lives in secrets/.env as AI_GATEWAY_API_KEY.
    with TypeSafeClient(api_key=os.environ["AI_GATEWAY_API_KEY"]) as client:
        response = client.system_one(
            state={"project": "StyleHub daily ELT on GCP", "findings": findings},
            questions=questions_for(findings),
        )
    answers = {qid: round(a.noul, 2) for qid, a in response.nouls.items()}
    answers |= {
        qid: {"score": round(a.score / (len(a.legend) - 1), 2), "conf": round(a.confidence, 2)}
        for qid, a in response.scores.items()
    }
    json.dump(answers, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
