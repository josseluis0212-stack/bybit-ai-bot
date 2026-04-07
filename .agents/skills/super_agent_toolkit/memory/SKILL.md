---
name: DeepMemory
description: Contextual navigation of Knowledge Items (KIs) and conversation logs.
---
# DeepMemory: Contextual Archeology

This skill enables the agent to perfectly recall project history.

## Core Instructions

1. **KI First**: Before starting any recurring task (e.g. "Add a field"), check `knowledge/` for existing patterns.
2. **Log-Diving**: If the user says "Like we did before", search the `brain/` logs for the specific conversation ID.
3. **Cross-Session Retrieval**: Use `read_url_content` or similar local tools to ingest past `walkthrough.md` files for state restoration.
4. **Knowledge Retention**: After a complex fix, update the relevant `KI` (Knowledge Item) to preserve the findings.

### Example
Recalling how the Bybit API was authenticated in Conversation `7b729fe7` to fix an authentication error in the current session.
