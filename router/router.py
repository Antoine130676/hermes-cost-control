#!/usr/bin/env python3
"""
Hermes Smart Router Agent
Takes natural language input, classifies task, routes to cheapest method automatically.
"""

import re
import sys
import os
import subprocess
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Task classification rules
TASK_RULES = {
    'FREE': {
        'patterns': [
            r'^curl\s', r'^cat\s', r'^ls\s', r'^grep\s', r'^find\s',
            r'^head\s', r'^tail\s', r'^wc\s', r'^file\s', r'^nslookup\s',
            r'^dig\s', r'^ping\s', r'^openssl\s', r'^sha256sum\s',
            r'^md5sum\s', r'^base64\s', r'^tar\s', r'^unzip\s',
            r'^git\s+(status|log|diff|show|branch)', r'^mkdir\s', r'^rm\s',
            r'^cp\s', r'^mv\s', r'^chmod\s', r'^chown\s', r'^echo\s',
            r'^pwd$', r'^cd\s', r'^which\s', r'^env$', r'^printenv',
            r'^ps\s', r'^top$', r'^df$', r'^du\s', r'^free$',
            r'^(check|curl|fetch|get|download|read|show)\s+(https?://)?[\w.-]+\.\w+',
            r'^(check|test|verify)\s+(ssl|certificate|cert|https?)',
            r'^(dns|resolve|lookup)\s+[\w.-]+\.\w+',
        ],
        'keywords': [
            'curl', 'download', 'fetch', 'get headers', 'check ssl',
            'dns lookup', 'resolve', 'read file', 'show file',
            'list files', 'directory', 'count lines', 'file size',
        ],
        'command': 'hermes -m qwen2.5:14b-instruct --provider local',
        'model': 'Ollama (local)',
        'cost': '$0.00'
    },
    'CHEAP': {
        'patterns': [
            r'search\s+(for|web|google)', r'look up', r'find\s+(info|information)',
            r'audit', r'analyze', r'check\s+(seo|site|website|performance)',
            r'extract', r'scrape', r'get\s+data\s+from',
            r'summarize', r'review', r'compare',
        ],
        'keywords': [
            'web search', 'google', 'research', 'information',
            'audit', 'analyze', 'check site', 'seo check',
            'extract data', 'scrape', 'summarize', 'review',
            'compare sites', 'competitor', 'keyword',
        ],
        'command': 'hermes -m moonshotai/kimi-k2-thinking --provider nous',
        'model': 'Kimi (Nous)',
        'cost': '~$0.15/M tokens'
    },
    'EXPENSIVE_WARNING': {
        'patterns': [
            r'browser', r'click', r'screenshot', r'automate\s+browser',
            r'full\s+page', r'render', r'javascript\s+execution',
        ],
        'keywords': [
            'browser automation', 'click', 'screenshot',
            'visual', 'render page', 'full audit with browser',
        ],
        'warning': True,
        'command': 'hermes -m moonshotai/kimi-k2-thinking --provider nous',
        'model': 'Kimi (Nous) - Alternative suggested',
        'cost': '~$0.15/M tokens (browser would be $0.80+)'
    }
}

