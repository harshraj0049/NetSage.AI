# NetSage AI

> AI-assisted network troubleshooting for Cisco / Packet Tracer environments.

NetSage AI helps diagnose network connectivity problems using a combination of:

* Cisco command evidence
* Deterministic rule-based checks
* LLM reasoning
* Additional evidence requests
* Human-in-the-loop review

Instead of relying on an LLM to guess the cause of a network problem, NetSage first processes the available evidence and provides the AI with structured findings.

---

## How It Works

```text
Symptom + Evidence
        ↓
 Evidence Parser
        ↓
 Deterministic Rule Checker
        ↓
      LLM
     ↙   ↘
More      Diagnosis
Evidence      ↓
     ↖     Human Review
      └──────┬──────┘
             ↓
        Final Result
```

For cases where the available evidence is insufficient, the AI can request an additional Cisco command.

Examples:

```text
show ip route
show access-lists
show vlan brief
show interfaces trunk
```

The user provides the additional output, and the same troubleshooting session continues with the newly available evidence.

---

## Human-in-the-Loop

Every final AI diagnosis goes through a human review step:

```text
Approve | Edit | Reject
```

Review decisions and corrections are recorded in the project audit history.

This ensures that the AI assists with troubleshooting while a human remains responsible for the final decision.

---

## Benchmark Dataset

The project contains **30 network troubleshooting cases (`V1_01`–`V1_30`)** covering common Cisco networking problems across multiple categories:

* Gateway
* VLAN
* DHCP
* DNS
* Routing
* ACL
* NAT
* Wireless

The benchmark cases are stored in:

```text
data/cases.csv
```

---

## Evaluation

Generated AI diagnoses are stored in:

```text
evaluation/ai_results.csv
```

Human evaluation results are stored separately in:

```text
evaluation/evaluation_results.csv
```

The evaluation interface allows each AI diagnosis to be classified as:

```text
Correct
Partially Correct
Incorrect
```

A dedicated metrics page summarizes the evaluation results and provides an overview of system performance.

---

## Project Structure

```text
netsaga/
├── api/
│   └── server.py
│
├── data/
│   └── cases.csv
│
├── evaluation/
│   ├── ai_results.csv
│   └── evaluation_results.csv
│
├── evidence/
│
├── llm_layer/
│   ├── pipeline.py
│   ├── evidence_parser.py
│   ├── rulechecker.py
│   └── case_history.jsonl
│
├── prompts/
│   └── diagnose_prompt.md
│
├── ui/
│   ├── index.html
│   ├── app.js
│   ├── evaluation.html
│   ├── evaluation.js
│   ├── metrics.html
│   └── metrics.js
│
├── requirements.txt
└── README.md
```

---

## Tech Stack

### Backend

* Python
* FastAPI
* Uvicorn

### AI / Agent

* LangChain
* LangGraph
* Human-in-the-Loop middleware

### Frontend

* HTML
* CSS
* JavaScript

---

## Running Locally

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the Model API Key

Create a `.env` file in the project root and add your model API key.

Example:

```env
MODEL_API_KEY=your_api_key_here
```

> Do not commit your `.env` file or API keys to GitHub.

### 3. Start the Backend

```bash
uvicorn api.server:app --reload
```

### 4. Start the Frontend

Open another terminal and run:

```bash
python -m http.server 5500 --directory ui
```

### 5. Open NetSage AI

Visit:

```text
http://127.0.0.1:5500/index.html
```

---

## Main Pages

### Diagnosis

```text
/index.html
```

The main interface for submitting a troubleshooting case, viewing evidence, and receiving an AI-assisted diagnosis.

### Evaluation

```text
/evaluation.html
```

Used to review generated diagnoses and classify them as:

* Correct
* Partially Correct
* Incorrect

### Metrics

```text
/metrics.html
```

Displays evaluation statistics and summarizes overall system performance.

---

## Troubleshooting Workflow

A typical NetSage session follows this process:

