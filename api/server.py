import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from llm_layer.pipeline import (
    diagnose,
    review_diagnosis,
    get_session_state,
    CASES,
)


# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

EVALUATION_DIR = BASE_DIR / "evaluation"

AI_RESULTS_FILE = (
    EVALUATION_DIR / "ai_results.csv"
)

EVALUATION_RESULTS_FILE = (
    EVALUATION_DIR / "evaluation_results.csv"
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="NetSage AI",
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class DiagnoseRequest(BaseModel):

    session_id: str | None = None

    case_id: str | None = None

    symptom: str = Field(
        ...,
        min_length=1,
    )

    evidence: str = Field(
        ...,
        min_length=1,
    )


class ReviewRequest(BaseModel):

    session_id: str = Field(
        ...,
        min_length=1,
    )

    decision: str

    correction: dict[str, Any] | None = None

    reason: str | None = None


class EvaluationResultRequest(BaseModel):

    case_id: str = Field(
        ...,
        min_length=1,
    )

    evaluation: str = Field(
        ...,
        min_length=1,
    )

    reviewer_notes: str = ""


# ============================================================
# CSV HELPERS
# ============================================================

AI_RESULT_HEADERS = [
    "case_id",
    "category",
    "ai_root_cause",
    "ai_osi_layer",
    "ai_severity",
    "ai_confidence",
    "ai_fix",
    "ai_evidence",
    "generated_at",
]


EVALUATION_HEADERS = [
    "case_id",
    "evaluation",
    "reviewer_notes",
    "evaluated_at",
]


def ensure_evaluation_directory():
    """
    Make sure the evaluation directory exists.
    """

    EVALUATION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def read_ai_results():
    """
    Read all valid AI results from ai_results.csv.

    Returns:
        dict[case_id, row]
    """

    results = {}

    if not AI_RESULTS_FILE.exists():
        return results

    try:

        with open(
            AI_RESULTS_FILE,
            "r",
            encoding="utf-8",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                case_id = (
                    row.get("case_id", "")
                    or ""
                ).strip()

                # Ignore malformed rows with no case ID.
                if not case_id:
                    continue

                results[case_id] = row

    except Exception as exc:

        print(
            f"ERROR reading AI results: {exc}"
        )

    return results


def write_ai_results(results):
    """
    Rewrite ai_results.csv using one row per case.
    """

    ensure_evaluation_directory()

    with open(
        AI_RESULTS_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=AI_RESULT_HEADERS,
        )

        writer.writeheader()

        for case_id, row in results.items():

            clean_row = {
                header: row.get(
                    header,
                    "",
                )
                for header in AI_RESULT_HEADERS
            }

            clean_row["case_id"] = case_id

            writer.writerow(clean_row)


def save_ai_result(
    case_id: str,
    diagnosis: dict,
):
    """
    Save/update the AI diagnosis for a benchmark case.

    This is the important connection between the diagnosis
    pipeline and the evaluation system.
    """

    if not case_id:
        raise ValueError(
            "case_id is required to save an AI result."
        )

    ensure_evaluation_directory()

    results = read_ai_results()

    case = CASES.get(
        case_id,
        {},
    )

    evidence = diagnosis.get(
        "evidence",
        [],
    )

    if isinstance(evidence, list):

        evidence_text = " | ".join(
            str(item)
            for item in evidence
        )

    else:

        evidence_text = str(
            evidence or ""
        )

    fix_steps = diagnosis.get(
        "fix_steps",
        [],
    )

    if isinstance(fix_steps, list):

        fix_text = " | ".join(
            str(item)
            for item in fix_steps
        )

    else:

        fix_text = str(
            fix_steps or ""
        )

    results[case_id] = {

        "case_id":
            case_id,

        "category":
            case.get(
                "category",
                "",
            ),

        "ai_root_cause":
            diagnosis.get(
                "root_cause",
                "",
            ),

        "ai_osi_layer":
            diagnosis.get(
                "osi_layer",
                "",
            ),

        "ai_severity":
            diagnosis.get(
                "severity",
                "",
            ),

        "ai_confidence":
            diagnosis.get(
                "confidence",
                "",
            ),

        "ai_fix":
            fix_text,

        "ai_evidence":
            evidence_text,

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    write_ai_results(
        results
    )

    print(
        f"[NetSage] AI result saved: "
        f"{case_id} -> {AI_RESULTS_FILE}"
    )

    return results[case_id]


def read_evaluation_results():
    """
    Read human evaluation results.

    Returns:
        dict[case_id, row]
    """

    results = {}

    if not EVALUATION_RESULTS_FILE.exists():
        return results

    try:

        with open(
            EVALUATION_RESULTS_FILE,
            "r",
            encoding="utf-8",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                case_id = (
                    row.get(
                        "case_id",
                        "",
                    )
                    or ""
                ).strip()

                if not case_id:
                    continue

                results[case_id] = row

    except Exception as exc:

        print(
            f"ERROR reading evaluation results: {exc}"
        )

    return results


def write_evaluation_results(
    results
):
    """
    Rewrite evaluation_results.csv.
    """

    ensure_evaluation_directory()

    with open(
        EVALUATION_RESULTS_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=EVALUATION_HEADERS,
        )

        writer.writeheader()

        for case_id, row in results.items():

            clean_row = {
                header: row.get(
                    header,
                    "",
                )
                for header in EVALUATION_HEADERS
            }

            clean_row["case_id"] = case_id

            writer.writerow(
                clean_row
            )


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "netsage-ai",
    }


# ============================================================
# DIAGNOSIS
# ============================================================

@app.post("/diagnose")
def diagnose_endpoint(
    request: DiagnoseRequest
):

    session_id = (
        request.session_id
        or str(uuid4())
    )

    case_id = (
        request.case_id
        or ""
    ).strip()

    # --------------------------------------------------------
    # Case ID is required for benchmark/evaluation mode.
    # --------------------------------------------------------

    if not case_id:

        raise HTTPException(
            status_code=400,
            detail=(
                "case_id is required. "
                "Example: V1_01."
            ),
        )

    # --------------------------------------------------------
    # Make sure the supplied case exists.
    # --------------------------------------------------------

    if case_id not in CASES:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown case_id: {case_id}"
            ),
        )

    try:

        result = diagnose(

            symptom=request.symptom,

            raw_evidence=request.evidence,

            session_id=session_id,

            case_id=case_id,
        )

        # ----------------------------------------------------
        # Always attach identifiers to response.
        # ----------------------------------------------------

        result["session_id"] = session_id

        result["case_id"] = case_id

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Save the AI diagnosis ONLY when the AI has actually
        # produced a diagnosis.
        #
        # Do NOT save "needs_more_evidence" as an AI result.
        # ----------------------------------------------------

        status = result.get(
            "status",
            "",
        )

        diagnosis = result.get(
            "diagnosis"
        )

        if (
            status == "needs_human_review"
            and isinstance(
                diagnosis,
                dict,
            )
        ):

            save_ai_result(
                case_id=case_id,
                diagnosis=diagnosis,
            )

        elif (
            status in {
                "completed",
                "diagnosed",
                "approved",
                "edited",
            }
            and isinstance(
                result.get(
                    "final_diagnosis"
                ),
                dict,
            )
        ):

            save_ai_result(
                case_id=case_id,
                diagnosis=result[
                    "final_diagnosis"
                ],
            )

        return result

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:

        print(
            "DIAGNOSIS ERROR:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Diagnosis failed: {exc}"
            ),
        )


