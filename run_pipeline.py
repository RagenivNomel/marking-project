"""Batch and Phase 1 CLI with deterministic visual rerendering."""
import argparse
import json
import sys
from pathlib import Path
from app import Pipeline
from excel.workbook import read_roster
from excel.legacy_reference import read_legacy_reference
from grading.mock_grader import MockGrader
from grading.schemas import ROOT, Identity
from scanning.intake import apply_identity_decisions, read_existing_split
from workflow.storage import read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    mock = sub.add_parser("mock", help="Run or resume one fake student")
    mock.add_argument("--input", type=Path, default=ROOT / "examples" / "mock_student.json")
    mock.add_argument("--batch", default="demo")
    mock.add_argument("--failure", choices=["invalid-rating", "long-comment"])
    render = sub.add_parser("rerender", help="Reread approved Excel values without grading")
    render.add_argument("--input", type=Path, default=ROOT / "examples" / "mock_student.json")
    render.add_argument("--batch", default="demo")
    roster = sub.add_parser("roster", help="Read the teacher workbook's roster without modifying it")
    roster.add_argument("workbook", type=Path)
    roster.add_argument("--sheet", default="作文诊断输入")
    intake = sub.add_parser("intake", help="Inventory an existing split pile and attach reviewed roster candidates; no grading")
    intake.add_argument("--pile", type=Path, required=True)
    intake.add_argument("--workbook", type=Path, required=True)
    intake.add_argument("--decisions", type=Path, required=True)
    intake.add_argument("--out", type=Path)
    real_batch = sub.add_parser("real-batch", help="Run confirmed intake records through the isolated real grader")
    real_batch.add_argument("--pile", type=Path, required=True)
    real_batch.add_argument("--workbook", type=Path, required=True)
    real_batch.add_argument("--decisions", type=Path, required=True)
    real_batch.add_argument("--limit", type=int, default=None)
    real_batch.add_argument("--essay-question", default=None)
    real_batch.add_argument("--model-profile", default=None, help="Configured profile, e.g. sol_medium or luna_xhigh")
    real_batch.add_argument("--batch", default="real")
    args = parser.parse_args(argv)
    try:
        if args.command == "roster":
            result = [identity.to_dict() for identity in read_roster(args.workbook, args.sheet)]
        elif args.command == "intake":
            records = apply_identity_decisions(
                read_existing_split(args.pile),
                read_roster(args.workbook, "作文诊断输入"),
                read_json(args.decisions),
            )
            strong_identities = [Identity.from_dict({
                "student_id": item["student_id"], "student_name": item["student_name"],
                "class_name": item["class_name"],
            }) for item in records if item["match_status"] == "STRONG_ROSTER_MATCH"]
            result = {
                "mode": "EXISTING_SPLIT_INTAKE_ONLY",
                "grading_performed": False,
                "source_pile": str(args.pile),
                "source_workbook": str(args.workbook),
                "records": records,
                "historical_reference": read_legacy_reference(args.workbook, strong_identities),
            }
            if args.out:
                from workflow.storage import atomic_json
                atomic_json(args.out, result)
        elif args.command == "real-batch":
            records = apply_identity_decisions(
                read_existing_split(args.pile),
                read_roster(args.workbook, "作文诊断输入"),
                read_json(args.decisions),
            )
            confirmed = [item for item in records if item["match_status"] == "STRONG_ROSTER_MATCH"]
            pipeline = Pipeline(args.project_dir, args.batch, allow_real=True)
            result = pipeline.run_real_batch(
                confirmed,
                args.pile,
                limit=args.limit,
                essay_question=args.essay_question,
                model_profile=args.model_profile,
            )
        else:
            source = read_json(args.input)
            factory = lambda: MockGrader(getattr(args, "failure", None))
            pipeline = Pipeline(args.project_dir, args.batch, grader_factory=factory)
            if args.command == "mock":
                result = pipeline.run_mock(source)
            else:
                result = {"render": str(pipeline.rerender(Identity.from_dict(source["identity"])))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
