---
name: Visual Sentinel
description: Strategic screenshot and video recording for verification.
---
# Visual Sentinel: Automated Screenshot Utility

This skill ensures visual proof and walkthroughs for UI-related tasks.

## Core Instructions

1. **Before/After Comparison**: Always take a screenshot before AND after any visual change.
2. **Recording Flow**: User `browser_subagent` to record a video (`RecordingName`) for complex flows like login or form submission.
3. **Artifact Embedding**: After taking a screenshot, immediately embed it into a `walkthrough.md` with a clear caption.
4. **Resolution Management**: If content is cut off, use `browser_subagent` with `viewport` adjustments to capture the full page.

### Example
Capturing the Render Dashboard logs and the Bybit Trade Historial to visually confirm bot execution.
