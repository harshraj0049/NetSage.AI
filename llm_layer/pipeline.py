import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from llm_layer.evidence_parser import parse_evidence
from llm_layer.rulechecker import run_all_checks


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

gemini_key = os.getenv("GEMINI_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")

if gemini_key and not google_key:
    os.environ["GOOGLE_API_KEY"] = gemini_key

if gemini_key and google_key:
    print(
        "Both GOOGLE_API_KEY and GEMINI_API_KEY are set. "
        "Using GOOGLE_API_KEY."
    )


groq_key = os.getenv("GROQ_API_KEY")

if not groq_key:
    raise RuntimeError(
        "GROQ_API_KEY is not set in the .env file."
    )

# ============================================================
# PATHS
# ============================================================

CASES_FILE = BASE_DIR / "data" / "cases.csv"

PROMPT_FILE = (
    BASE_DIR
    / "prompts"
    / "diagnose_prompt.md"
)

EVALUATION_DIR = (
    BASE_DIR
    / "evaluation"
)

AI_RESULTS_FILE = (
    EVALUATION_DIR
    / "ai_results.csv"
)

HISTORY_FILE = (
    BASE_DIR
    / "llm_layer"
    / "case_history.jsonl"
)


EVALUATION_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# LOAD CASES
# ============================================================

def load_cases():
    """
    Load benchmark cases from cases.csv.

    Supports both:
    1. The correct 13-column CSV format.
    2. The older malformed CSV format where the header contains
       only 11 columns but each data row contains 13 values.

    Normalized case structure:

        case_id
        category
        symptom
        initial_evidence
        expected_next_command
        additional_evidence
        expected_fault
        osi_layer
        concept
        severity
        expected_fix
        stage
        rule_solvable
    """

    cases = {}

    if not CASES_FILE.exists():
        print(
            f"[CASES] WARNING: cases file not found: {CASES_FILE}"
        )
        return cases

    try:
        with open(
            CASES_FILE,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.reader(file)

            rows = list(reader)

    except Exception as exc:
        print(
            f"[CASES] ERROR loading cases.csv: {exc}"
        )
        return cases

    if not rows:
        return cases

    header = [
        str(value).strip()
        for value in rows[0]
    ]

    # ------------------------------------------------------------
    # Correct expected 13-column schema.
    # ------------------------------------------------------------

    expected_headers = [
        "case_id",
        "category",
        "symptom",
        "initial_evidence",
        "expected_next_command",
        "additional_evidence",
        "expected_fault",
        "osi_layer",
        "concept",
        "severity",
        "expected_fix",
        "stage",
        "rule_solvable",
    ]

    # ------------------------------------------------------------
    # Process every data row.
    # ------------------------------------------------------------

    for row_number, raw_row in enumerate(
        rows[1:],
        start=2,
    ):

        row = [
            str(value).strip()
            for value in raw_row
        ]

        if not row:
            continue

        # --------------------------------------------------------
        # Ignore completely empty rows.
        # --------------------------------------------------------

        if not any(row):
            continue

        # --------------------------------------------------------
        # The supplied CSV currently has 13 values per data row
        # but only 11 headers.
        #
        # Its actual layout is:
        #
        # 0  case_id
        # 1  category
        # 2  symptom
        # 3  initial_evidence
        # 4  expected_next_command
        # 5  additional_evidence
        # 6  expected_fault
        # 7  osi_layer
        # 8  concept
        # 9  severity
        # 10 expected_fix
        # 11 stage
        # 12 rule_solvable
        # --------------------------------------------------------

        if len(row) >= 13:

            normalized = {
                "case_id": row[0],
                "category": row[1],
                "symptom": row[2],
                "initial_evidence": row[3],
                "expected_next_command": row[4],
                "additional_evidence": row[5],
                "expected_fault": row[6],
                "osi_layer": row[7],
                "concept": row[8],
                "severity": row[9],
                "expected_fix": row[10],
                "stage": row[11],
                "rule_solvable": row[12],
            }

        else:

            # ----------------------------------------------------
            # Correctly formatted CSV with named headers.
            # ----------------------------------------------------

            padded = row + [
                ""
            ] * max(
                0,
                len(header) - len(row),
            )

            raw = {
                key: padded[index]
                for index, key in enumerate(header)
                if index < len(padded)
            }

            normalized = {
                key: raw.get(key, "")
                for key in expected_headers
            }

            # Some versions used "fix" instead of
            # "expected_fix".
            if not normalized["expected_fix"]:
                normalized["expected_fix"] = (
                    raw.get("fix", "")
                )

            # Some versions used "expected_severity".
            if not normalized["severity"]:
                normalized["severity"] = (
                    raw.get(
                        "expected_severity",
                        "",
                    )
                )

            # Some versions used "expected_concept".
            if not normalized["concept"]:
                normalized["concept"] = (
                    raw.get(
                        "expected_concept",
                        "",
                    )
                )

        case_id = (
            normalized.get(
                "case_id",
                "",
            )
            or ""
        ).strip()

        if not case_id:
            print(
                f"[CASES] WARNING: skipping row {row_number} "
                "because case_id is empty."
            )
            continue

        cases[case_id] = normalized

    print(
        f"[CASES] Loaded {len(cases)} benchmark cases."
    )

    return cases


CASES = load_cases()


# ============================================================
# MODEL
# ============================================================

model = init_chat_model(     
    "google_genai:gemini-3.1-flash-lite" 
)


# ============================================================
# LLM RESPONSE MODELS
# ============================================================

class SubmitDiagnosis(BaseModel):

    root_cause: str = Field(
        ...,
        description=(
            "The identified root cause "
            "of the network fault."
        ),
    )

    osi_layer: str = Field(
        ...,
        description=(
            "The relevant OSI layer."
        ),
    )

    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description=(
            "Confidence between 0 and 1."
        ),
    )

    evidence: list[str] = Field(
        ...,
        description=(
            "Specific evidence supporting "
            "the diagnosis."
        ),
    )

    fix_steps: list[str] = Field(
        ...,
        description=(
            "Concrete and minimal steps "
            "to fix the fault."
        ),
    )

    severity: Literal[
        "Low",
        "Medium",
        "High",
    ] = Field(
        ...,
        description=(
            "Severity of the issue."
        ),
    )


