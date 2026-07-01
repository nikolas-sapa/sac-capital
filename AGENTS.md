# AGENTS.md — Agent workflow instructions for sapa_fund

## Pipeline Execution

### Canonical command
```bash
set -a; source .env; set +a; uv run python runner_equities.py
```

### Environment setup requirement
Before executing the runner, the `.env` file must be sourced to export configuration variables into the process environment. The pattern `set -a; source .env; set +a` ensures:
- `set -a`: Mark all subsequent variables as auto-export
- `source .env`: Load and export variables from `.env`
- `set +a`: Return to normal export behavior
- Pipeline script receives all required config

Omitting this step will cause the script to fail with missing configuration errors.

### Execution flow (default)
Running the canonical command without flags executes:
1. **Screening phase**: Evaluates equities against selection criteria
2. **Analyst phase**: LLM-powered analysis of passed securities

### Available operational flags

| Flag | Purpose | Behavior |
|---|---|---|
| `--no-analyse` | Skip LLM analysis | Runs screening only; stops after evaluation |
| `--mark-only` | Mark-to-market operations | Performs only position mark-to-market and exit recording; skips screening and analysis |
| `--reconcile-only` | Broker reconciliation | Runs only broker account reconciliation |
| `--dry-run` | Simulation mode | Executes all logic without writing to ledger, forward-tracker, or broker systems |
| `--checkpoint` | Resume from checkpoint | Reuses previously validated LLM stage checkpoints (useful after analysis interruption) |
| `--clear-analysis-checkpoints` | Reset analysis state | Clears saved checkpoints before running to force re-analysis |

### Natural language interpretation rules
When agents encounter user instructions like:
- "run the pipeline"
- "run the bot"
- "run equities"
- "execute the screening"
- "analyze the portfolio"

**Map to:** `set -a; source .env; set +a; uv run python runner_equities.py [optional flags]`

If the user specifies additional modifiers (dry-run, skip analysis, etc.), append the corresponding flags from the table above.

### Command examples

```bash
# Full pipeline: screening + LLM analysis
set -a; source .env; set +a; uv run python runner_equities.py

# Screening only, no LLM analysis
set -a; source .env; set +a; uv run python runner_equities.py --no-analyse

# Simulation: full pipeline without any writes
set -a; source .env; set +a; uv run python runner_equities.py --dry-run

# Simulation + screening only (no analysis, no writes)
set -a; source .env; set +a; uv run python runner_equities.py --dry-run --no-analyse

# Mark-to-market and exit recording only
set -a; source .env; set +a; uv run python runner_equities.py --mark-only

# Broker reconciliation only
set -a; source .env; set +a; uv run python runner_equities.py --reconcile-only

# Resume analysis from last checkpoint
set -a; source .env; set +a; uv run python runner_equities.py --checkpoint

# Reset analysis checkpoints and re-run full pipeline
set -a; source .env; set +a; uv run python runner_equities.py --clear-analysis-checkpoints
```

### Exit behavior
The runner processes until completion or error. Check exit code for success:
- `0`: Success
- Non-zero: Error (check logs for details)

### Debugging
If the runner fails:
1. Verify `.env` exists and is readable
2. Confirm `uv` and Python environment are properly configured
3. Check logs for stage-specific errors
4. Use `--dry-run` to test without side effects
