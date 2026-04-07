---
name: Parallel Executor
description: Multi-tasking and parallel execution of tool calls.
---
# Parallelism: Multi-Tasking Agent

This skill maximizes performance by executing non-sequential tasks together.

## Core Instructions

1. **Independent Branching**: If a task requires research and local analysis, trigger both `search_web` and `grep_search` in the same turn.
2. **Backgrounding**: Use `run_command` for long-running scripts (e.g. `npm run build`) while continuing unrelated work.
3. **Safety First**: Never run two modifying tool calls (like `replace_file_content`) on the same file in parallel.
4. **Synchronization**: After parallel tasks finish, use a single synthesis step to align results.

### Example
Running `python main.py` in the background while monitoring Render logs via `browser_subagent`.