class RequestMoreEvidence(BaseModel):

    next_command: str = Field(
        ...,
        description=(
            "The exact Cisco command "
            "needed next."
        ),
    )

    reasoning: str = Field(
        ...,
        description=(
            "Why the additional evidence "
            "is required."
        ),
    )


# ============================================================
# TOOLS
# ============================================================

@tool(args_schema=RequestMoreEvidence)
def request_more_evidence(
    next_command: str,
    reasoning: str,
):
    """
    Ask the user for additional evidence.

    The tool does NOT access cases.csv.
    The user supplies the next evidence.
    """

    return {
        "status": "more_evidence_needed",
        "requested_command": next_command,
        "reasoning": reasoning,
    }


@tool(args_schema=SubmitDiagnosis)
def submit_diagnosis(
    root_cause: str,
    osi_layer: str,
    confidence: float,
    evidence: list[str],
    fix_steps: list[str],
    severity: str,
):
    """
    Submit a final diagnosis.

    HumanInTheLoopMiddleware intercepts
    this tool call before acceptance.
    """

    return {
        "root_cause": root_cause,
        "osi_layer": osi_layer,
        "confidence": confidence,
        "evidence": evidence,
        "fix_steps": fix_steps,
        "severity": severity,
    }


# ============================================================
# SYSTEM PROMPT
# ============================================================

def load_system_prompt():

    if PROMPT_FILE.exists():

        return PROMPT_FILE.read_text(
            encoding="utf-8",
        )

    return """
You are NetSage AI, a Cisco network troubleshooting assistant.

You receive:
1. A user symptom.
2. Deterministic rule-checker findings.
3. Cisco show-command evidence.

Only diagnose when the evidence supports the conclusion.

Rules:
- Never invent network information.
- Do not treat missing evidence as proof of a fault.
- If evidence is insufficient, request more evidence.
- If multiple faults remain possible, request more evidence.
- Use actual supplied evidence.
- Prefer the smallest safe fix.
- Do not remove an entire security control when a specific rule
  is the actual problem.
- Submit a diagnosis only when sufficiently supported.

Call exactly one tool per turn:
request_more_evidence
OR
submit_diagnosis.
"""


SYSTEM_PROMPT = load_system_prompt()


# ============================================================
# LANGGRAPH AGENT
# ============================================================

checkpointer = InMemorySaver()


agent = create_agent(
    model=model,

    tools=[
        request_more_evidence,
        submit_diagnosis,
    ],

    system_prompt=SYSTEM_PROMPT,

    checkpointer=checkpointer,

    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on={
                "submit_diagnosis": {
                    "allowed_decisions": [
                        "approve",
                        "edit",
                        "reject",
                    ]
                },

                # Requesting more evidence should continue
                # without HITL.
                "request_more_evidence": False,
            }
        )
    ],
)


