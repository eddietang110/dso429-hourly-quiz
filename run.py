"""Fetch questions.csv, answer every round that has no answer file yet, write answers/round-NNNN.json.

Usage:
  python run.py            # answer unanswered rounds
  python run.py --check    # score solver against practice_keys.csv (no files written)
  python run.py --alarm    # exit 1 if a round is >60 min old with no answer, or a question was guessed
"""
import csv
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from solver import solve

BASE = "https://raw.githubusercontent.com/FaisalXL/dso429-hourly-quiz/main/"
ANSWERS = Path(__file__).parent / "answers"
GUESS_LOG = Path(__file__).parent / "guesses.log"


def fetch_csv(name):
    req = urllib.request.Request(BASE + name, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def group_rounds(rows):
    rounds = defaultdict(list)
    for r in rows:
        rounds[int(r["round_id"])].append(r)
    return rounds


def check():
    rounds = group_rounds(fetch_csv("questions.csv"))
    keys = {(int(k["round_id"]), int(k["q_index"])): k["answer"] for k in fetch_csv("practice_keys.csv")}
    right = total = 0
    methods = defaultdict(int)
    for rid in sorted(rounds):
        for row in rounds[rid]:
            key = keys.get((rid, int(row["q_index"])))
            if key is None:
                continue
            letter, method = solve(row)
            methods[method] += 1
            total += 1
            if letter == key:
                right += 1
            else:
                print(f"WRONG r{rid} q{row['q_index']}: got {letter}, key {key} | {row['question_text']}")
    print(f"{right}/{total} correct ({right / total:.2%}); methods: {dict(methods)}")
    return right == total


def main():
    ANSWERS.mkdir(exist_ok=True)
    rounds = group_rounds(fetch_csv("questions.csv"))
    written, guessed = [], []
    for rid in sorted(rounds):
        path = ANSWERS / f"round-{rid:04d}.json"
        if path.exists():
            continue
        rows = sorted(rounds[rid], key=lambda r: int(r["q_index"]))
        answers, methods = {}, defaultdict(int)
        for row in rows:
            letter, method = solve(row)
            answers[f"q{int(row['q_index'])}"] = letter
            methods[method] += 1
            if method == "guess":
                guessed.append(f"round {rid} q{row['q_index']}: {row['question_text']}")
        path.write_text(json.dumps({"round_id": rid, "answers": answers}, indent=2) + "\n")
        written.append(rid)
        print(f"round {rid}: {len(answers)} answers, {dict(methods)}")
    print(f"wrote {len(written)} round(s): {written}" if written else "nothing new")
    if guessed:
        GUESS_LOG.write_text("\n".join(guessed) + "\n")


def alarm(max_minutes=60):
    """Fail if any round released more than max_minutes ago has no answer file,
    or if this run had to guess on any question (an unknown template)."""
    now = datetime.now(timezone.utc)
    problems = []
    for rid, rows in sorted(group_rounds(fetch_csv("questions.csv")).items()):
        released = datetime.fromisoformat(rows[0]["released_at"].replace("Z", "+00:00"))
        age = (now - released).total_seconds() / 60
        if age > max_minutes and not (ANSWERS / f"round-{rid:04d}.json").exists():
            problems.append(f"OVERDUE: round {rid} released {age:.0f} min ago, no answer file")
    if GUESS_LOG.exists():
        problems += ["GUESSED (unknown question type): " + line for line in GUESS_LOG.read_text().splitlines()]
    for p in problems:
        print(p)
    print("all clear" if not problems else f"{len(problems)} problem(s)")
    return not problems


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    elif "--alarm" in sys.argv:
        sys.exit(0 if alarm() else 1)
    else:
        main()
