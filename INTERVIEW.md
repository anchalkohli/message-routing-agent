# Interview practice: Message Routing Agent

## Run it yourself
Use Python 3.11 or 3.12. Install requirements in a virtual environment.
Run `python -m unittest discover -v`, then `streamlit run app.py`.
Manual tabs work without an API key. For genuine LLM execution set
OPENAI_API_KEY and OPENAI_MODEL to a Responses API model with function calling
available to your account. Run `python live_demo.py` before your interview.
Never commit credentials or enter employer data. API calls may cost money.

## 90-second explanation
I built a portfolio routing copilot for fictional financial message rules.
The LLM interprets natural-language requests and selects typed read-only tools.
Python loads the local CSVs, joins copy routes by region and GCN, checks
conflicts, and returns source-line evidence. The agent can use these
observations to decide its next tool call. It is bounded to five model
iterations. The UI exposes model identity, API usage, response IDs and tool
arguments/results. A separate offline deployment profile supports audited
manual review with versioned data. It does not route live payments.

## Demo sequence
1. Search NAM, DEMOUS33, MT103. Expect FININROUT line 12, GCN 0101,
   ARTRULES line 7, copy GCN 0901.
2. Ask the assistant to find that rule and review recreating it.
   Expect a lookup followed by a review returning Duplicate.
3. Ask to review NAM RR1 DEMOUS55 MT103 GCN 0101.
   Expect a specific rule plus Catch-All preview.
4. Ask to review a rule without providing a GCN. Expect clarification.
5. Open the live API telemetry and tool trace. Explain that the response IDs
   and usage are returned by the provider, not fabricated by the application.

## Questions you should be able to answer
- Why agentic AI? The model chooses tools based on observed results; the
  application manages the loop and enforces its maximum iterations.
- Why not use the LLM for validation? Routing constraints are deterministic;
  Python is reproducible, testable and does not hallucinate policy.
- Why function calling instead of RAG? The records and operations are
  structured. Exact field matching is appropriate; vector retrieval is not
  needed for exact BIC/GCN rules. RAG could help with unstructured manuals.
- What is state? The question, model messages, calls and tool results within
  one run. Cross-turn persistent memory is not implemented.
- How do you prevent unauthorized changes? Only lookup and preview tools
  are exposed. No write/deploy tool exists. Production mode disables hosted AI.
- What if a provider fails? The HTTP client times out, reports errors and
  never modifies routing files. Five iterations limits repeated calls.
- How do you evaluate an agent? Unit tests with mocked model responses,
  expected evidence and tool sequences; a separate live smoke test. Add
  multiple live trials for tool accuracy, latency, token cost and refusal cases.
- Why no LangGraph? The current explicit loop is small and transparent.
  LangGraph becomes useful for persistent state, branching and checkpoints;
  it is not part of this implementation.
- Is it production ready? No. Real file formats, routing semantics, access
  control, approval workflow, live evaluation and security review are pending.

## Resume (after successful live smoke test)
Built a Python/Streamlit LLM routing copilot using OpenAI Responses API,
dynamic function calling, file-backed rule retrieval, deterministic conflict
validation and observable execution traces; designed an offline audited
review profile with checksum-verified data releases.