# ============================================================
# SESSION STORE
# ============================================================

SESSIONS = {}


def create_session(
    session_id: str,
    case_id: Optional[str] = None,
):

    if session_id not in SESSIONS:

        SESSIONS[session_id] = {

            "session_id":
                session_id,

            "case_id":
                case_id,

            "symptom":
                "",

            "evidence_parts":
                [],

            "checker_findings":
                {},

            "original_ai_diagnosis":
                None,

            "latest_diagnosis":
                None,

            "status":
                "active",

            "created_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),
        }

    else:

        if case_id:

            SESSIONS[
                session_id
            ][
                "case_id"
            ] = case_id

    return SESSIONS[
        session_id
    ]


def get_session(
    session_id: str,
):

    return SESSIONS.get(
        session_id
    )


# ============================================================
# EVIDENCE HELPERS
# ============================================================

def combine_evidence(
    session,
):

    return "\n\n".join(
        session[
            "evidence_parts"
        ]
    )


def parse_and_check(
    raw_evidence: str,
):

    try:

        parsed_evidence = (
            parse_evidence(
                raw_evidence
            )
        )

        checker_findings = (
            run_all_checks(
                parsed_evidence
            )
        )

        return (
            parsed_evidence,
            checker_findings,
        )

    except Exception as exc:

        return (
            {},
            {
                "parser": {
                    "status": "ERROR",
                    "reason": str(exc),
                    "details": {},
                }
            },
        )


# ============================================================
# MESSAGE BUILDER
# ============================================================

def build_human_message(
    symptom: str,
    checker_findings: dict,
    evidence: str,
):

    content = f"""
SYMPTOM:
{symptom}

DETERMINISTIC RULE CHECKER FINDINGS:
{json.dumps(checker_findings, indent=2)}

CISCO SHOW-COMMAND EVIDENCE:
{evidence}
"""

    return HumanMessage(
        content=content
    )


# ============================================================
# LOGGING
# ============================================================

def log_case(
    session_id: str,
    event: str,
    record: dict,
):

    HISTORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {

        "session_id":
            session_id,

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "event":
            event,

        **record,
    }

    with open(
        HISTORY_FILE,
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            json.dumps(
                payload,
                ensure_ascii=False,
            )
            + "\n"
        )


# ============================================================
# SAVE AI RESULT
# ============================================================

