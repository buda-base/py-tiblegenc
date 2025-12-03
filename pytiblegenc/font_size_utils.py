#!/usr/bin/env python3
"""
Script to simplify font size markup in txt files.
Removes noise from font size changes that are about layout rather than semantics.

This is step 1a in the processing pipeline, executed before Unicode normalization.
The goal is to reduce font size markup to only semantically meaningful changes,
preparing for step 2 where we'll convert to semantic tags like <small>, <large>, etc.

Usage:
    python3 step1_fs.py              # Process all files
    python3 step1_fs.py --test       # Run tests
    
Or import and use the simplify_font_sizes() function directly.
"""

import re
import csv
from pathlib import Path
from collections import Counter


def simplify_font_sizes(text):
    """
    Simplify font size markup by removing layout-related changes.
    
    Rules:
    1. Remove font size changes without tsheg (་) or shad (།) before next change
    2. Merge parentheses ༼ and ༽ with adjacent font sizes
    
    Args:
        text: Input text with <fs:xx> markup
        
    Returns:
        Simplified text with reduced font size markup
    """
    
    # Step 1: Parse text into segments of (font_size, content) pairs
    # Split by <fs:xx> tags
    pattern = r'<fs:(\d+)>'
    parts = re.split(pattern, text)
    
    # Build list of (font_size, content) tuples
    segments = []
    current_fs = None
    
    for i, part in enumerate(parts):
        if i % 2 == 0:
            # This is content
            if part:  # Only add non-empty content
                segments.append((current_fs, part))
        else:
            # This is a font size number
            current_fs = part
    
    if not segments:
        return text
    
    # Step 2: Process segments to handle parentheses
    # ༼ that is standalone (just "༼") should use the next font size
    # ༼ that is part of longer content should stay with current font size
    # ༽ should be merged with previous content (acts as a separator)
    processed_segments = []
    
    for i, (fs, content) in enumerate(segments):
        # Skip segments marked as processed (empty content)
        if not content:
            continue
            
        # Handle opening parenthesis ༼ - only if it's standalone
        if content == '༼' and i + 1 < len(segments):
            # Standalone ༼ followed by another segment - merge with next font size
            next_fs, next_content = segments[i + 1]
            processed_segments.append((next_fs, '༼' + next_content))
            segments[i + 1] = (None, '')  # Mark as processed
        # Handle closing parenthesis ༽
        elif content.startswith('༽') and processed_segments:
            # ༽ at start of content (after font size change) - merge with previous segment
            prev_fs, prev_content = processed_segments[-1]
            processed_segments[-1] = (prev_fs, prev_content + content)
        elif content == '༽' and processed_segments:
            # Standalone ༽ - merge with previous segment
            prev_fs, prev_content = processed_segments[-1]
            processed_segments[-1] = (prev_fs, prev_content + '༽')
        else:
            # Keep segment as is (including segments with fs=None)
            processed_segments.append((fs, content))
    
    segments = [(fs, c) for fs, c in processed_segments if c]
    
    # Step 3: Merge segments without tsheg/shad with previous segments
    merged_segments = []
    
    for i, (fs, content) in enumerate(segments):
        # Check if current content has tsheg, shad, or closing parenthesis
        # Closing parenthesis ༽ acts as a separator
        has_separator = '་' in content or '།' in content or content.endswith('༽')
        
        # If no separator and we have previous segments, merge with previous
        if not has_separator and merged_segments:
            # Merge with previous segment (use previous font size)
            prev_fs, prev_content = merged_segments[-1]
            merged_segments[-1] = (prev_fs, prev_content + content)
        # Special case: first segment that is only whitespace - keep without font size tag
        elif not has_separator and not merged_segments and not content.strip():
            merged_segments.append((None, content))
        else:
            # Has separator or first segment with non-whitespace content - keep as is
            merged_segments.append((fs, content))
    
    # Step 4: Remove consecutive segments with same font size
    final_segments = []
    for fs, content in merged_segments:
        if final_segments and final_segments[-1][0] == fs:
            # Merge with previous segment
            prev_fs, prev_content = final_segments[-1]
            final_segments[-1] = (fs, prev_content + content)
        else:
            final_segments.append((fs, content))
    
    # Step 5: Rebuild text
    result = []
    for fs, content in final_segments:
        if fs is not None:
            result.append(f'<fs:{fs}>{content}')
        else:
            # Content without font size (e.g., leading spaces before first tag)
            result.append(content)
    
    return ''.join(result)