```text
1. User provides network symptom
          ↓
2. Cisco evidence is collected
          ↓
3. Evidence parser structures the output
          ↓
4. Deterministic rules check known conditions
          ↓
5. LLM receives structured evidence + rule findings
          ↓
6. AI produces a diagnosis
          ↓
7. AI may request additional evidence
          ↓
8. User provides requested Cisco command output
          ↓
9. Diagnosis is updated
          ↓
10. Human reviews the final result
          ↓
11. Review decision is recorded
```

This approach reduces reliance on unsupported LLM assumptions by grounding the diagnosis in observable network evidence.

---

## Evidence-Grounded Diagnosis

NetSage is designed around the principle that a network diagnosis should be supported by evidence.

For example, instead of simply asking an LLM:

```text
Why can't PC5 communicate with the network?
```

the system can provide structured evidence such as:

```text
PC5 IP: 192.168.60.5
Default Gateway: 192.168.60.10

Router Interface:
192.168.60.1

Rule Finding:
PC5 default gateway does not match the router interface
for the local subnet.
```

The AI can then reason over the observed configuration rather than attempting to guess the problem from the symptom alone.

---

## Additional Evidence Requests

When the available information is insufficient to reach a reliable conclusion, NetSage can request additional evidence.

Examples include:

```text
show ip route
show access-lists
show vlan brief
show interfaces trunk
show ip interface brief
show running-config
```

This creates an iterative troubleshooting loop:

```text
Evidence
   ↓
Analysis
   ↓
Missing Information?
   ├── No → Diagnosis
   │
   └── Yes
        ↓
 Request Additional Evidence
        ↓
 New Cisco Output
        ↓
     Re-analysis
```

---

## Human Review

NetSage keeps a human in the decision-making loop.

After the AI generates a diagnosis, the reviewer can:

```text
Approve
Edit
Reject
```

This provides two benefits:

1. It prevents the AI diagnosis from being treated as automatically authoritative.
2. It creates a record of human corrections that can be used for evaluation and future analysis.

---

## Evaluation Dataset

The benchmark is organized into individual troubleshooting cases:

```text
V1_01
V1_02
V1_03
...
V1_30
```

Each case represents a Cisco-style networking scenario with associated evidence and an expected troubleshooting outcome.

The dataset is intended to evaluate whether NetSage can:

* Identify the actual root cause
* Use network evidence correctly
* Avoid unsupported assumptions
* Request additional evidence when necessary
* Produce a technically relevant diagnosis

---

## Evaluation Results

The evaluation pipeline separates AI-generated results from human judgments.

### AI Results

```text
evaluation/ai_results.csv
```

Contains the diagnoses generated by the system.

### Human Evaluation

```text
evaluation/evaluation_results.csv
```

Contains reviewer judgments for each diagnosis.

The primary evaluation categories are:

```text
Correct
Partially Correct
Incorrect
```

The metrics interface uses these results to summarize system performance.

---

## Design Philosophy

NetSage AI follows an **evidence-first** troubleshooting approach.

The system is intentionally designed so that:

```text
Observed Evidence
       +
Deterministic Checks
       +
LLM Reasoning
       +
Human Review
       ↓
Final Diagnosis
```

The goal is not to replace a network engineer.

The goal is to build an AI-assisted workflow that makes troubleshooting faster while keeping the reasoning grounded in actual network configuration and observable Cisco command output.

---

## Project Goal

NetSage AI is designed to demonstrate an **evidence-grounded network troubleshooting workflow** in which AI assists with diagnosis while a human remains responsible for the final decision.

The project combines:

* Network troubleshooting
* Cisco / Packet Tracer environments
* Deterministic reasoning
* LLM-based analysis
* Agentic evidence collection
* Human-in-the-loop review
* Structured evaluation

---

## Academic / Prototype Disclaimer

This project is an **academic/prototype implementation** for Cisco-style network troubleshooting and evaluation.

It is intended for experimentation, demonstration, and research rather than production network operations.

---

## Author

**NetSage AI**

AI-assisted network troubleshooting for Cisco / Packet Tracer environments.
