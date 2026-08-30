async function loadMetrics() {

    try {

        const response =
            await fetch(
                "http://127.0.0.1:8000/metrics"
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.detail ||
                "Could not load metrics."
            );
        }


        renderCards(data);

        renderAgreement(data);

        renderCategoryTable(data);

        renderSeverityTable(data);

    }

    catch (error) {

        document.body.innerHTML +=
            `
            <div style="
                padding:20px;
                color:red;
            ">
                Error loading metrics:
                ${error.message}
            </div>
            `;
    }
}


/* ============================================================
   SUMMARY CARDS
   ============================================================ */

function renderCards(
    data
) {

    const container =
        document.getElementById(
            "cards"
        );


    const cards = [

        {
            title: "Total Cases",
            value:
                data.total_cases
        },

        {
            title: "AI Results",
            value:
                data.ai_results
        },

        {
            title: "Evaluated",
            value:
                data.evaluated_cases
        },

        {
            title: "Pending Evaluation",
            value:
                data.unevaluated_generated_cases
        },

        {
            title: "Correct",
            value:
                data.correct
        },

        {
            title: "Partially Correct",
            value:
                data.partial
        },

        {
            title: "Incorrect",
            value:
                data.incorrect
        },

    ];


    container.innerHTML =
        cards.map(
            card => `

                <div class="card">

                    <h3>
                        ${card.title}
                    </h3>

                    <div class="number">
                        ${card.value}
                    </div>

                </div>

            `
        ).join("");
}


/* ============================================================
   AGREEMENT
   ============================================================ */

function renderAgreement(
    data
) {

    const percentage =
        (
            data.agreement_rate
            *
            100
        ).toFixed(1);


    document.getElementById(
        "agreement"
    ).innerHTML = `

        <div
            style="
                font-size:42px;
                font-weight:bold;
            "
        >
            ${percentage}%
        </div>

        <p>
            Correct / evaluated cases.
        </p>

        <div class="bar">

            <div
                class="bar-fill"
                style="
                    width:${percentage}%;
                "
            ></div>

        </div>

    `;
}


/* ============================================================
   CATEGORY TABLE
   ============================================================ */

function renderCategoryTable(
    data
) {

    const entries =
        Object.entries(
            data.by_category
        );


    if (!entries.length) {

        document.getElementById(
            "categoryTable"
        ).innerHTML =
            "<p>No evaluations yet.</p>";

        return;
    }


    let html = `

        <table>

            <thead>

                <tr>

                    <th>Category</th>
                    <th>Total</th>
                    <th>Correct</th>
                    <th>Partial</th>
                    <th>Incorrect</th>
                    <th>Agreement</th>

                </tr>

            </thead>

            <tbody>

    `;


    entries.forEach(
        ([category, values]) => {

            const agreement =
                values.total
                    ? (
                        values.correct
                        /
                        values.total
                        *
                        100
                    ).toFixed(1)
                    : "0.0";


            html += `

                <tr>

                    <td>
                        ${category}
                    </td>

                    <td>
                        ${values.total}
                    </td>

                    <td>
                        ${values.correct}
                    </td>

                    <td>
                        ${values.partial}
                    </td>

                    <td>
                        ${values.incorrect}
                    </td>

                    <td>
                        ${agreement}%
                    </td>

                </tr>

            `;
        }
    );


    html += `

            </tbody>

        </table>
    `;


    document.getElementById(
        "categoryTable"
    ).innerHTML =
        html;
}


/* ============================================================
   SEVERITY TABLE
   ============================================================ */

function renderSeverityTable(
    data
) {

    const entries =
        Object.entries(
            data.by_severity
        );


    if (!entries.length) {

        document.getElementById(
            "severityTable"
        ).innerHTML =
            "<p>No evaluations yet.</p>";

        return;
    }


    let html = `

        <table>

            <thead>

                <tr>

                    <th>Severity</th>
                    <th>Total</th>
                    <th>Correct</th>
                    <th>Partial</th>
                    <th>Incorrect</th>

                </tr>

            </thead>

            <tbody>

    `;


    entries.forEach(
        ([severity, values]) => {

            html += `

                <tr>

                    <td>
                        ${severity}
                    </td>

                    <td>
                        ${values.total}
                    </td>

                    <td>
                        ${values.correct}
                    </td>

                    <td>
                        ${values.partial}
                    </td>

                    <td>
                        ${values.incorrect}
                    </td>

                </tr>

            `;

        }
    );


    html += `

            </tbody>

        </table>
    `;


    document.getElementById(
        "severityTable"
    ).innerHTML =
        html;
}


/* ============================================================
   START
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    loadMetrics
);