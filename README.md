# DSO 429 Homework 3: The Hourly Quiz

A GitHub Actions workflow runs every 10 minutes. Each run:

1. Downloads `questions.csv` from [FaisalXL/dso429-hourly-quiz](https://github.com/FaisalXL/dso429-hourly-quiz).
2. Finds every round that has no `answers/round-NNNN.json` yet.
3. Answers each question with a deterministic solver (`solver.py`), one rule per question template (compound interest, gross margin, break-even, settlement dates, and so on). A question that matches no known template falls through, in order, to:
   - Claude Code on a Claude subscription, if the `CLAUDE_CODE_OAUTH_TOKEN` secret is set;
   - the Claude API, if the `ANTHROPIC_API_KEY` secret is set;
   - a guess of A, which also turns the run red so the question gets fixed by hand within the three-hour window.
4. Commits the new answer files and pushes them to `main`.

A last step, `python run.py --alarm`, fails the run if any round is more than an hour old with no answer file, or if a question was guessed.

`python run.py --check` scores the solver against the practice answer keys (rounds 1–48).
