---
name: Multi-Agent Orchestrator
description: Logic for delegating complex sub-tasks to specialized sub-agents.
---
# Orchestrator: Multi-Agent Coordination

This skill manages complexity by splitting large tasks into specialized sub-agent missions.

## Core Instructions

1. **Mission Decomposition**: Break any requested task larger than 5 files into "Workstreams".
2. **Context Passing**: When invoking `browser_subagent`, provide a "Deep State Context" containing all previous findings.
3. **Synthesis**: Collect and consolidate all sub-agent reports into a final "Executive Summary".
4. **Resiliency**: If a sub-agent fails, analyze the failure and re-invoke with "Corrective Instructions".

### Example
Triggering a `browser_subagent` to research Bybit Webhook API while simultaneously running `grep_search` on the local codebase for webhook implementations.
