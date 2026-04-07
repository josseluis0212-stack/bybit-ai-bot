---
name: DeepDive Researcher
description: Systematic website navigation and automated data extraction.
---
# DeepDive: Advanced Web Research

This skill enables the agent to act as a specialized human researcher.

## Core Instructions

1. **Breadth-First Navigation**: Start by finding the `index` or `documentation sitemap` of a target library.
2. **Keyterm Isolation**: Identify specific keywords or API endpoints and use `read_browser_page` on their specific documentation.
3. **Drafting Local Specs**: As information is found, create a local `spec.md` or `api_reference.md` to prevent context loss.
4. **Validation**: Always cross-reference instructions from different sources (e.g. Bybit Python SDK vs. Official REST API Docs).

### Example
Finding and documenting all Bybit Linear Perpetual error codes from their Github and official support portal.
