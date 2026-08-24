# NetSage AI

AI-assisted troubleshooting for Cisco Packet Tracer networking labs.

NetSage combines deterministic network checks with LLM-based reasoning and
Human-in-the-Loop (HITL) review to help diagnose networking faults without
automatically modifying the network.

## Architecture

```text
Packet Tracer Evidence
        ↓
Deterministic Rule Checker
        ↓
LLM Reasoning (Gemini)
        ↓
Evidence sufficient?
   ┌────┴────┐
  No        Yes
   ↓          ↓
Request      Structured
next show    Diagnosis
command         ↓
   └──────→ Human Review
              ↓
       ┌──────┼──────┐
     Accept   Edit   Reject
                       ↓
                 One AI Retry
                       ↓
                Human Takeover
                       ↓
                 Case History