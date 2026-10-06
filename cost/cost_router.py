#!/usr/bin/env python3
"""
Hermes Cost Router - Auto-select cheapest model for each task
Priority: Ollama (free) > Kimi (cheap) > Nothing else
"""

import os
import sys
import re

# Cost hierarchy (per 1M tokens)
COST_PER_M = {
    'ollama': 0.00,           # FREE
    'qwen2.5:14b': 0.00,      # FREE (local)
    'qwen3:14b': 0.00,        # FREE (local)
    'mistral-nemo:12b': 0.00, # FREE (local)
    'kimi-k2-thinking': 0.15, # CHEAP
    'kimi-k3': 0.15,          # CHEAP
    'claude-haiku': 0.50,     # EXPENSIVE
    'claude-sonnet': 3.00,    # VERY EXPENSIVE
    'claude-opus': 15.00,     # PROHIBITIVE
    'gpt-4': 10.00,           # EXPENSIVE
    'gemini-pro': 0.50,       # EXPENSIVE
}

# Task routing rules
TASK_PATTERNS = {
    # FREE tasks - Ollama only
    'free': [
        r'cat|ls|dir|pwd|echo|grep',
        r'curl.*-I|curl.*-s',  # Simple HTTP headers
        r'openssl.*x509',
        r'nslookup|dig|ping',
        r'file\s+-',
        r'wc\s+-l',
        r'head|tail',
        r'sha256sum|md5sum',
        r'unset|export|alias',
        r'chmod|chown',
        r'find.*-name',
        r'git.*status|git.*log.*-1',
        r'mkdir|rm|cp|mv',
    ],
    
    # CHEAP tasks - Kimi allowed
    'cheap': [
        r'web_search',
        r'web_extract',
        r'skill_view',
        r'read_file',
        r'search_files',
        r'terminal.*complex',
        r'execute_code.*simple',
        r'write_file.*small',
    ],
    
    # EXPENSIVE - Kimi only if no choice
    'expensive': [
        r'browser_exec',
        r'delegate_task',
        r'vision_analyze',
        r'image_generate',
        r'complex.*reasoning',
        r'audit.*full',
        r'subagent',
    ]
}

def classify_task(command):
    """Classify task and recommend cheapest model"""
    command_lower = command.lower()
    
    # Check FREE patterns
    for pattern in TASK_PATTERNS['free']:
        if re.search(pattern, command_lower, re.IGNORECASE):
            return {
                'tier': 'FREE',
                'model': 'qwen2.5:14b-instruct',
                'provider': 'local',
                'cost_per_m': 0.00,
                'reason': 'Simple terminal/file operation'
            }
    
    # Check CHEAP patterns
    for pattern in TASK_PATTERNS['cheap']:
        if re.search(pattern, command_lower, re.IGNORECASE):
            return {
                'tier': 'CHEAP',
                'model': 'moonshotai/kimi-k2-thinking',
                'provider': 'nous',
                'cost_per_m': 0.15,
                'reason': 'Information retrieval'
            }
    
    # Default to cheap for unknown
    return {
        'tier': 'CHEAP',
        'model': 'moonshotai/kimi-k2-thinking',
        'provider': 'nous',
        'cost_per_m': 0.15,
        'reason': 'Default to cheap tier'
    }

def get_cheapest_command(task):
    """Get the cheapest Hermes command for a task"""
    recommendation = classify_task(task)
    
    if recommendation['tier'] == 'FREE':
        return {
            'command': f"hermes -m {recommendation['model']} --provider local",
            'cost': '$0.00',
            'savings_vs_claude': '100%'
        }
    else:
        return {
            'command': f"hermes -m {recommendation['model']} --provider nous",
            'cost': '~$0.15/M tokens',
            'savings_vs_claude': '95%'
        }

if __name__ == '__main__':
    if len(sys.argv) > 1:
        task = ' '.join(sys.argv[1:])
        result = get_cheapest_command(task)
        print(f"Task: {task}")
        print(f"Cheapest: {result['command']}")
        print(f"Cost: {result['cost']}")
        print(f"Savings vs Claude: {result['savings_vs_claude']}")
    else:
        print("Usage: python cost_router.py '<task description>'")
        print("\nExamples:")
        print("  python cost_router.py 'curl -I https://example.com'")
        print("  python cost_router.py 'web_search SEO trends'")
        print("  python cost_router.py 'browser_exec complex audit'")