AI_RESULTS_HEADERS = [
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


def ensure_ai_results_file():

    if not AI_RESULTS_FILE.exists():

        with open(
            AI_RESULTS_FILE,
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=AI_RESULTS_HEADERS,
            )

            writer.writeheader()


def save_ai_result(
    session,
    diagnosis,
    case_id: Optional[str] = None,
):
    """
    Save the ORIGINAL AI diagnosis.

    This happens as soon as the AI submits the diagnosis,
    before the human reviewer chooses Approve/Edit/Reject.

    Normal non-benchmark sessions are ignored because they
    have no case_id.
    """

    # Prefer the explicitly supplied benchmark ID. Fall back to
    # the session value for callers that already have a stored case.
    case_id = (
        case_id
        or session.get("case_id")
        or ""
    ).strip()

    print(
        f"[AI RESULTS] save_ai_result called with case_id={case_id!r}"
    )

    if not case_id:
        print(
            "[AI RESULTS] SKIPPED: no benchmark case_id was supplied."
        )
        return False

    # Keep the session synchronized as well.
    session["case_id"] = case_id

    ensure_ai_results_file()

    category = ""

    if case_id in CASES:

        category = CASES[
            case_id
        ].get(
            "category",
            "",
        )

    row = {

        "case_id":
            case_id,

        "category":
            category,

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
            " | ".join(
                str(x)
                for x in diagnosis.get(
                    "fix_steps",
                    [],
                )
            ),

        "ai_evidence":
            " | ".join(
                str(x)
                for x in diagnosis.get(
                    "evidence",
                    [],
                )
            ),

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    existing_rows = []

    if AI_RESULTS_FILE.exists():

        with open(
            AI_RESULTS_FILE,
            "r",
            encoding="utf-8",
            newline="",
        ) as file:

            reader = csv.DictReader(
                file
            )

            for existing in reader:

                existing_case_id = (
                    existing.get(
                        "case_id",
                        "",
                    )
                    or ""
                ).strip()

                if (
                    existing_case_id
                    != case_id
                ):

                    existing_rows.append(
                        existing
                    )

    existing_rows.append(
        row
    )

    with open(
        AI_RESULTS_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=AI_RESULTS_HEADERS,
        )

        writer.writeheader()

        writer.writerows(
            existing_rows
        )

    print(
        f"[AI RESULTS] Saved {case_id} -> {AI_RESULTS_FILE}"
    )

    return True


# ============================================================
# LANGGRAPH INTERRUPT HELPERS
# ============================================================

def get_interrupts(
    result,
):

    interrupts = result.get(
        "__interrupt__"
    )

    if not interrupts:
        return []

    if isinstance(
        interrupts,
        (list, tuple),
    ):

        return list(
            interrupts
        )

    return [interrupts]


def get_action_requests(
    result,
):

    interrupts = get_interrupts(
        result
    )

    if not interrupts:
        return []

    all_actions = []

    for interrupt in interrupts:

        value = getattr(
            interrupt,
            "value",
            None,
        )

        if not isinstance(
            value,
            dict,
        ):
            continue

        actions = value.get(
            "action_requests",
            [],
        )

        if isinstance(
            actions,
            list,
        ):

            all_actions.extend(
                actions
            )

    return all_actions


# ============================================================
# EXTRACT AI DIAGNOSIS
# ============================================================

def extract_diagnosis_from_action(
    action,
):

    if not action:
        return None

    if action.get(
        "name"
    ) != "submit_diagnosis":

        return None

    args = action.get(
        "args",
        {},
    )

    if not isinstance(
        args,
        dict,
    ):
        return None

    return {
        "root_cause":
            args.get(
                "root_cause",
                "",
            ),

        "osi_layer":
            args.get(
                "osi_layer",
                "",
            ),

        "confidence":
            args.get(
                "confidence",
                0,
            ),

        "evidence":
            args.get(
                "evidence",
                [],
            ),

        "fix_steps":
            args.get(
                "fix_steps",
                [],
            ),

        "severity":
            args.get(
                "severity",
                "",
            ),
    }


# ============================================================
# MAIN DIAGNOSIS
# ============================================================

def diagnose(
    symptom: str,
    raw_evidence: str,
    session_id: Optional[str] = None,
    case_id: Optional[str] = None,
):
    """
    Web-facing diagnosis function.

    Every request belongs to a session.

    A session may go through:

        initial evidence
              ↓
        more evidence
              ↓
        more evidence
              ↓
        AI diagnosis
              ↓
        HITL review
    """

    if not session_id:

        raise ValueError(
            "session_id is required."
        )

    session = create_session(
        session_id,
        case_id,
    )

    # The benchmark case ID is metadata supplied by the browser.
    # Preserve it across additional-evidence turns.
    if case_id:
        session["case_id"] = case_id.strip()

    if symptom.strip():

        session[
            "symptom"
        ] = symptom.strip()

    if raw_evidence.strip():

        session[
            "evidence_parts"
        ].append(
            raw_evidence.strip()
        )

    combined_evidence = (
        combine_evidence(
            session
        )
    )

    parsed_evidence, checker_findings = (
        parse_and_check(
            combined_evidence
        )
    )

    session[
        "checker_findings"
    ] = checker_findings

    human_message = (
        build_human_message(
            session[
                "symptom"
            ],
            checker_findings,
            combined_evidence,
        )
    )

    config = {
        "configurable": {
            "thread_id":
                session_id
        }
    }

    result = agent.invoke(
        {
            "messages": [
                human_message
            ]
        },
        config=config,
    )

    actions = get_action_requests(
        result
    )

    # ========================================================
    # REQUEST MORE EVIDENCE
    # ========================================================

    for action in actions:

        if action.get(
            "name"
        ) == "request_more_evidence":

            args = action.get(
                "args",
                {},
            )

            requested_command = (
                args.get(
                    "next_command",
                    "",
                )
            )

            reasoning = (
                args.get(
                    "reasoning",
                    "",
                )
            )

            session[
                "status"
            ] = "needs_more_evidence"

            log_case(
                session_id,
                "ai_requested_evidence",
                {
                    "command":
                        requested_command,

                    "reasoning":
                        reasoning,

                    "checker_findings":
                        checker_findings,
                },
            )

            return {

                "status":
                    "needs_more_evidence",

                "session_id":
                    session_id,

                "case_id":
                    session.get(
                        "case_id"
                    ),

                "requested_command":
                    requested_command,

                "reasoning":
                    reasoning,

                "checker_findings":
                    checker_findings,
            }

    # ========================================================
    # AI DIAGNOSIS / HITL INTERRUPT
    # ========================================================

    for action in actions:

        diagnosis = (
            extract_diagnosis_from_action(
                action
            )
        )

        if diagnosis is not None:

            session[
                "original_ai_diagnosis"
            ] = diagnosis

            session[
                "latest_diagnosis"
            ] = diagnosis

            session[
                "status"
            ] = "needs_human_review"

            # ------------------------------------------------
            # THIS IS THE IMPORTANT FIX:
            #
            # Save the AI result NOW, before HITL review.
            # ------------------------------------------------

            save_ai_result(
                session,
                diagnosis,
                case_id=session.get("case_id"),
            )

            log_case(
                session_id,
                "ai_diagnosis",
                {
                    "case_id":
                        session.get("case_id"),

                    "diagnosis":
                        diagnosis,

                    "checker_findings":
                        checker_findings,
                },
            )

            return {

                "status":
                    "needs_human_review",

                "session_id":
                    session_id,

                "case_id":
                    session.get(
                        "case_id"
                    ),

                "diagnosis":
                    diagnosis,

                "checker_findings":
                    checker_findings,
            }

    # ========================================================
    # FALLBACK
    # ========================================================

    # Do NOT dump raw LangChain messages into the frontend.
    # Return a clean response instead.

    return {

        "status":
            "completed",

        "session_id":
            session_id,

        "case_id":
            session.get(
                "case_id"
            ),

        "checker_findings":
            checker_findings,

        "message":
            "NetSage completed the turn, but did not produce a structured diagnosis or evidence request.",
    }


# ============================================================
# HUMAN REVIEW
# ============================================================

def review_diagnosis(
    session_id: str,
    decision: str,
    correction: Optional[dict] = None,
    reason: Optional[str] = None,
):
    """
    Handle the human decision for a pending diagnosis.
    """

    session = get_session(
        session_id
    )

    if not session:

        raise ValueError(
            "Session not found."
        )

    decision = (
        decision.strip()
        .lower()
    )

    if decision not in {
        "approve",
        "edit",
        "reject",
    }:

        raise ValueError(
            "Decision must be "
            "approve, edit, or reject."
        )

    original_ai = session.get(
        "original_ai_diagnosis"
    )

    if not original_ai:

        raise ValueError(
            "No AI diagnosis is pending "
            "for human review."
        )

    # --------------------------------------------------------
    # APPROVE
    # --------------------------------------------------------

    if decision == "approve":

        final_diagnosis = (
            original_ai
        )

        status = "approved"

    # --------------------------------------------------------
    # EDIT
    # --------------------------------------------------------

    elif decision == "edit":

        if not correction:

            raise ValueError(
                "Correction is required "
                "when editing."
            )

        final_diagnosis = dict(
            original_ai
        )

        final_diagnosis.update(
            correction
        )

        status = "edited"

    # --------------------------------------------------------
    # REJECT
    # --------------------------------------------------------

    else:

        final_diagnosis = None

        status = "rejected"

    # --------------------------------------------------------
    # Log HITL event.
    # --------------------------------------------------------

    log_case(
        session_id,
        "human_review",
        {
            "decision":
                status,

            "ai_diagnosis":
                original_ai,

            "human_correction":
                correction,

            "final_diagnosis":
                final_diagnosis,

            "reason":
                reason,
        },
    )

    session[
        "status"
    ] = status

    session[
        "latest_diagnosis"
    ] = final_diagnosis

    return {

        "status":
            status,

        "session_id":
            session_id,

        "case_id":
            session.get(
                "case_id"
            ),

        "final_diagnosis":
            final_diagnosis,

        "reason":
            reason,
    }


# ============================================================
# SESSION STATE
# ============================================================

def get_session_state(
    session_id: str,
):

    session = get_session(
        session_id
    )

    if not session:

        raise ValueError(
            "Session not found."
        )

    return {

        "session_id":
            session_id,

        "case_id":
            session.get(
                "case_id"
            ),

        "symptom":
            session.get(
                "symptom",
                "",
            ),

        "status":
            session.get(
                "status",
                "active",
            ),

        "checker_findings":
            session.get(
                "checker_findings",
                {},
            ),

        "pending_diagnosis":
            session.get(
                "original_ai_diagnosis"
            ),

        "latest_diagnosis":
            session.get(
                "latest_diagnosis"
            ),
    }


# ============================================================
# RESET SESSION
# ============================================================

def reset_session(
    session_id: str,
):

    if session_id in SESSIONS:

        del SESSIONS[
            session_id
        ]

    return {
        "status":
            "reset",
        "session_id":
            session_id,
    }