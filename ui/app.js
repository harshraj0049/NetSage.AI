// ============================================================
// NetSage AI Frontend
// ============================================================

const API_BASE = "http://127.0.0.1:8000";

let sessionId = null;
let currentCaseId = null;


// ============================================================
// HELPERS
// ============================================================

function setStatus(message) {
    const element = document.getElementById("status");

    if (element) {
        element.textContent = message;
    }
}


function setResult(message) {
    const element = document.getElementById("result");

    if (element) {
        element.textContent = message;
    }
}


function showReviewButtons(show) {
    const section = document.getElementById("reviewSection");

    if (!section) {
        return;
    }

    section.style.display = show ? "block" : "none";
}


function getCaseId() {
    const element = document.getElementById("caseId");

    if (!element) {
        return currentCaseId || null;
    }

    const value = (element.value || "").trim();

    if (value) {
        return value;
    }

    return currentCaseId || null;
}


function setDiagnosisFormEnabled(enabled) {
    const symptom = document.getElementById("symptom");
    const evidence = document.getElementById("evidence");

    if (symptom) {
        symptom.disabled = !enabled;
    }

    if (evidence) {
        evidence.disabled = !enabled;
    }
}


function createSessionId() {
    if (
        window.crypto &&
        typeof window.crypto.randomUUID === "function"
    ) {
        return window.crypto.randomUUID();
    }

    return (
        "netsage-" +
        Date.now().toString(36) +
        "-" +
        Math.random().toString(36).slice(2)
    );
}


// ============================================================
// SHOW RESPONSE
// ============================================================

function showResult(data) {

    // --------------------------------------------------------
    // Additional evidence required
    // --------------------------------------------------------

    if (data.status === "needs_more_evidence") {

        setResult(
            "ADDITIONAL EVIDENCE REQUIRED\n\n" +
            "Case ID:\n" +
            (data.case_id || currentCaseId || "") +
            "\n\n" +
            "Command requested:\n" +
            (data.requested_command || "Not specified") +
            "\n\n" +
            "Reason:\n" +
            (
                data.reasoning ||
                "The AI needs more evidence."
            )
        );

        setStatus(
            "Provide the requested evidence and click Diagnose again."
        );

        showReviewButtons(false);
        setDiagnosisFormEnabled(true);

        return;
    }


    // --------------------------------------------------------
    // Human review required
    // --------------------------------------------------------

    if (data.status === "needs_human_review") {

        const diagnosis = data.diagnosis || {};

        const evidence =
            Array.isArray(diagnosis.evidence)
                ? diagnosis.evidence.join("\n")
                : (diagnosis.evidence || "");

        const fixes =
            Array.isArray(diagnosis.fix_steps)
                ? diagnosis.fix_steps.join("\n")
                : (diagnosis.fix_steps || "");

        setResult(
            "HUMAN REVIEW REQUIRED\n\n" +

            "Case ID:\n" +
            (
                data.case_id ||
                currentCaseId ||
                ""
            ) +

            "\n\nRoot cause:\n" +
            (
                diagnosis.root_cause ||
                ""
            ) +

            "\n\nOSI Layer:\n" +
            (
                diagnosis.osi_layer ||
                ""
            ) +

            "\n\nConfidence:\n" +
            (
                diagnosis.confidence ??
                ""
            ) +

            "\n\nSeverity:\n" +
            (
                diagnosis.severity ||
                ""
            ) +

            "\n\nEvidence:\n" +
            evidence +

            "\n\nFix:\n" +
            fixes
        );

        setStatus(
            "Human review required."
        );

        showReviewButtons(true);
        setDiagnosisFormEnabled(false);

        return;
    }


    // --------------------------------------------------------
    // Approved
    // --------------------------------------------------------

    if (data.status === "approved") {

        setResult(
            "FINAL DIAGNOSIS\n\n" +
            JSON.stringify(
                data.final_diagnosis,
                null,
                2
            )
        );

        setStatus(
            "Diagnosis approved."
        );

        showReviewButtons(false);
        setDiagnosisFormEnabled(true);

        return;
    }


    // --------------------------------------------------------
    // Edited
    // --------------------------------------------------------

    if (data.status === "edited") {

        setResult(
            "FINAL DIAGNOSIS — HUMAN EDITED\n\n" +
            JSON.stringify(
                data.final_diagnosis,
                null,
                2
            )
        );

        setStatus(
            "Diagnosis edited by human reviewer."
        );

        showReviewButtons(false);
        setDiagnosisFormEnabled(true);

        return;
    }


    // --------------------------------------------------------
    // Rejected
    // --------------------------------------------------------

    if (data.status === "rejected") {

        setResult(
            "DIAGNOSIS REJECTED\n\n" +
            (
                data.reason ||
                "Rejected by human reviewer."
            )
        );

        setStatus(
            "Diagnosis rejected."
        );

        showReviewButtons(false);
        setDiagnosisFormEnabled(true);

        return;
    }


    // --------------------------------------------------------
    // Completed / fallback
    // --------------------------------------------------------

    setResult(
        data.message ||
        "NetSage completed the request."
    );

    setStatus(
        data.status === "completed"
            ? "Completed."
            : (
                data.status ||
                "Completed."
            )
    );
}


