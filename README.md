# DSO 429 Homework 3: The Hourly Quiz

A GitHub Actions workflow runs every 10 minutes. Each run:

1. Downloads `questions.csv` from [FaisalXL/dso429-hourly-quiz](https://github.com/FaisalXL/dso429-hourly-quiz).
2. Finds every round that has no `answers/round-NNNN.json` yet.
3. Answers each question with a deterministic solver (`solver.py`), one rule per question template (compound interest, gross margin, break-even, settlement dates, and so on). If a question matches no known template, it falls back to Claude when an `ANTHROPIC_API_KEY` secret is configured.
4. Commits the new answer files and pushes them to `main`.

`python run.py --check` scores the solver against the practice answer keys (rounds 1–48).
