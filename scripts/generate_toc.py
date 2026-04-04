#!/usr/bin/env python3
import os
import re
import glob

def create_anchor(heading_text):
    """Creates a GitHub-compatible markdown anchor from heading text."""
    # Convert to lowercase
    anchor = heading_text.lower()
    # Remove special characters except spaces and hyphens
    anchor = re.sub(r'[^\w\s\-]', '', anchor)
    # Replace spaces with hyphens
    anchor = re.sub(r'\s+', '-', anchor)
    return anchor

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_code_block = False
    headings = []
    toc_start_idx = -1
    toc_end_idx = -1
    first_h2_idx = -1

    # First pass: find existing boundaries, the first H2 (for injection), and extract headings
    for i, line in enumerate(lines):
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
            
        if not in_code_block:
            if line.strip() == '<!-- toc -->':
                toc_start_idx = i
            elif line.strip() == '<!-- toc stop -->':
                toc_end_idx = i
            
            # Match ## or ### heading
            match = re.match(r'^(#{2,3})\s+(.+)$', line)
            if match:
                level_str = match.group(1)
                text = match.group(2).strip()
                
                # Do not include the TOC header itself
                if text.lower() == 'table of contents':
                    continue
                    
                # Mark the first H2 if not yet found
                if first_h2_idx == -1 and len(level_str) == 2:
                    first_h2_idx = i
                
                headings.append((len(level_str), text))

    if not headings:
        print(f"Skipping {filepath}: No H2/H3 headings found.")
        return

    # Check if we have an injection point
    if toc_start_idx == -1 and first_h2_idx == -1:
        print(f"Skipping {filepath}: Could not determine injection point (no H2 found).")
        return

    # Build the TOC text
    toc_lines = ['<!-- toc -->\n', '## Table of Contents\n\n']
    for level, text in headings:
        indent = '  ' if level == 3 else ''
        anchor = create_anchor(text)
        toc_lines.append(f"{indent}- [{text}](#{anchor})\n")
    toc_lines.append('\n<!-- toc stop -->\n')

    # Replace or insert
    if toc_start_idx != -1 and toc_end_idx != -1 and toc_start_idx < toc_end_idx:
        # Replace existing TOC
        new_lines = lines[:toc_start_idx] + toc_lines + lines[toc_end_idx+1:]
    else:
        # Insert before first H2
        # Ensure there's a blank line before the TOC if there isn't one already
        if first_h2_idx > 0 and lines[first_h2_idx - 1].strip() != '':
            toc_lines.insert(0, '\n')
        # Add a blank line after the TOC block
        toc_lines.append('\n')
        new_lines = lines[:first_h2_idx] + toc_lines + lines[first_h2_idx:]

    # Write back if changed
    if new_lines != lines:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Updated TOC in {filepath}")
    else:
        print(f"No changes needed for {filepath}")

if __name__ == '__main__':
    search_pattern = '/Users/sanjeevmurthy/le/repos/le-linux/linux-notes/**/*.md'
    md_files = glob.glob(search_pattern, recursive=True)
    
    if not md_files:
        print("No markdown files found!")
        
    for md_file in md_files:
        process_file(md_file)
