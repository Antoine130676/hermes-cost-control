#!/bin/bash
# Hermes Cost Guard - Intercepts expensive operations
# Usage: Source this file or add to .bashrc

HERMES_COST_LIMIT=3.00
HERMES_COST_CURRENT=0.00
HERMES_COST_GUARD_ACTIVE=true

# Function to check cost before running
check_cost_before() {
    local model="$1"
    local estimated_tokens="${2:-1000000}"  # Default 1M tokens
    
    # Pricing per 1M tokens
    local cost_per_m=0.15  # Default Kimi
    
    case "$model" in
        *ollama*|*qwen*|*mistral*)
            cost_per_m=0.00
            ;;
        *kimi*)
            cost_per_m=0.15
            ;;
        *haiku*)
            cost_per_m=0.50
            ;;
        *sonnet*)
            cost_per_m=3.00
            ;;
        *opus*|*gpt-4*)
            cost_per_m=15.00
            ;;
    esac
    
    local estimated_cost=$(echo "$estimated_tokens * $cost_per_m / 1000000" | bc -l 2>/dev/null || echo "1.00")
    local new_total=$(echo "$HERMES_COST_CURRENT + $estimated_cost" | bc -l 2>/dev/null || echo "999")
    
    # Check if would exceed limit
    if (( $(echo "$new_total > $HERMES_COST_LIMIT" | bc -l 2>/dev/null || echo "0") )); then
        echo ""
        echo "⚠️  COST GUARD ALERT ⚠️"
        echo "This operation would exceed your $${HERMES_COST_LIMIT} budget!"
        echo "Current: $${HERMES_COST_CURRENT} | This op: ~$${estimated_cost} | After: ~$${new_total}"
        echo ""
        echo "Alternatives:"
        echo "  1. Use Ollama (FREE): hermes-free"
        echo "  2. Use Kimi (CHEAP): hermes-cheap"
        echo "  3. Run anyway (risky): Continue with current model"
        echo ""
        return 1
    fi
    
    return 0
}

# Wrapper for expensive operations
hermes-guard() {
    local cmd="$*"
    
    # Check if it's an expensive operation
    if [[ "$cmd" =~ (browser_exec|delegate_task|vision_analyze|image_generate) ]]; then
        echo ""
        echo "💰 EXPENSIVE OPERATION DETECTED 💰"
        echo "Operation: $cmd"
        echo ""
        echo "This will use browser automation (~$0.30-0.80 per page)."
        echo ""
        echo "Cheaper alternatives:"
        echo "  • Use 'curl -s' instead of browser_exec where possible"
        echo "  • Use terminal commands instead of subagents"
        echo "  • Use web_search instead of web_extract"
        echo ""
        echo "Continue? (y/N)"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "Cancelled. Use hermes-cheap for safer option."
            return 1
        fi
    fi
    
    # Run the command
    "$@"
}

# Export functions
export -f check_cost_before
export -f hermes-guard
export HERMES_COST_LIMIT
export HERMES_COST_CURRENT
export HERMES_COST_GUARD_ACTIVE