// ============================================================
// DIAGNOSE
// ============================================================

async function diagnose() {

    const symptomElement =
        document.getElementById("symptom");

    const evidenceElement =
        document.getElementById("evidence");


    const symptom =
        symptomElement
            ? symptomElement.value.trim()
            : "";


    const evidence =
        evidenceElement
            ? evidenceElement.value.trim()
            : "";


    const enteredCaseId =
        getCaseId();


    // --------------------------------------------------------
    // Validate symptom
    // --------------------------------------------------------

    if (!symptom) {

        setStatus(
            "Please enter a symptom."
        );

        return;
    }


    // --------------------------------------------------------
    // Validate evidence
    // --------------------------------------------------------

    if (!evidence) {

        setStatus(
            "Please enter evidence."
        );

        return;
    }


    // --------------------------------------------------------
    // Benchmark Case ID is required.
    //
    // This ensures the backend can associate the AI diagnosis
    // with the correct benchmark case and save it into:
    //
    // evaluation/ai_results.csv
    // --------------------------------------------------------

    if (!enteredCaseId) {

        setStatus(
            "Please enter the benchmark Case ID before diagnosing."
        );

        setResult(
            "Example: V1_01\n\n" +
            "The Case ID is required so NetSage can save " +
            "this AI diagnosis to evaluation/ai_results.csv."
        );

        return;
    }


    // --------------------------------------------------------
    // Preserve the case ID for every subsequent request.
    // --------------------------------------------------------

    currentCaseId =
        enteredCaseId;


    // --------------------------------------------------------
    // Generate the session ID on the frontend.
    //
    // This guarantees that the first request already has a
    // stable session ID that can be reused for:
    //
    // 1. Initial diagnosis
    // 2. Additional evidence
    // 3. Human review
    // --------------------------------------------------------

    if (!sessionId) {

        sessionId =
            createSessionId();
    }


    setStatus(
        "NetSage is analyzing..."
    );


    try {

        const response =
            await fetch(
                `${API_BASE}/diagnose`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            session_id:
                                sessionId,

                            case_id:
                                currentCaseId,

                            symptom:
                                symptom,

                            evidence:
                                evidence
                        })
                }
            );


        // ----------------------------------------------------
        // Parse JSON safely.
        // ----------------------------------------------------

        let data;

        try {

            data =
                await response.json();

        } catch (jsonError) {

            throw new Error(
                `Backend returned an invalid response (HTTP ${response.status}).`
            );
        }


        // ----------------------------------------------------
        // Backend error
        // ----------------------------------------------------

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                "Diagnosis failed."
            );
        }


        // ----------------------------------------------------
        // Backend remains authoritative if it returns IDs.
        // ----------------------------------------------------

        sessionId =
            data.session_id ||
            sessionId;


        currentCaseId =
            data.case_id ||
            currentCaseId;


        // ----------------------------------------------------
        // Display result.
        // ----------------------------------------------------

        showResult(
            data
        );


        // ----------------------------------------------------
        // Clear only the evidence field.
        //
        // IMPORTANT:
        // The backend keeps the evidence history in the session.
        //
        // The symptom and Case ID remain visible so the user
        // knows which case is currently active.
        // ----------------------------------------------------

        if (evidenceElement) {

            evidenceElement.value =
                "";
        }


    } catch (error) {

        console.error(
            "NetSage diagnose error:",
            error
        );


        setStatus(
            "Error"
        );


        setResult(
            error.message ||
            "Unable to contact the NetSage backend."
        );
    }
}


