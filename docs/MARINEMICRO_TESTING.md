# MarineMicro Testing on Windows

This guide describes how to test the Jev player against the MarineMicro map on Windows with a real StarCraft II installation.

## Prerequisites

1. **StarCraft II** installed via Battle.net
2. **Python 3.12+** with uv package manager
3. **OpenRouter API key** with access to the Jev model

## Setup

1. Configure StarCraft II to enable the API:
   - Open Battle.net
   - Go to StarCraft II → Settings → Game Settings
   - Under **Additional command line arguments**, add:
     ```
     -listen 127.0.0.1 -port 5001 -displayMode 0
     ```
   - Click **Play** to launch SC2 with API enabled

2. Install Python dependencies:
   ```bash
   uv sync
   ```

3. Set up your OpenRouter API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENROUTER_API_KEY
   ```

4. Fetch the MarineMicro map (if not already present):
   ```bash
   uv run python scripts/fetch_map.py
   ```

## Running MarineMicro Tests

The MarineMicro map is a simple combat scenario with Marines vs. a computer opponent. This is ideal for testing combat policy improvements.

### Basic Run

```bash
uv run python -m jev_sc2 --attach --map maps/MarineMicro.SC2Map --opponent
```

### With Custom Parameters

```bash
# Longer time limit and more calls for thorough evaluation
uv run python -m jev_sc2 --attach --map maps/MarineMicro.SC2Map --opponent --seconds 300 --max-calls 500

# With camera following for visual inspection
uv run python -m jev_sc2 --attach --map maps/MarineMicro.SC2Map --opponent --follow-camera

# Custom decision age window
uv run python -m jev_sc2 --attach --map maps/MarineMicro.SC2Map --opponent --max-age-loops 64
```

### Parameters Explained

- `--attach`: Connects to an already-running SC2 process (launched via Battle.net)
- `--map`: Path to the map file (MarineMicro.SC2Map)
- `--opponent`: Adds a VeryEasy Zerg AI opponent (required for MarineMicro)
- `--seconds`: Maximum runtime in seconds (default: 180)
- `--max-calls`: Maximum number of Jev decision calls (default: 300)
- `--max-age-loops`: Discard decisions older than this many game loops (default: 64)
- `--follow-camera`: Camera follows combat action (visual only, doesn't affect decisions)

## Checking Results

After a run completes, check the latest run directory under `runs/`:

```bash
# View the result summary
cat runs/<timestamp>/result.json

# Generate a detailed report
uv run python scripts/report.py
```

Key metrics to check:
- **status**: `victory`, `defeat`, or `incomplete`
- **calls**: Number of Jev decisions made
- **cost_usd**: API cost for the run
- **actions_submitted**: Number of commands sent to SC2
- **replay**: Path to the saved replay file (if available)

## Interpreting Results

### Expected Behavior (After Improvements)

With the combat policy improvements:
- Continue should NOT dominate choices when units are idle and enemies are nearby
- Combat actions should be highlighted with `[COMBAT]` prefix
- Units should actively engage enemies rather than staying idle
- Actions should be submitted throughout the match, not just at the start

### Common Issues

1. **"No owned units observed for ninety seconds"**: Game ended but result wasn't detected
2. **Many stale decisions**: Decisions took too long, increase `--max-age-loops`
3. **High continue choice count**: Check that idle-continue filtering is working
4. **Zero submissions after early game**: Units may have all died; check replay

## Running Tests

To run the unit tests for combat improvements:

```bash
uv run pytest tests/test_combat_improvements.py -v
```

To run all tests:

```bash
uv run pytest tests/ -v
```

## Comparing Results

To compare performance before and after changes:

1. Baseline run on main branch
2. Note key metrics (actions_submitted, continue choices, survival time)
3. Switch to feature branch
4. Run multiple trials
5. Compare metrics and replay outcomes

Track in particular:
- Ratio of attack actions to continue choices
- Number of actions submitted per game loop
- Final unit count (survival)
- Game outcome (victory/defeat)
