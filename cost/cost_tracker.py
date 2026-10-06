#!/usr/bin/env python3
"""
Hermes Real-Time Cost Tracker
Tracks cost per session/task and suggests cheaper alternatives
"""

import json
import os
from datetime import datetime
from pathlib import Path

COST_DB = Path(os.environ.get('HERMES_PROJECTS_DIR', Path.home() / 'hermes-projects')) / 'cost-optimizer' / 'cost_tracker.json'
COST_DB.parent.mkdir(parents=True, exist_ok=True)

# Pricing (per 1M tokens)
PRICING = {
    'ollama': {'input': 0, 'output': 0, 'name': 'Ollama (Local)'},
    'qwen2.5:14b': {'input': 0, 'output': 0, 'name': 'Qwen 2.5 14B (Local)'},
    'kimi-k2': {'input': 0.15, 'output': 0.60, 'name': 'Kimi K2 (Nous)'},
    'kimi-k3': {'input': 0.15, 'output': 0.60, 'name': 'Kimi K3 (Nous)'},
    'claude-haiku': {'input': 0.25, 'output': 1.25, 'name': 'Claude Haiku'},
    'claude-sonnet': {'input': 3.00, 'output': 15.00, 'name': 'Claude Sonnet'},
    'claude-opus': {'input': 15.00, 'output': 75.00, 'name': 'Claude Opus'},
}

class CostTracker:
    def __init__(self):
        self.data = self.load()
        
    def load(self):
        if COST_DB.exists():
            with open(COST_DB) as f:
                return json.load(f)
        return {
            'sessions': {},
            'daily_totals': {},
            'alerts': []
        }
    
    def save(self):
        with open(COST_DB, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def estimate_cost(self, model, input_tokens, output_tokens):
        """Estimate cost for a request"""
        pricing = PRICING.get(model.lower().replace('moonshotai/', '').replace('-thinking', ''), 
                             {'input': 0.15, 'output': 0.60, 'name': 'Unknown model (default pricing)'})
        
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        
        return {
            'input_cost': input_cost,
            'output_cost': output_cost,
            'total': input_cost + output_cost,
            'model_name': pricing['name']
        }
    
    def suggest_cheaper(self, current_model, task_type):
        """Suggest cheaper alternative"""
        current_pricing = PRICING.get(current_model.lower(), {'input': 999})
        current_input = current_pricing['input']
        
        suggestions = []
        
        # Check if Ollama can handle it
        if task_type in ['terminal', 'file', 'simple']:
            suggestions.append({
                'model': 'qwen2.5:14b',
                'savings': '100%',
                'command': 'hermes -m qwen2.5:14b-instruct --provider local'
            })
        
        # Check if Kimi is cheaper
        if current_input > 0.15:
            savings = ((current_input - 0.15) / current_input) * 100
            suggestions.append({
                'model': 'kimi-k2',
                'savings': f'{savings:.0f}%',
                'command': 'hermes -m moonshotai/kimi-k2-thinking --provider nous'
            })
        
        return suggestions
    
    def get_session_summary(self):
        """Get current session cost summary"""
        today = datetime.now().strftime('%Y-%m-%d')
        daily = self.data.get('daily_totals', {}).get(today, {'cost': 0, 'tokens': 0})
        
        return {
            'today_cost': daily.get('cost', 0),
            'today_tokens': daily.get('tokens', 0),
            'budget_remaining': max(0, 3.0 - daily.get('cost', 0)),
            'at_risk': daily.get('cost', 0) > 2.5
        }
    
    def print_status(self):
        """Print current cost status"""
        summary = self.get_session_summary()
        
        print(f"\n{'='*60}")
        print(f"HERMES COST TRACKER")
        print(f"{'='*60}")
        print(f"Today's cost: ${summary['today_cost']:.2f}")
        print(f"Today's tokens: {summary['today_tokens']:,}")
        print(f"Budget remaining: ${summary['budget_remaining']:.2f} (threshold: $3)")
        
        if summary['at_risk']:
            print(f"⚠️  WARNING: Approaching $3 limit!")
        
        print(f"{'='*60}\n")
    
    def log_usage(self, model, input_tokens, output_tokens, task):
        """Log a usage event"""
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.data['daily_totals']:
            self.data['daily_totals'][today] = {'cost': 0, 'tokens': 0}
        
        self.data['daily_totals'][today]['cost'] += cost['total']
        self.data['daily_totals'][today]['tokens'] += (input_tokens + output_tokens)
        
        self.save()
        return cost

if __name__ == '__main__':
    tracker = CostTracker()
    tracker.print_status()
    
    # Show savings for common tasks
    print("CHEAPER ALTERNATIVES:")
    print("-" * 40)
    
    tasks = [
        ('curl -I https://example.com', 'terminal'),
        ('web_search SEO trends', 'web'),
        ('browser_exec full audit', 'browser'),
    ]
    
    for task, task_type in tasks:
        print(f"\nTask: {task}")
        suggestions = tracker.suggest_cheaper('claude-sonnet', task_type)
        for sug in suggestions[:2]:
            print(f"  → Use {sug['model']}: Save {sug['savings']}")
            print(f"     Command: {sug['command']}")