// ============================================================
// APPROVE
// ============================================================

async function approveDiagnosis() {

    await submitReview(
        "approve"
    );
}


// ============================================================
// REJECT
// ============================================================

async function rejectDiagnosis() {

    const reason =
        prompt(
            "Reason for rejection:"
        );


    if (reason === null) {

        return;
    }


    await submitReview(
        "reject",
        null,
        reason
    );
}


// ============================================================
// EDIT
// ============================================================

async function editDiagnosis() {

    const rootCause =
        prompt(
            "Corrected root cause:"
        );


    if (
        !rootCause ||
        !rootCause.trim()
    ) {

        return;
    }


    const reason =
        prompt(
            "Why are you correcting the AI?"
        );


    if (reason === null) {

        return;
    }


    await submitReview(
        "edit",
        {
            root_cause:
                rootCause.trim()
        },
        reason
    );
}


// ============================================================
// REVIEW REQUEST
// ============================================================

async function submitReview(
    decision,
    correction = null,
    reason = null
) {

    // --------------------------------------------------------
    // A review is only valid for an active session.
    // --------------------------------------------------------

    if (!sessionId) {

        setStatus(
            "No active troubleshooting session."
        );

        return;
    }


    try {

        const response =
            await fetch(
                `${API_BASE}/review`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            session_id:
                                sessionId,

                            decision:
                                decision,

                            correction:
                                correction,

                            reason:
                                reason
                        })
                }
            );


        // ----------------------------------------------------
        // Parse response safely.
        // ----------------------------------------------------

        let data;

        try {

            data =
                await response.json();

        } catch (jsonError) {

            throw new Error(
                `Backend returned an invalid review response (HTTP ${response.status}).`
            );
        }


        // ----------------------------------------------------
        // Backend error
        // ----------------------------------------------------

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                "Review failed."
            );
        }


        // ----------------------------------------------------
        // Preserve backend identifiers.
        // ----------------------------------------------------

        sessionId =
            data.session_id ||
            sessionId;


        currentCaseId =
            data.case_id ||
            currentCaseId;


        // ----------------------------------------------------
        // Display review result.
        // ----------------------------------------------------

        showResult(
            data
        );


    } catch (error) {

        console.error(
            "NetSage review error:",
            error
        );


        setStatus(
            "Review error"
        );


        setResult(
            error.message ||
            "Unable to submit the human review."
        );
    }
}


// ============================================================
// NEW SESSION
// ============================================================

function newSession() {

    // --------------------------------------------------------
    // Completely reset the frontend session.
    // --------------------------------------------------------

    sessionId =
        null;

    currentCaseId =
        null;


    const symptom =
        document.getElementById(
            "symptom"
        );


    const evidence =
        document.getElementById(
            "evidence"
        );


    const caseId =
        document.getElementById(
            "caseId"
        );


    // --------------------------------------------------------
    // Clear symptom.
    // --------------------------------------------------------

    if (symptom) {

        symptom.value =
            "";
    }


    // --------------------------------------------------------
    // Clear evidence.
    // --------------------------------------------------------

    if (evidence) {

        evidence.value =
            "";
    }


    // --------------------------------------------------------
    // Clear Case ID.
    // --------------------------------------------------------

    if (caseId) {

        caseId.value =
            "";
    }


    // --------------------------------------------------------
    // Reset result/status.
    // --------------------------------------------------------

    setResult(
        ""
    );


    setStatus(
        "New troubleshooting session."
    );


    // --------------------------------------------------------
    // Hide human review controls.
    // --------------------------------------------------------

    showReviewButtons(
        false
    );


    // --------------------------------------------------------
    // Re-enable diagnosis fields.
    // --------------------------------------------------------

    setDiagnosisFormEnabled(
        true
    );
}


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function () {

        showReviewButtons(
            false
        );


        setDiagnosisFormEnabled(
            true
        );

    }
);