# ============================================================
# HUMAN REVIEW
# ============================================================

@app.post("/review")
def review_endpoint(
    request: ReviewRequest
):

    try:

        result = review_diagnosis(

            session_id=
                request.session_id,

            decision=
                request.decision,

            correction=
                request.correction,

            reason=
                request.reason,
        )

        # ----------------------------------------------------
        # Preserve identifiers from the session/result.
        # ----------------------------------------------------

        result["session_id"] = (
            request.session_id
        )

        # ----------------------------------------------------
        # Determine case ID.
        # ----------------------------------------------------

        case_id = (
            result.get("case_id")
            or ""
        ).strip()

        if not case_id:

            try:

                session_state = (
                    get_session_state(
                        request.session_id
                    )
                )

                case_id = (
                    session_state.get(
                        "case_id",
                        "",
                    )
                    or ""
                ).strip()

            except Exception:
                pass

        if case_id:

            result["case_id"] = case_id

        # ----------------------------------------------------
        # Save the FINAL diagnosis after human review.
        #
        # This means:
        #
        # approve -> save AI diagnosis
        # edit    -> save human-edited diagnosis
        # reject  -> don't save as a final AI result
        # ----------------------------------------------------

        decision = (
            request.decision
            .strip()
            .lower()
        )

        if decision in {
            "approve",
            "approved",
        }:

            diagnosis = (
                result.get(
                    "final_diagnosis"
                )
                or result.get(
                    "diagnosis"
                )
            )

            if (
                case_id
                and isinstance(
                    diagnosis,
                    dict,
                )
            ):

                save_ai_result(
                    case_id,
                    diagnosis,
                )

        elif decision in {
            "edit",
            "edited",
        }:

            diagnosis = (
                result.get(
                    "final_diagnosis"
                )
            )

            if (
                case_id
                and isinstance(
                    diagnosis,
                    dict,
                )
            ):

                save_ai_result(
                    case_id,
                    diagnosis,
                )

        return result

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception as exc:

        print(
            "REVIEW ERROR:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Review failed: {exc}"
            ),
        )


