"""Deterministic solvers for the DSO 429 hourly quiz question templates.

solve(row) returns (letter, method): "rule" when a template matched,
"claude_code" or "api" when a Claude fallback answered, or "guess" otherwise.
"""
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta

NUM = r"\$?(-?[\d,]+(?:\.\d+)?)"
LETTERS = "ABCD"


def num(s):
    return float(s.replace(",", "").replace("$", ""))


def parse_option(s):
    """Pull the first number out of an option like '$1,234.56', '12.3%', '667 units'."""
    m = re.search(r"-?[\d,]*\.?\d+", s.replace("$", ""))
    return float(m.group(0).replace(",", "")) if m else None


def closest(value, options):
    vals = [parse_option(o) for o in options]
    best = min(range(4), key=lambda i: abs(vals[i] - value) if vals[i] is not None else float("inf"))
    return LETTERS[best]


def parse_date(s):
    return datetime.strptime(s.strip(), "%d %B %Y").date()


# Each entry: (regex, function(match) -> numeric value or date)
RULES = []


def rule(pattern):
    def deco(fn):
        RULES.append((re.compile(pattern, re.I), fn))
        return fn
    return deco


@rule(rf"An investment of {NUM} grows at {NUM}% compounded annually\. What is its value after {NUM} years\?")
def compound(m):
    p, r, n = num(m[1]), num(m[2]), num(m[3])
    return p * (1 + r / 100) ** n


@rule(rf"generates {NUM} in revenue against {NUM} in cost of goods sold\. What is the gross margin\?")
def gross_margin(m):
    rev, cogs = num(m[1]), num(m[2])
    return (rev - cogs) / rev * 100


@rule(rf"An item listed at {NUM} is discounted by {NUM}%\. What is the sale price\?")
def discount(m):
    return num(m[1]) * (1 - num(m[2]) / 100)


@rule(rf"sells {NUM} units at {NUM} each\. What is total revenue\?")
def revenue(m):
    return num(m[1]) * num(m[2])


@rule(rf"An invoice for {NUM} is converted to euros at {NUM} euros per US dollar\.")
def fx(m):
    return num(m[1]) * num(m[2])


@rule(rf"Region A had {NUM} orders averaging {NUM}; region B had {NUM} orders averaging {NUM}\.")
def weighted_avg(m):
    na, aa, nb, ab = (num(m[i]) for i in range(1, 5))
    return (na * aa + nb * ab) / (na + nb)


@rule(rf"Fixed costs are {NUM}\. Each unit sells for {NUM} with a variable cost of {NUM}\.")
def break_even(m):
    fixed, price, var = num(m[1]), num(m[2]), num(m[3])
    return round(fixed / (price - var))


@rule(rf"holds {NUM} (\w+) tickets, {NUM} (\w+) tickets and {NUM} (\w+) tickets\. .*probability it is an? (\w+) ticket\?")
def probability(m):
    counts = {m[2].lower(): num(m[1]), m[4].lower(): num(m[3]), m[6].lower(): num(m[5])}
    return counts[m[7].lower()] / sum(counts.values()) * 100


@rule(rf"moved from {NUM} to {NUM}\. What is the percentage change\?")
def pct_change(m):
    a, b = num(m[1]), num(m[2])
    return (b - a) / a * 100


@rule(rf"A {NUM} .*? is split between two channels in the ratio (\d+):(\d+)\. What does the (first|second) channel receive\?")
def ratio_split(m):
    total, a, b = num(m[1]), num(m[2]), num(m[3])
    return total * (a if m[4].lower() == "first" else b) / (a + b)


@rule(r"series runs ([\d, .-]+?)\. If the pattern continues, what is the next value\?")
def next_in_series(m):
    xs = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", m[1])]
    diffs = {xs[i + 1] - xs[i] for i in range(len(xs) - 1)}
    if len(diffs) == 1:
        return xs[-1] + diffs.pop()
    if all(x != 0 for x in xs):
        ratios = {round(xs[i + 1] / xs[i], 9) for i in range(len(xs) - 1)}
        if len(ratios) == 1:
            return xs[-1] * ratios.pop()
    # second differences constant (quadratic)
    d1 = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    d2 = {d1[i + 1] - d1[i] for i in range(len(d1) - 1)}
    if len(d2) == 1:
        return xs[-1] + d1[-1] + d2.pop()
    raise ValueError("unknown series pattern")


@rule(r"signed on (\d{1,2} \w+ \d{4}) has a (\d+)-day settlement period\. On what date does it settle\?")
def settle_date(m):
    return parse_date(m[1]) + timedelta(days=int(m[2]))


def solve_rule(row):
    q = row["question_text"]
    options = [row[f"option_{c}"] for c in "abcd"]
    for pattern, fn in RULES:
        m = pattern.search(q)
        if not m:
            continue
        value = fn(m)
        if isinstance(value, date):
            for i, o in enumerate(options):
                try:
                    if parse_date(o) == value:
                        return LETTERS[i]
                except ValueError:
                    pass
            raise ValueError(f"computed date {value} not among options")
        return closest(value, options)
    return None


def llm_prompt(row):
    return (
        "Answer this multiple-choice business arithmetic question.\n\n"
        f"{row['question_text']}\n\n"
        f"A) {row['option_a']}\nB) {row['option_b']}\nC) {row['option_c']}\nD) {row['option_d']}\n\n"
        "Work it out carefully, then end your reply with a final line of the form "
        "'ANSWER: X' where X is A, B, C, or D."
    )


def parse_letter(text):
    m = re.findall(r"ANSWER:\s*\**\(?([ABCD])\)?", text)
    return m[-1] if m else None


def solve_claude_code(row):
    """Claude Code CLI on the Pro subscription (CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`)."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") or not shutil.which("claude"):
        return None
    # Claude Code prefers ANTHROPIC_API_KEY over the OAuth token when both are set;
    # drop it so this tier really bills the subscription, not the API key.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        ["claude", "-p", llm_prompt(row), "--model", "claude-sonnet-5-5", "--effort", "medium",
         "--tools", "", "--output-format", "text"],
        env=env, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()[:300]}")
    return parse_letter(result.stdout)


def solve_api(row):
    """Messages API, billed per token (ANTHROPIC_API_KEY from console.anthropic.com)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    client = anthropic.Anthropic()
    # fallbacks="default": if Sonnet declines on a safety classifier, the API reruns the request on a fallback model.
    response = client.beta.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": llm_prompt(row)}],
    )
    if response.stop_reason == "refusal":
        return None
    return parse_letter("".join(b.text for b in response.content if b.type == "text"))


# Priority: free rules, then the Pro subscription, then the paid API key, then a guess.
TIERS = [("rule", solve_rule), ("claude_code", solve_claude_code), ("api", solve_api)]


def solve(row):
    for name, fn in TIERS:
        try:
            letter = fn(row)
            if letter:
                return letter, name
        except Exception as e:  # noqa: BLE001 - fall through to the next tier
            print(f"  {name} error r{row['round_id']} q{row['q_index']}: {e}")
    return "A", "guess"
