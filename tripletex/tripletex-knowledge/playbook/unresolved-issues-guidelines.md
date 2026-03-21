# Unresolved Issues Guidelines

How to write entries for `tripletex-knowledge/unresolved-issues.md`.

## Rules

- **Log the problem with specifics.** What happened, what was expected, relevant log lines or call sequences. Vague descriptions waste the investigating agent's time.
- **Include intel that helps investigation.** Endpoint, parameters, status codes, task context, the sequence of calls that led to the problem.
- **Do NOT propose solutions or guesses.** The agent resolving the issue will figure that out. Premature solutions bias investigation and are often wrong.
- **Each issue should be self-contained.** Someone reading it cold — with no context from the conversation that found it — should understand the problem fully.
- **Remove when fixed.** After verifying a fix against the sandbox, delete the entire issue block. The file is a backlog, not a changelog.

## Template

```markdown
### <Short description of the problem>

**Found in:** <task name, log file, or conversation context>
**Observed:** <What actually happened — include endpoints, status codes, call sequences>
**Expected:** <What should have happened>
**Raw evidence:** <Relevant log lines, API responses, or call sequences>
**Review-plan called:** <yes / no — did the agent call review-plan before executing?>
**Review-plan caught it:** <yes / no / n/a — if called, did the review flag the specific inefficiency?>
```
