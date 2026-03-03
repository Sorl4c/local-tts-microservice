# Codex Models Research (2026-03-02)

## Scope
Research summary focused on:
- `gpt-5.3-codex`
- `gpt-5.2-codex`
- `gpt-5.1-codex-max`
- `gpt-5.2`
- `gpt-5.1-codex-mini`
- `gpt-5.3-codex-spark` (separate quota track in Codex UI/CLI status)

## Key Findings
1. `gpt-5.3-codex` is the strongest default for complex coding and end-to-end implementation.
2. `gpt-5.3-codex-spark` is positioned for very low latency coding interactions and short loops.
3. Spark is best used as a fast specialist/sub-agent, not as the final decision-maker for large refactors.
4. Multi-agent orchestration is officially supported in Codex CLI (experimental), enabling per-agent model assignment.
5. `codex exec` + JSON output is the practical route to automate testing/review pipelines.

## Practical Comparison
| Model | Strengths | Weaknesses | Best Use |
|---|---|---|---|
| `gpt-5.3-codex` | Best coding quality, strong planning + execution | Higher quota burn vs mini/spark | Main agent for complex tasks |
| `gpt-5.2-codex` | Solid coding baseline, stable behavior | Generally below 5.3-codex on hard tasks | Reliable fallback |
| `gpt-5.1-codex-max` | Strong deep reasoning profile | Older generation tradeoffs | Heavy analysis when preferred by team |
| `gpt-5.2` | Broad general reasoning | Less coding-specialized than codex variants | Mixed product + coding work |
| `gpt-5.1-codex-mini` | Fast/cheap | Lower ceiling on difficult coding | Repetitive edits and quick ops |
| `gpt-5.3-codex-spark` | Very fast iteration, separate quota track (in current status output) | Lower reliability on long autonomous tasks | Test runner, triage, first-pass audit |

## Real-World Community Signal (Reddit/Forums)
Observed pattern from user reports:
1. Spark is praised for speed.
2. Spark gets mixed feedback on long-horizon autonomous execution.
3. Full `gpt-5.3-codex` is generally preferred for final implementation quality.
4. Tooling/integration context (Codex CLI vs third-party wrappers) changes perceived quality a lot.

Note: community posts are anecdotal and can vary by date, rollout phase, and integration.

## Recommended Architecture for This Project
Use a 2-layer agent setup:
1. `Spark Test Agent` for fast checks: lint, targeted tests, quick bug localization, result summaries.
2. `Main Codex Agent (5.3-codex)` for final changes, architecture decisions, and release-ready output.

This aligns with your goal: preserve weekly quota while keeping implementation quality high.

## Source Links (Official)
- https://developers.openai.com/codex/multi-agent
- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/cli/reference
- https://developers.openai.com/codex/models
- https://openai.com/index/introducing-gpt-5-3-codex/
- https://openai.com/index/introducing-gpt-5-3-codex-spark/
- https://openai.com/index/introducing-gpt-5-2-codex/
- https://platform.openai.com/docs/models
- https://help.openai.com/en/articles/9624314-model-release-notes

## Source Links (Community / Anecdotal)
- https://www.reddit.com/r/codex/
- https://community.openai.com/c/codex/305
- https://www.reddit.com/r/cursor/
- https://www.reddit.com/r/GithubCopilot/

