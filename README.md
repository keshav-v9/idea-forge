# idea-forge

Find a startup idea, then try to kill it before you spend three months on it.

1. **Brainstorm.** Four idea-generation methods (reverse brainstorming, role storming, SCAMPER, mind map) each propose ideas tailored to *your* background and constraints. A curation pass merges duplicates.
2. **Shortlist.** You pick the ones that interest you.
3. **Brief.** Each pick is expanded into a one-page brief using Six Thinking Hats and Starbursting.
4. **Council.** Several different LLMs independently assess each brief (with instructions to be skeptical), anonymously critique each other, and a chairman model writes a ruling with a GO / MAYBE / NO-GO verdict, the top reasons it could fail, and the cheapest test to run.
5. **Report.** Everything lands in `runs/<timestamp>-<name>/report.md` (plus `session.json` so you can re-run the council later).

Python 3.10+, standard library only. One API key (OpenRouter) covers every model.

## Setup

```bash
cp .env.example .env          # then paste your OpenRouter key (https://openrouter.ai/keys)
python -m ideaforge check     # confirms the key and that the configured model IDs exist
```

Model IDs change often. If `check` reports a MISSING model, set valid IDs in `.env`
(`IDEAFORGE_COUNCIL_MODELS`, `IDEAFORGE_CHAIRMAN`, `IDEAFORGE_BRAINSTORM_MODEL`).

## Use

```bash
python -m ideaforge run                      # full interactive flow
python -m ideaforge run --profile me.txt     # skip the questions; me.txt = your background/interests/constraints
python -m ideaforge run --methods reverse,role-storm --per-method 8
python -m ideaforge run --mock               # no key, no cost: fake model, to see how the flow works

python -m ideaforge brainstorm               # only stage 1; saves a session
python -m ideaforge council runs/<dir> --pick 2,5   # run (or re-run) the council on other ideas from a saved session
```

Tips for good output:
- Be specific in your profile. "CS + econ student who works on low-latency trading systems and hates manual reporting" beats "I like tech".
- Say what you do **not** want to build. It prunes a lot of noise.
- Read the council's "where the panel disagreed" section first. That is usually the real risk.

## Web UI

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[ui]"
streamlit run streamlit_app.py
```

The UI also lets you revise the idea list with plain-language feedback and choose which specialists review each idea.

## Saved data

Everything stays in `runs/`, which git ignores: `runs/<timestamp>-<name>/` holds each idea list, brief, revision request, and report; `runs/calls/` logs every prompt and model response as it arrives; `runs/profile.json` remembers your last profile. Open past runs from the app's sidebar.

## Specialists

Besides the general council, eight agents each examine one angle: long-term growth and market feasibility, customer demand, competition, unit economics, go-to-market, technical feasibility, legal risk, and founder fit. The chairman weighs their reports in the ruling.

## Cost

Per shortlisted idea the council makes `2 x (council size) + (specialists) + 1` calls (17 with the default 4 models and all 8 specialists), plus one call for the overall recommendation. Brainstorming is about 5 calls and each brief is one. A typical run with 3 shortlisted ideas is roughly 60 calls. Expect a few dollars at most, depending on the models you choose. Check pricing on OpenRouter.

## Limits

- The council catches weak reasoning, crowded markets, and missing pieces. It **cannot tell you whether people will pay.** An idea that survives the council still needs about 10 conversations with real customers before you build anything.
- LLMs lean agreeable; the prompts push against that, but treat a GO as "worth a cheap test", never "build it".
- Models can hallucinate competitors or numbers. Verify anything you act on.

## Develop

```bash
pip install pytest && pytest -q
```
Tests run against a deterministic mock model (no network).

## Credits

Inspired by [Azzedde/brainstormers](https://github.com/Azzedde/brainstormers) (structured brainstorming methods) and [karpathy/llm-council](https://github.com/karpathy/llm-council) (independent answers, anonymized peer review, chairman synthesis). Neither repository ships a license file, so **no code or prompt text was copied**: everything here is original, and only the general ideas (public brainstorming techniques and the 3-stage council pattern) are shared.
