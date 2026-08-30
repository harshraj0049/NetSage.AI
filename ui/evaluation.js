// ============================================================
// NetSage Evaluation
// ============================================================

const API_BASE = "http://127.0.0.1:8000";

let evaluationCases = [];
let selectedCase = null;


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    () => {
        loadEvaluationCases();
    }
);


// ============================================================
// LOAD CASES
// ============================================================

async function loadEvaluationCases() {

    const summaryText =
        document.getElementById(
            "summaryText"
        );

    const caseList =
        document.getElementById(
            "caseList"
        );

    if (!caseList) {

        console.error(
            "Evaluation page is missing #caseList."
        );

        if (summaryText) {
            summaryText.textContent =
                "Evaluation page configuration error.";
        }

        return;
    }

    try {

        if (summaryText) {
            summaryText.textContent =
                "Loading generated AI results...";
        }

        const response =
            await fetch(
                `${API_BASE}/evaluation/cases`,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );

        let data;

        try {

            data =
                await response.json();

        } catch (error) {

            throw new Error(
                `Backend returned invalid JSON (HTTP ${response.status}).`
            );
        }

        console.log(
            "Evaluation API response:",
            data
        );

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                "Failed to load evaluation cases."
            );
        }

        evaluationCases =
            Array.isArray(data.cases)
                ? data.cases
                : [];

        const count =
            typeof data.count === "number"
                ? data.count
                : evaluationCases.length;

        if (summaryText) {

            summaryText.textContent =
                `${count} case(s) have AI results available for evaluation.`;
        }

        renderCaseList();

        // Automatically show the first case.
        if (evaluationCases.length > 0) {

            selectCase(
                evaluationCases[0].case_id
            );
        }

    } catch (error) {

        console.error(
            "Evaluation loading error:",
            error
        );

        evaluationCases = [];

        if (summaryText) {

            summaryText.textContent =
                "Unable to load evaluation cases.";
        }

        caseList.innerHTML = `
            <p>
                <strong>Error:</strong>
                ${escapeHtml(error.message)}
            </p>
        `;
    }
}


// ============================================================
// RENDER CASE LIST
// ============================================================

function renderCaseList() {

    const caseList =
        document.getElementById(
            "caseList"
        );

    if (!caseList) {
        return;
    }

    caseList.innerHTML = "";

    if (evaluationCases.length === 0) {

        caseList.innerHTML =
            "<p>No AI-generated cases are available yet.</p>";

        return;
    }

    evaluationCases.forEach(
        (caseData) => {

            const button =
                document.createElement(
                    "button"
                );

            button.type = "button";

            button.className =
                "case-button";

            const caseId =
                getValue(
                    caseData.case_id,
                    "Unknown"
                );

            const category =
                getValue(
                    caseData.category,
                    "Unknown"
                );

            if (caseData.evaluation) {

                button.classList.add(
                    "evaluated"
                );
            }

            button.textContent =
                `${caseId} — ${category}`;

            button.addEventListener(
                "click",
                () => {
                    selectCase(caseId);
                }
            );

            caseList.appendChild(
                button
            );
        }
    );
}


// ============================================================
// SELECT CASE
// ============================================================

function selectCase(caseId) {

    selectedCase =
        evaluationCases.find(
            (item) =>
                item.case_id === caseId
        );

    if (!selectedCase) {

        console.error(
            "Case not found:",
            caseId
        );

        return;
    }

    const casePanel =
        document.getElementById(
            "casePanel"
        );

    if (casePanel) {

        casePanel.style.display =
            "block";
    }

    const caseTitle =
        document.getElementById(
            "caseTitle"
        );

    if (caseTitle) {

        caseTitle.textContent =
            `${getValue(selectedCase.case_id, "Unknown")} — ${getValue(selectedCase.category, "Unknown")}`;
    }

    renderGroundTruth(
        selectedCase
    );

    renderAIResponse(
        selectedCase
    );

    renderEvaluationState(
        selectedCase
    );
}


// ============================================================
// GROUND TRUTH
// ============================================================

function renderGroundTruth(caseData) {

    const element =
        document.getElementById(
            "groundTruth"
        );

    if (!element) {
        return;
    }

    const groundTruth =
        caseData.ground_truth ||
        {};

    // Support both new nested API and
    // old flat API responses.
    const expectedFault =
        firstAvailable(
            groundTruth.expected_fault,
            caseData.expected_fault
        );

    const osiLayer =
        firstAvailable(
            groundTruth.osi_layer,
            caseData.expected_osi_layer
        );

    const severity =
        firstAvailable(
            groundTruth.severity,
            caseData.expected_severity
        );

    const expectedFix =
        firstAvailable(
            groundTruth.expected_fix,
            caseData.expected_fix
        );

    const concept =
        firstAvailable(
            groundTruth.concept,
            caseData.concept
        );

    element.textContent =
        "Expected Fault:\n" +
        valueOrFallback(expectedFault) +

        "\n\n" +

        "Expected OSI Layer:\n" +
        valueOrFallback(osiLayer) +

        "\n\n" +

        "Expected Severity:\n" +
        valueOrFallback(severity) +

        "\n\n" +

        "Expected Fix:\n" +
        valueOrFallback(expectedFix) +

        "\n\n" +

        "Concept:\n" +
        valueOrFallback(concept);
}


// ============================================================
// AI RESPONSE
// ============================================================