class SmartRouter:
    def __init__(self):
        self.base = Path(os.environ.get('HERMES_PROJECTS_DIR', Path.home() / 'hermes-projects'))
        self.log_file = str(self.base / 'smart-router' / 'router.log')
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # PKB paths
        self.pkb_base = self.base / "personal"
        self.pkb_research = self.pkb_base / "research"
        self.pkb_research.mkdir(parents=True, exist_ok=True)
        
    def save_to_pkb(self, user_input, result, tier, cost, command):
        """Save results to Personal Knowledge Base"""
        
        # Generate filename based on query and date
        date_str = datetime.now().strftime('%Y-%m-%d')
        query_hash = hashlib.md5(user_input.encode()).hexdigest()[:8]
        
        # Extract domain/topic from query
        domain_match = re.search(r'([\w.-]+\.\w+)', user_input)
        topic = domain_match.group(1) if domain_match else user_input[:20].replace(' ', '_')
        
        filename = f"{date_str}--{topic}--{query_hash}.md"
        filepath = self.pkb_research / filename
        
        # Truncate result if too large (store first 50KB)
        result_truncated = result[:50000] if len(result) > 50000 else result
        
        content = f"""# Research: {user_input}

**Date:** {datetime.now().isoformat()}
**Tier:** {tier}
**Cost:** {cost}
**Command:** `{command}`

## Results

```
{result_truncated}
```

---
*Auto-saved by Smart Router*
"""
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.log(f"Saved to PKB: {filepath}")
            return filepath
        except Exception as e:
            self.log(f"Failed to save PKB: {e}")
            return None
        
    def log(self, message):
        timestamp = datetime.now().isoformat()
        with open(self.log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
    
    def classify_task(self, user_input):
        """Classify user input into FREE, CHEAP, or EXPENSIVE_WARNING"""
        input_lower = user_input.lower()
        
        # Check FREE patterns first (also try with a trailing space so a bare `ls` matches `^ls\s`)
        probe = user_input.strip() + ' '
        for pattern in TASK_RULES['FREE']['patterns']:
            if re.search(pattern, user_input, re.IGNORECASE) or re.search(pattern, probe, re.IGNORECASE):
                return 'FREE', TASK_RULES['FREE']
        
        for keyword in TASK_RULES['FREE']['keywords']:
            if keyword in input_lower:
                return 'FREE', TASK_RULES['FREE']
        
        # Check EXPENSIVE_WARNING patterns
        for pattern in TASK_RULES['EXPENSIVE_WARNING']['patterns']:
            if re.search(pattern, user_input, re.IGNORECASE):
                return 'EXPENSIVE_WARNING', TASK_RULES['EXPENSIVE_WARNING']
        
        for keyword in TASK_RULES['EXPENSIVE_WARNING']['keywords']:
            if keyword in input_lower:
                return 'EXPENSIVE_WARNING', TASK_RULES['EXPENSIVE_WARNING']
        
        # Check CHEAP patterns
        for pattern in TASK_RULES['CHEAP']['patterns']:
            if re.search(pattern, user_input, re.IGNORECASE):
                return 'CHEAP', TASK_RULES['CHEAP']
        
        for keyword in TASK_RULES['CHEAP']['keywords']:
            if keyword in input_lower:
                return 'CHEAP', TASK_RULES['CHEAP']
        
        # Default to CHEAP for anything else
        return 'CHEAP', TASK_RULES['CHEAP']
    
    def translate_command(self, user_input, tier, rules):
        """Translate natural language to terminal command if FREE"""
        if tier == 'FREE':
            # Extract URL if present
            url_match = re.search(r'https?://([^\s]+)', user_input)
            if url_match:
                url = url_match.group(0)
                return f'curl -sL {url}'
            
            # Extract domain if present (no http)
            domain_match = re.search(r'(?:check|curl|fetch|get)\s+(https?://)?([\w.-]+\.\w+)', user_input, re.IGNORECASE)
            if domain_match:
                domain = domain_match.group(2)
                return f'curl -sL https://{domain}'
            
            # File operations
            file_match = re.search(r'(?:read|show|cat|display)\s+(?:file\s+)?([~/\.\w-]+)', user_input, re.IGNORECASE)
            if file_match:
                filepath = file_match.group(1)
                return f'cat {filepath}'
            
            # DNS lookup
            dns_match = re.search(r'(?:dns|nslookup|resolve|lookup)\s+(https?://)?([\w.-]+\.\w+)', user_input, re.IGNORECASE)
            if dns_match:
                domain = dns_match.group(2)
                return f'nslookup {domain}'
            
            # SSL check
            ssl_match = re.search(r'(?:ssl|certificate|cert|https?://)?([\w.-]+\.\w+)', user_input, re.IGNORECASE)
            if ssl_match:
                domain = ssl_match.group(1)
                return f'echo | openssl s_client -connect {domain}:443 -servername {domain} 2>/dev/null | openssl x509 -noout -dates'
            
        # For CHEAP and EXPENSIVE, pass through with context
        return user_input
    
    def route(self, user_input):
        """Main routing logic"""
        tier, rules = self.classify_task(user_input)
        command = self.translate_command(user_input, tier, rules)
        
        print(f"\n🎯 SMART ROUTER: {tier} TIER")
        print(f"   Input: {user_input}")
        print(f"   Model: {rules['model']}")
        print(f"   Cost: {rules['cost']}")
        
        if tier == 'EXPENSIVE_WARNING' and rules.get('warning'):
            print(f"\n⚠️  WARNING: Browser automation detected (expensive).")
            print(f"   Consider: 'curl -sL <url>' instead of full browser.")
            print(f"   Using cheaper alternative...\n")
        else:
            print(f"   Executing: {rules['command']} \"{command}\"\n")
        
        self.log(f"TIER={tier} MODEL={rules['model']} COST={rules['cost']} CMD={command}")
        
        # Execute
        result = ""
        if tier == 'FREE':
            # For FREE tier, execute directly via terminal (no hermes API call)
            print(f"Running directly: {command}\n")
            result = subprocess.getoutput(command)
            print(result[:2000] if len(result) > 2000 else result)  # Print first 2K chars
            if len(result) > 2000:
                print(f"\n... ({len(result) - 2000} more chars)")
        else:
            # For CHEAP tier, use hermes
            full_command = f"{rules['command']} \"{command}\""
            print(f"Running: {full_command}\n")
            result = subprocess.getoutput(full_command)
            print(result[:2000] if len(result) > 2000 else result)
            if len(result) > 2000:
                print(f"\n... ({len(result) - 2000} more chars)")
        
        # Save to PKB
        pkb_path = self.save_to_pkb(user_input, result, tier, rules['cost'], command)
        if pkb_path:
            print(f"\n💾 Saved to PKB: {pkb_path}")

    def main(self):
        if len(sys.argv) < 2:
            print("Usage: hr <your natural language request>")
            print("\nExamples:")
            print("  hr check example.com")
            print("  hr curl https://example.com")
            print("  hr web search for SEO trends")
            print("  hr audit example.org")
            print("\nI'll automatically route to the cheapest model.")
            sys.exit(1)
        
        user_input = ' '.join(sys.argv[1:])
        self.route(user_input)

def main():
    router = SmartRouter()
    router.main()

if __name__ == '__main__':
    main()
