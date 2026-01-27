#!/usr/bin/env python3
"""
Script to fix common datetime-related linting errors.
Run this script to fix DTZ005, DTZ007, and DTZ011 errors.
"""

import re
from pathlib import Path


def fix_datetime_now(file_path):
    """Fix DTZ005: datetime.now() without tzinfo"""
    with open(file_path, encoding='utf-8') as f:
        content = f.read()
    
    # Replace datetime.now() with datetime.now(UTC)
    content = re.sub(
        r'datetime\.now\(\)',
        'datetime.now(UTC)',
        content
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_datetime_strptime(file_path):
    """Fix DTZ007: datetime.strptime() without timezone"""
    with open(file_path, encoding='utf-8') as f:
        content = f.read()
    
    # This is more complex and needs manual review
    # For now, just mark the lines
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'datetime.strptime(' in line:
            lines[i] = line + '  # TODO: Add timezone handling'
    
    content = '\n'.join(lines)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def fix_date_today(file_path):
    """Fix DTZ011: date.today() usage"""
    with open(file_path, encoding='utf-8') as f:
        content = f.read()
    
    # Check if datetime is imported
    if 'from datetime import' in content:
        # Replace date.today() with datetime.now(UTC).date()
        content = re.sub(
            r'date\.today\(\)',
            'datetime.now(UTC).date()',
            content
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

def main():
    """Main function to fix all Python files"""
    src_dir = Path('src')
    tasks_dir = Path('tasks')
    
    # Find all Python files
    python_files = list(src_dir.rglob('*.py')) + list(tasks_dir.rglob('*.py'))
    
    for file_path in python_files:
        try:
            fix_datetime_now(file_path)
            fix_date_today(file_path)
        except Exception:
            pass

if __name__ == '__main__':
    main()