function renderAIResponse(caseData) {

    const element =
        document.getElementById(
            "aiResponse"
        );

    if (!element) {
        return;
    }

    const ai =
        caseData.ai ||
        {};

    const rootCause =
        firstAvailable(
            ai.root_cause,
            caseData.ai_root_cause
        );

    const osiLayer =
        firstAvailable(
            ai.osi_layer,
            caseData.ai_osi_layer
        );

    const confidence =
        firstAvailable(
            ai.confidence,
            caseData.ai_confidence
        );

    const severity =
        firstAvailable(
            ai.severity,
            caseData.ai_severity
        );

    const evidence =
        firstAvailable(
            ai.evidence,
            caseData.ai_evidence
        );

    const fix =
        firstAvailable(
            ai.fix,
            caseData.ai_fix
        );

    element.textContent =
        "Root Cause:\n" +
        valueOrFallback(rootCause) +

        "\n\n" +

        "OSI Layer:\n" +
        valueOrFallback(osiLayer) +

        "\n\n" +

        "Confidence:\n" +
        valueOrFallback(confidence) +

        "\n\n" +

        "Severity:\n" +
        valueOrFallback(severity) +

        "\n\n" +

        "Evidence:\n" +
        valueOrFallback(evidence) +

        "\n\n" +

        "Fix:\n" +
        valueOrFallback(fix);
}


// ============================================================
// HUMAN EVALUATION STATE
// ============================================================

function renderEvaluationState(caseData) {

    const status =
        document.getElementById(
            "status"
        );

    const notes =
        document.getElementById(
            "reviewerNotes"
        );

    const evaluation =
        caseData.evaluation ||
        "";

    const reviewerNotes =
        caseData.reviewer_notes ||
        "";

    if (notes) {

        notes.value =
            reviewerNotes;
    }

    if (status) {

        if (evaluation) {

            status.textContent =
                `Previously evaluated: ${evaluation}`;

        } else {

            status.textContent =
                "Not evaluated yet.";
        }
    }

    highlightEvaluationButton(
        evaluation
    );
}


// ============================================================
// SAVE HUMAN EVALUATION
// ============================================================

async function saveEvaluation(
    evaluation
) {

    if (!selectedCase) {

        setGlobalStatus(
            "Please select a case first."
        );

        return;
    }

    const notesElement =
        document.getElementById(
            "reviewerNotes"
        );

    const statusElement =
        document.getElementById(
            "status"
        );

    const reviewerNotes =
        notesElement
            ? notesElement.value.trim()
            : "";

    if (statusElement) {

        statusElement.textContent =
            "Saving evaluation...";
    }

    try {

        const response =
            await fetch(
                `${API_BASE}/evaluation/result`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Accept":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            case_id:
                                selectedCase.case_id,

                            evaluation:
                                evaluation,

                            reviewer_notes:
                                reviewerNotes
                        })
                }
            );

        let data;

        try {

            data =
                await response.json();

        } catch (error) {

            throw new Error(
                `Backend returned invalid JSON (HTTP ${response.status}).`
            );
        }

        console.log(
            "Evaluation save response:",
            data
        );

        if (!response.ok) {

            throw new Error(
                data.detail ||
                data.message ||
                "Failed to save evaluation."
            );
        }

        // Update frontend state.
        selectedCase.evaluation =
            evaluation;

        selectedCase.reviewer_notes =
            reviewerNotes;

        if (statusElement) {

            statusElement.textContent =
                `Saved: ${evaluation}`;
        }

        highlightEvaluationButton(
            evaluation
        );

        renderCaseList();

    } catch (error) {

        console.error(
            "Evaluation save error:",
            error
        );

        if (statusElement) {

            statusElement.textContent =
                `Error: ${error.message}`;
        }
    }
}


// ============================================================
// BUTTON HIGHLIGHT
// ============================================================

function highlightEvaluationButton(
    evaluation
) {

    const buttons =
        document.querySelectorAll(
            ".evaluation-buttons button"
        );

    buttons.forEach(
        (button) => {

            button.classList.remove(
                "selected-evaluation"
            );

            const text =
                button.textContent.trim();

            if (
                evaluation &&
                text === evaluation
            ) {

                button.classList.add(
                    "selected-evaluation"
                );
            }
        }
    );
}


// ============================================================
// STATUS
// ============================================================

function setGlobalStatus(
    message
) {

    const status =
        document.getElementById(
            "status"
        );

    if (status) {

        status.textContent =
            message;
    }
}


// ============================================================
// VALUE HELPERS
// ============================================================

function firstAvailable(
    ...values
) {

    for (
        const value of values
    ) {

        if (
            value !== undefined &&
            value !== null &&
            value !== ""
        ) {

            return value;
        }
    }

    return "";
}


function valueOrFallback(
    value
) {

    if (
        value === undefined ||
        value === null ||
        value === ""
    ) {

        return "Not available";
    }

    if (
        Array.isArray(value)
    ) {

        return value.join(
            " | "
        );
    }

    return String(value);
}


function getValue(
    value,
    fallback
) {

    if (
        value === undefined ||
        value === null ||
        value === ""
    ) {

        return fallback;
    }

    return String(value);
}


// ============================================================
// HTML ESCAPING
// ============================================================

function escapeHtml(
    value
) {

    if (
        value === undefined ||
        value === null
    ) {

        return "";
    }

    return String(value)
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
}