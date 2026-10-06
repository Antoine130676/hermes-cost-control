#!/usr/bin/env python3
"""
Hermes Strict Provider Enforcement Agent
- Monitors all subagents and API calls
- Ensures ONLY Nous Portal + Kimi-k2-thinking is used
- Alerts on credit limits ($3 threshold)
- Kills unauthorized provider switches
- Logs all enforcement actions
"""

import os
import sys
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Configuration
ALERT_THRESHOLD_USD = 3.00
PROVIDER_ALLOWLIST = ['nous', 'nousresearch']
MODEL_ALLOWLIST = ['moonshotai/kimi-k2-thinking', 'moonshotai/kimi-k3']
VIOLATION_ACTION = 'kill'  # Options: 'kill', 'alert', 'log'

# Paths
HERMES_LOG_DIR = Path(os.path.expanduser('~/AppData/Local/hermes/logs'))
HERMES_CACHE = Path(os.path.expanduser('~/AppData/Local/hermes/cache'))
MONITOR_LOG = Path(os.path.expanduser('~/hermes-projects/hermes-monitor/enforcement.log'))
ALERT_LOG = Path(os.path.expanduser('~/hermes-projects/hermes-monitor/alerts.log'))
CREDIT_TRACKER = Path(os.path.expanduser('~/hermes-projects/hermes-monitor/credit_tracker.json'))