# ============================================================
# SESSION
# ============================================================

@app.get(
    "/session/{session_id}"
)
def session_endpoint(
    session_id: str
):

    try:

        return get_session_state(
            session_id
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


# ============================================================
# EVALUATION — AI GENERATED CASES
# ============================================================

@app.get("/evaluation/cases")
def evaluation_cases():
    """
    Return all benchmark cases for which an AI diagnosis
    exists in evaluation/ai_results.csv.

    The response deliberately provides both:
        - nested fields
        - flat compatibility fields

    This prevents frontend breakage if an older evaluation.js
    version is being served by the browser.
    """

    ai_results = read_ai_results()

    evaluation_results = read_evaluation_results()

    cases = []

    for case_id, ai_row in ai_results.items():

        ground_truth = CASES.get(
            case_id,
            {},
        )

        # --------------------------------------------------------
        # Ground truth
        # --------------------------------------------------------

        expected_fault = (
            ground_truth.get(
                "expected_fault",
                "",
            )
            or ""
        )

        osi_layer = (
            ground_truth.get(
                "osi_layer",
                "",
            )
            or ""
        )

        concept = (
            ground_truth.get(
                "concept",
                "",
            )
            or ""
        )

        severity = (
            ground_truth.get(
                "severity",
                "",
            )
            or ""
        )

        expected_fix = (
            ground_truth.get(
                "expected_fix",
                "",
            )
            or ""
        )

        # --------------------------------------------------------
        # Compatibility fallback for older case structures.
        # --------------------------------------------------------

        if not severity:

            severity = (
                ground_truth.get(
                    "expected_severity",
                    "",
                )
                or ""
            )

        if not concept:

            concept = (
                ground_truth.get(
                    "expected_concept",
                    "",
                )
                or ""
            )

        if not expected_fix:

            expected_fix = (
                ground_truth.get(
                    "fix",
                    "",
                )
                or ""
            )

        # --------------------------------------------------------
        # AI result
        # --------------------------------------------------------

        ai_root_cause = (
            ai_row.get(
                "ai_root_cause",
                "",
            )
            or ""
        )

        ai_osi_layer = (
            ai_row.get(
                "ai_osi_layer",
                "",
            )
            or ""
        )

        ai_severity = (
            ai_row.get(
                "ai_severity",
                "",
            )
            or ""
        )

        ai_confidence = (
            ai_row.get(
                "ai_confidence",
                "",
            )
            or ""
        )

        ai_fix = (
            ai_row.get(
                "ai_fix",
                "",
            )
            or ""
        )

        ai_evidence = (
            ai_row.get(
                "ai_evidence",
                "",
            )
            or ""
        )

        generated_at = (
            ai_row.get(
                "generated_at",
                "",
            )
            or ""
        )

        # --------------------------------------------------------
        # Existing human evaluation.
        # --------------------------------------------------------

        evaluation_row = (
            evaluation_results.get(
                case_id,
                {},
            )
        )

        evaluation = (
            evaluation_row.get(
                "evaluation",
                "",
            )
            or ""
        )

        reviewer_notes = (
            evaluation_row.get(
                "reviewer_notes",
                "",
            )
            or ""
        )

        category = (
            ai_row.get(
                "category",
                "",
            )
            or ground_truth.get(
                "category",
                "",
            )
            or ""
        )

        # --------------------------------------------------------
        # Nested structure.
        # --------------------------------------------------------

        case_data = {

            "case_id":
                case_id,

            "category":
                category,

            "ground_truth": {

                "expected_fault":
                    expected_fault,

                "osi_layer":
                    osi_layer,

                "severity":
                    severity,

                "expected_fix":
                    expected_fix,

                "concept":
                    concept,
            },

            "ai": {

                "root_cause":
                    ai_root_cause,

                "osi_layer":
                    ai_osi_layer,

                "severity":
                    ai_severity,

                "confidence":
                    ai_confidence,

                "fix":
                    ai_fix,

                "evidence":
                    ai_evidence,

                "generated_at":
                    generated_at,
            },

            "evaluation":
                evaluation,

            "reviewer_notes":
                reviewer_notes,

            # ----------------------------------------------------
            # Flat compatibility fields.
            #
            # These are intentionally included so older frontend
            # versions do not show "undefined".
            # ----------------------------------------------------

            "expected_fault":
                expected_fault,

            "expected_osi_layer":
                osi_layer,

            "expected_severity":
                severity,

            "expected_fix":
                expected_fix,

            "concept":
                concept,

            "ai_root_cause":
                ai_root_cause,

            "ai_osi_layer":
                ai_osi_layer,

            "ai_severity":
                ai_severity,

            "ai_confidence":
                ai_confidence,

            "ai_fix":
                ai_fix,

            "ai_evidence":
                ai_evidence,

            "generated_at":
                generated_at,
        }

        cases.append(
            case_data
        )

    return {
        "count":
            len(cases),

        "total_generated":
            len(cases),

        "cases":
            cases,
    }

# ============================================================
# EVALUATION — SAVE HUMAN JUDGMENT
# ============================================================

@app.post(
    "/evaluation/result"
)
def save_evaluation_result(
    request: EvaluationResultRequest
):

    allowed = {
        "Correct",
        "Partially Correct",
        "Incorrect",
    }

    evaluation = (
        request.evaluation
        .strip()
    )

    if evaluation not in allowed:

        raise HTTPException(
            status_code=400,
            detail=(
                "evaluation must be "
                "Correct, Partially Correct, "
                "or Incorrect."
            ),
        )

    # --------------------------------------------------------
    # Check that AI result exists.
    # --------------------------------------------------------

    ai_results = (
        read_ai_results()
    )

    if request.case_id not in ai_results:

        raise HTTPException(
            status_code=404,
            detail=(
                "No AI diagnosis has been "
                f"generated for {request.case_id}."
            ),
        )

    # --------------------------------------------------------
    # Read previous human evaluations.
    # --------------------------------------------------------

    evaluations = (
        read_evaluation_results()
    )

    # --------------------------------------------------------
    # Update this case.
    # --------------------------------------------------------

    evaluations[
        request.case_id
    ] = {

        "case_id":
            request.case_id,

        "evaluation":
            evaluation,

        "reviewer_notes":
            request.reviewer_notes,

        "evaluated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    write_evaluation_results(
        evaluations
    )

    print(
        "[NetSage] Evaluation saved:",
        request.case_id,
        evaluation,
    )

    return {

        "status":
            "saved",

        "case_id":
            request.case_id,

        "evaluation":
            evaluation,
    }


# ============================================================
# METRICS
# ============================================================

@app.get(
    "/metrics"
)
def metrics():

    # --------------------------------------------------------
    # Load data.
    # --------------------------------------------------------

    ai_results = (
        read_ai_results()
    )

    evaluations = (
        read_evaluation_results()
    )

    # --------------------------------------------------------
    # Count evaluations.
    # --------------------------------------------------------

    total_evaluated = (
        len(evaluations)
    )

    correct = 0
    partial = 0
    incorrect = 0

    for evaluation in (
        evaluations.values()
    ):

        value = (
            evaluation.get(
                "evaluation",
                "",
            )
            or ""
        ).strip()

        if value == "Correct":

            correct += 1

        elif value == "Partially Correct":

            partial += 1

        elif value == "Incorrect":

            incorrect += 1

    # --------------------------------------------------------
    # Rates.
    # --------------------------------------------------------

    exact_correct_rate = (

        correct /
        total_evaluated

        if total_evaluated
        else 0
    )

    agreement_rate = (

        (
            correct +
            partial
        )
        /
        total_evaluated

        if total_evaluated
        else 0
    )

    # --------------------------------------------------------
    # Category metrics.
    # --------------------------------------------------------

    by_category = {}

    for case_id, evaluation in (
        evaluations.items()
    ):

        case = CASES.get(
            case_id,
            {},
        )

        category = case.get(
            "category",
            "Unknown",
        )

        if category not in by_category:

            by_category[
                category
            ] = {

                "total": 0,
                "correct": 0,
                "partial": 0,
                "incorrect": 0,
            }

        item = by_category[
            category
        ]

        item["total"] += 1

        value = (
            evaluation.get(
                "evaluation",
                "",
            )
            or ""
        ).strip()

        if value == "Correct":

            item["correct"] += 1

        elif value == "Partially Correct":

            item["partial"] += 1

        elif value == "Incorrect":

            item["incorrect"] += 1

    # --------------------------------------------------------
    # Severity metrics.
    # --------------------------------------------------------

    by_severity = {}

    for case_id, evaluation in (
        evaluations.items()
    ):

        case = CASES.get(
            case_id,
            {},
        )

        severity = case.get(
            "severity",
            "Unknown",
        )

        if severity not in by_severity:

            by_severity[
                severity
            ] = {

                "total": 0,
                "correct": 0,
                "partial": 0,
                "incorrect": 0,
            }

        item = by_severity[
            severity
        ]

        item["total"] += 1

        value = (
            evaluation.get(
                "evaluation",
                "",
            )
            or ""
        ).strip()

        if value == "Correct":

            item["correct"] += 1

        elif value == "Partially Correct":

            item["partial"] += 1

        elif value == "Incorrect":

            item["incorrect"] += 1

    # --------------------------------------------------------
    # Final metrics.
    # --------------------------------------------------------

    return {

        "total_cases":
            len(CASES),

        "ai_results":
            len(ai_results),

        "total_evaluated":
            total_evaluated,

        "pending_evaluation":
            max(
                len(ai_results)
                -
                total_evaluated,
                0,
            ),

        "correct":
            correct,

        "partial":
            partial,

        "incorrect":
            incorrect,

        "exact_correct_rate":
            round(
                exact_correct_rate,
                3,
            ),

        "agreement_rate":
            round(
                agreement_rate,
                3,
            ),

        "by_category":
            by_category,

        "by_severity":
            by_severity,
    }


# ============================================================
# DEBUG ENDPOINT
# ============================================================

@app.get(
    "/debug/evaluation"
)
def debug_evaluation():

    """
    Temporary/simple debugging endpoint.

    Useful while testing locally.
    """

    ai_results = (
        read_ai_results()
    )

    evaluations = (
        read_evaluation_results()
    )

    return {

        "ai_results_file":
            str(AI_RESULTS_FILE),

        "ai_results_exists":
            AI_RESULTS_FILE.exists(),

        "ai_result_count":
            len(ai_results),

        "ai_case_ids":
            list(ai_results.keys()),

        "evaluation_results_file":
            str(
                EVALUATION_RESULTS_FILE
            ),

        "evaluation_results_exists":
            EVALUATION_RESULTS_FILE.exists(),

        "evaluated_case_ids":
            list(
                evaluations.keys()
            ),
    }