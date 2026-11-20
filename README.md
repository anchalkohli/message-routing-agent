# Message Routing Agent

A personal portfolio prototype that investigates message-routing configuration and reviews proposed rules. The CLI ships with fictional FININROUT and ARTRULES records. It reads demo records and produces previews in memory.

## Start in PyCharm

Open this folder as a project. Select Python 3.10 or later. In the PyCharm terminal, run:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

The app starts with bundled sample files and works without an API key for rule search and draft review. To exercise the command line and test suite, run:

```bash
python routing_agent.py --demo
python -m unittest -v
```

The tests include a simulated model that requests a lookup, reads the result, and uses it to request a rule review.

## Read files from a local directory

Set `ROUTING_DATA_DIR` to the full directory path in the PyCharm run configuration or in the terminal that starts Streamlit. For example:

```bash
export ROUTING_DATA_DIR="/path/to/routing-data"
```

PowerShell uses `$env:ROUTING_DATA_DIR = 'C:\routing-data'`. In the app, choose **Local directory** in the sidebar. The folder is on the computer running Streamlit. **Reload files** refreshes the data after a local change.

| File | UTF-8 CSV headers in order |
| --- | --- |
| `fininrout.csv` (required) | `region,rule_type,bic,message_type,gcn,sender,action` |
| `artrules.csv` (optional) | `region,gcn,copy_gcn` |

Each FININROUT record accepts one message type or inclusive range. Search and draft review also accept comma-separated values. Use uppercase region and BIC, preserve four-digit demo GCNs as text, and supply an action such as `rtecode`. Each file supports up to 2 MB. See `samples/` for exact examples. Copy routing joins by region and Destination GCN. A missing ARTRULES file displays **Unavailable**. Physical line references and original CSV records are preserved.

Use the documented portfolio CSV schema or adapt `routing_files.py` to your internal parser. The proprietary positional FININROUT and ARTRULES formats need their own mappings.

## Explore the workspace

- **Rule search** filters by selected region, destination BIC, message type or range, sender BIC and Destination GCN. Select a result to inspect the FININROUT and ARTRULES evidence side by side. The wildcard checkbox includes rules that span MT100–999 in a message type search.
- **Draft review** checks the whole request for duplicate, overlap or shadow conflicts. An eligible new RR1/RR2 destination BIC gets one Catch-All draft after the specific rules. A clean proposal can be downloaded as a draft CSV with a suggested insertion anchor. This anchor uses the first fallback for an existing BIC when present, the nearest message type for other existing BICs, or the last regional record for a new BIC. The local input files are read-only.
- **Routing assistant** uses bundled fictional rules. The hosted model can choose tools and the interface displays the tools' actual responses. Local directory files stay on the app server and are excluded from model inputs.

## Enable model tool calling

Use a personal environment with access to the OpenAI API. Set `OPENAI_API_KEY` and `OPENAI_MODEL` as environment variables in your PyCharm run configuration or terminal. Open the **Routing assistant** tab or use the CLI example below. Choose a model available to your API project that supports Responses API function calling. Keep the API key out of source control and shared run configurations. Requests and tool evidence go to the hosted API, so enter fictional data only.

[OpenAI function calling documentation](https://developers.openai.com/api/docs/guides/function-calling)

```bash
python routing_agent.py "Find the NAM MT103 route for DEMOUS33 and its copy routes. Then check what would happen if we recreated that specific rule with the same GCN."
```

Expected evidence for the two-step demo: FININROUT line 12 matches, ARTRULES line 7 defines a copy route, and recreating the specific rule is blocked as a duplicate. The result includes the tool trace so you can verify the model's summary.

| Try this prompt | Expected evidence |
| --- | --- |
| Find the NAM route for DEMOUS33 and MT103. Include wildcard rules. | FININROUT lines 12, 14 and 21. The RR1RRC at line 21 is a wildcard interval and is not classified as Catch-All. |
| Review adding a NAM RR1 for DEMOUS33 MT204 to GCN 0202. | Duplicate at FININROUT line 13. |
| Review adding a NAM RR1 for DEMOUS55 MT103 to GCN 0101. | Specific rule followed by a Catch-All preview. |
| Review adding a NAM route for DEMOUS55 MT103. | Clarifying question for rule type and GCN. |

## What to explain in an interview

**Where is the agentic behaviour?** The model selects from two structured tools and can use an earlier result to decide what to call next. Python validates arguments and calculates routing results. The trace captures the actual evidence behind the answer.

**Why cap the loop?** A limit of five model rounds bounds the number of requests even if the model keeps asking for another tool. The handler allowlist restricts it to retrieval and in-memory rule review.

**Why is the trace important?** A generated summary can make a mistake. The trace shows the exact source line and validation result that the Python tools returned.

**What would you add for the internal version?** Wire the tools to the existing regional parsers, validator and Streamlit view in the company environment. Validate real column mappings, rule precedence, and editor insertion behaviour there. The demo schema models one optional sender condition and emits structured previews. Synthetic line numbers are fixture attributes. Real file parsing, production rule serialization, and deployment are outside this prototype.

## Résumé bullet after you have run and explained the live-model demo

> Developed a Python-based agentic AI prototype for SWIFT routing-rule analysis, using LLM function calling to retrieve routing and copy-routing evidence and deterministic validation to identify duplicate, overlapping and shadowed rules with source-line references.

## Move the project to Git

Extract the ZIP and copy this folder into a new repository. Commit the bundled sample CSVs, Python files, tests, README, requirements and Streamlit theme. Keep operational CSVs in a separate local directory. The included ignore rules cover common local credentials and virtual environments.

## Production deployment

Set `ROUTING_MODE=production`, `ROUTING_DATA_DIR` to the active release directory, and `ROUTING_AUDIT_DB` to an absolute SQLite file path. Use the [Linux deployment runbook](deploy/README.md) for a configured systemd service, publishing and rolling back releases, readiness checks, access and audit recovery.

Production mode opens only the local search and draft-review workspace. The hosted assistant remains available in the demo profile with fictional data. The production input adapter currently expects the documented normalized CSV schema. Verify your internal mappings, real routing precedence and infrastructure access controls before deployment.
