---
name: QuickFind
description: Rapid indexing and targeted multi-query search protocols.
---
# QuickFind: Speed Search Protocol

This skill enables the agent to find technical information with extreme efficiency.

## Core Instructions

1. **Parallel Queries**: When searching for complex topics, trigger multiple `search_web` calls in parallel with diverse but related queries.
2. **Domain Targeting**: Use the `domain` parameter to restrict searches to high-authority sites (GitHub, StackOverflow, Official Docs).
3. **Snippet Extraction**: Focus on extracting executable snippets and configuration examples immediately.
4. **Recursive Search**: If initial results are vague, use the information found to perform a second, more specific "Deep Search".

### Example
Triggering 3 parallel searches for "Bybit API rate limit", "Bybit websocket latency", "Bybit Frankfurt geo-latency".