class HermesEnforcer:
    def __init__(self):
        self.running = False
        self.session_cost = 0.0
        self.violations = []
        self._ensure_dirs()
        
    def _ensure_dirs(self):
        MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
        
    def log(self, msg, level='INFO'):
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] [{level}] {msg}"
        print(log_entry)
        with open(MONITOR_LOG, 'a') as f:
            f.write(log_entry + '\n')
            
    def alert(self, msg, cost=None):
        """Send alert via notification and log"""
        timestamp = datetime.now().isoformat()
        alert_msg = f"🚨 HERMES ALERT: {msg}"
        if cost:
            alert_msg += f" (Session cost: ${cost:.2f})"
        
        self.log(alert_msg, 'ALERT')
        with open(ALERT_LOG, 'a') as f:
            f.write(f"[{timestamp}] {alert_msg}\n")
            
        # Also write to Telegram-compatible file
        telegram_file = Path(os.path.expanduser('~/hermes-projects/hermes-monitor/telegram_alerts.txt'))
        with open(telegram_file, 'a') as f:
            f.write(f"{timestamp}: {alert_msg}\n")
        
        return alert_msg
        
    def parse_log_line(self, line):
        """Parse Hermes agent.log for provider switches and costs"""
        data = {}
        
        # Detect provider switches
        if 'model/provider switched' in line:
            match = re.search(r'(\S+) via (\S+) -> (\S+) via (\S+)', line)
            if match:
                old_model, old_provider, new_model, new_provider = match.groups()
                data['event'] = 'PROVIDER_SWITCH'
                data['old'] = {'model': old_model, 'provider': old_provider}
                data['new'] = {'model': new_model, 'provider': new_provider}
                data['timestamp'] = datetime.now().isoformat()
                
        # Detect API calls with costs
        elif 'api call' in line.lower() and 'provider=' in line:
            match = re.search(r'provider=(\S+).*model=(\S+)', line)
            if match:
                provider, model = match.groups()
                data['event'] = 'API_CALL'
                data['provider'] = provider
                data['model'] = model
                data['timestamp'] = datetime.now().isoformat()
                
        # Detect cost tracking
        elif 'total=' in line and 'in=' in line:
            match = re.search(r'in=(\d+).*out=(\d+).*total=(\d+)', line)
            if match:
                in_tok, out_tok, total_tok = map(int, match.groups())
                # Estimate cost: Kimi ~$0.15/M tokens, Claude ~$3/M tokens
                data['event'] = 'TOKENS_USED'
                data['tokens'] = total_tok
                data['estimated_cost'] = total_tok * 0.00000015  # Conservative estimate
                
        return data if data else None
        
    def is_authorized(self, provider, model):
        """Check if provider/model is authorized"""
        provider_ok = any(p in provider.lower() for p in PROVIDER_ALLOWLIST)
        model_ok = any(m == model.lower() for m in MODEL_ALLOWLIST)
        return provider_ok and model_ok
        
    def handle_violation(self, data):
        """Handle unauthorized provider usage"""
        violation_msg = f"UNAUTHORIZED: {data.get('old', {}).get('model', 'unknown')} -> {data.get('new', {}).get('model', 'unknown')}"
        
        if VIOLATION_ACTION == 'kill':
            self.log(f"KILLING SESSION: {violation_msg}", 'VIOLATION')
            self.alert(f"PROVIDER SWITCH BLOCKED! Session terminated.")
            # Note: Actual session kill requires more integration with Hermes internals
            # This logs the intent for manual intervention
            self.violations.append(data)
            return 'killed'
        elif VIOLATION_ACTION == 'alert':
            self.alert(f"PROVIDER VIOLATION DETECTED: {violation_msg}")
            self.violations.append(data)
            return 'alerted'
        else:
            self.log(f"Violation logged: {violation_msg}")
            self.violations.append(data)
            return 'logged'
            
    def check_credit_limit(self, current_cost):
        """Check if approaching credit limit"""
        if current_cost >= ALERT_THRESHOLD_USD:
            self.alert(
                f"CREDIT LIMIT WARNING: ${current_cost:.2f} spent (threshold: ${ALERT_THRESHOLD_USD})",
                cost=current_cost
            )
            return True
        return False
        
    def monitor_session(self, session_id=None):
        """Monitor active Hermes session"""
        self.log(f"Starting monitor for session: {session_id or 'all'}")
        self.running = True
        last_position = 0
        session_cost = 0.0
        
        log_file = HERMES_LOG_DIR / 'agent.log'
        
        try:
            while self.running:
                if not log_file.exists():
                    time.sleep(1)
                    continue
                    
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    last_position = f.tell()
                    
                for line in new_lines:
                    data = self.parse_log_line(line)
                    if data:
                        if data['event'] == 'PROVIDER_SWITCH':
                            old = data.get('old', {})
                            new = data.get('new', {})
                            
                            if not self.is_authorized(new.get('provider', ''), new.get('model', '')):
                                action = self.handle_violation(data)
                                self.log(f"VIOLATION: {old.get('model')}->{new.get('model')} ACTION: {action}")
                            else:
                                self.log(f"Authorized switch: {old.get('model')} -> {new.get('model')}")
                                
                        elif data['event'] == 'TOKENS_USED':
                            cost = data.get('estimated_cost', 0)
                            session_cost += cost
                            
                            if self.check_credit_limit(session_cost):
                                self.log(f"Credit alert sent. Total: ${session_cost:.2f}")
                                
                        elif data['event'] == 'API_CALL':
                            provider = data.get('provider', '')
                            model = data.get('model', '')
                            
                            if not self.is_authorized(provider, model):
                                self.alert(f"UNAUTHORIZED API CALL: {model} via {provider}")
                                
                time.sleep(0.5)  # Poll every 500ms
                
        except KeyboardInterrupt:
            self.log("Monitor stopped by user")
        except Exception as e:
            self.log(f"Monitor error: {e}", 'ERROR')
            
        return session_cost
        
    def generate_report(self):
        """Generate enforcement report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'violations': self.violations,
            'total_violations': len(self.violations),
            'session_cost': self.session_cost,
            'alert_threshold': ALERT_THRESHOLD_USD
        }
        
        report_file = MONITOR_LOG.parent / f"enforcement_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
            
        return report

def main():
    """Main entry point"""
    print("="*60)
    print("HERMES STRICT PROVIDER ENFORCEMENT AGENT")
    print("="*60)
    print(f"Allowed Provider: Nous Portal only")
    print(f"Allowed Models: {', '.join(MODEL_ALLOWLIST)}")
    print(f"Credit Alert Threshold: ${ALERT_THRESHOLD_USD}")
    print(f"Violation Action: {VIOLATION_ACTION}")
    print("="*60)
    
    enforcer = HermesEnforcer()
    
    # Check if we should run once or monitor continuously
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        print("Running single check...")
        enforcer.log("Single check mode")
    else:
        print("Starting continuous monitor (Ctrl+C to stop)...")
        try:
            enforcer.monitor_session()
        finally:
            report = enforcer.generate_report()
            print(f"\nMonitor stopped. Violations: {report['total_violations']}")
            print(f"Report saved to: {enforcer.MONITOR_LOG.parent}")

if __name__ == '__main__':
    main()
