"""CSV import and batch review for the documented portfolio schema."""
import csv
from dataclasses import dataclass
import io
from pathlib import Path
import re

from routing_agent import REGIONS, RULE_TYPES, Rule, is_bic, review_rule

ROUTE_COLUMNS = ("region", "rule_type", "bic", "message_type", "gcn", "sender", "action")
COPY_COLUMNS = ("region", "gcn", "copy_gcn")
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class RoutingFiles:
    rules: tuple
    copies: dict | None
    route_source: dict
    copy_source: dict


def message_intervals(value):
    """Accept MT103, 100 TO 199, 100-199, 100:199 and comma-separated lists."""
    if not value.strip():
        return ()
    intervals = []
    for token in value.split(","):
        match = re.fullmatch(
            r"\s*(?:MT\s*)?([1-9][0-9]{2})(?:\s*(?:TO|-|:)\s*(?:MT\s*)?([1-9][0-9]{2}))?\s*",
            token, re.IGNORECASE,
        )
        if not match:
            raise ValueError(f"Invalid message type or range: {token.strip()!r}.")
        first = int(match[1])
        last = int(match[2] or match[1])
        if first > last:
            raise ValueError("Each message type range must start at or below its end.")
        intervals.append((first, last))
    return tuple(intervals)


def records(data, columns, label):
    if len(data) > MAX_BYTES:
        raise ValueError(f"{label} exceeds the 2 MB demo limit.")
    try:
        lines = data.decode("utf-8-sig").splitlines(keepends=True)
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8 CSV.") from error
    reader = csv.reader(lines, strict=True)
    header = next(reader, None)
    if header is None or tuple(field.strip() for field in header) != columns:
        raise ValueError(f"{label} header must be: {', '.join(columns)}")
    while True:
        line = reader.line_num + 1
        row = next(reader, None)
        if row is None:
            return
        if not row or not any(field.strip() for field in row):
            continue
        if len(row) != len(columns):
            raise ValueError(f"{label} line {line}: expected {len(columns)} fields.")
        raw = "".join(lines[line - 1:reader.line_num]).rstrip("\r\n")
        yield line, tuple(field.strip() for field in row), raw


def valid_gcn(value):
    return bool(re.fullmatch(r"[0-9]{4}", value))


def load_routing_files(routes, copies=None):
    rules = []
    route_source = {}
    copy_source = {}
    copy_index = {} if copies is not None else None
    try:
        for line, row, raw in records(routes, ROUTE_COLUMNS, "FININROUT"):
            region, kind, bic, mt, gcn, sender, action = row
            try:
                intervals = message_intervals(mt)
                if (region not in REGIONS or kind not in RULE_TYPES or not is_bic(bic)
                        or len(intervals) != 1 or not valid_gcn(gcn)
                        or (sender and not is_bic(sender))
                        or not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", action)):
                    raise ValueError("Check region, type, BICs, one MT interval, four-digit GCN and action.")
            except ValueError as error:
                raise ValueError(f"FININROUT line {line}: {error}") from error
            first, last = intervals[0]
            rules.append(Rule(line, region, kind, bic, first, last, gcn, sender or None, action))
            route_source[line] = raw
        if copies is not None:
            for line, (region, gcn, copy_gcn), raw in records(copies, COPY_COLUMNS, "ARTRULES"):
                if region not in REGIONS or not valid_gcn(gcn) or not valid_gcn(copy_gcn):
                    raise ValueError(f"ARTRULES line {line}: check region and four-digit GCNs.")
                copy_index.setdefault((region, gcn), []).append({"line": line, "copy_gcn": copy_gcn})
                copy_source[line] = raw
    except csv.Error as error:
        raise ValueError(f"Malformed CSV: {error}") from error
    return RoutingFiles(tuple(rules), copy_index, route_source, copy_source)


def read_csv(path):
    if not path.is_file():
        raise ValueError(f"Expected a regular CSV file at {path}.")
    try:
        with path.open("rb") as source:
            data = source.read(MAX_BYTES + 1)
    except OSError as error:
        raise ValueError(f"Could not read {path}: {error.strerror}.") from error
    if len(data) > MAX_BYTES:
        raise ValueError(f"{path.name} exceeds the 2 MB demo limit.")
    return data


def read_local_files(directory):
    folder = Path(directory).expanduser()
    if not folder.is_dir():
        raise ValueError(f"Routing file directory does not exist: {folder}")
    routes = read_csv(folder / "fininrout.csv")
    copies = folder / "artrules.csv"
    return routes, read_csv(copies) if copies.exists() else None


def review_batch(region, kind, bic, message_types, gcn, sender, rules):
    intervals = message_intervals(message_types)
    if not intervals or len(intervals) > 20:
        raise ValueError("Enter one to twenty message types or ranges.")
    ordered = sorted(intervals)
    if any(a[1] >= b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("Proposed message type ranges overlap each other.")
    findings = []
    drafts = []
    catch_all = None
    for first, last in intervals:
        result = review_rule(region, kind, bic, first, last, gcn, sender, rules=rules)
        if result["status"] == "Blocked":
            findings.extend({**finding, "requested_mt": format_mt(first, last)}
                            for finding in result["findings"])
            continue
        specific, *generated = result["draft_rules"]
        specific["insert_after_line"] = insertion_anchor(rules, region, bic, first, last)
        drafts.append(specific)
        if generated:
            catch_all = {**generated[0], "insert_after_line": specific["insert_after_line"]}
    if findings:
        return {"status": "Blocked", "findings": findings}
    if catch_all:
        drafts.append(catch_all)
    return {"status": "Preview only", "draft_rules": drafts}


def insertion_anchor(rules, region, bic, first, last):
    matches = [rule for rule in rules if rule.region == region and rule.bic == bic]
    catch_all = [rule.line for rule in matches if rule.catch_all]
    if catch_all:
        # A specific rule must precede the first eligible fallback.
        return min(catch_all) - 1
    if matches:
        closest = min(matches, key=lambda rule:
                      (max(rule.first_mt - last, first - rule.last_mt, 0), -rule.line))
        return closest.line
    return max((rule.line for rule in rules if rule.region == region), default=1)


def format_mt(first, last):
    return str(first) if first == last else f"{first} TO {last}"


def draft_csv(drafts):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow((*ROUTE_COLUMNS, "insert_after_line"))
    for rule in drafts:
        writer.writerow((rule["region"], rule["rule_type"], rule["bic"],
                         format_mt(rule["first_mt"], rule["last_mt"]), rule["gcn"],
                         rule["sender"], rule["action"], rule["insert_after_line"]))
    return output.getvalue()
