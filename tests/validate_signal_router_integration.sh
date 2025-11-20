#!/bin/bash
# Validate signal router integration into coordinator
# Checks code structure without requiring full dependency stack

echo "============================================================"
echo "SignalRouter Integration Validation"
echo "============================================================"

COORDINATOR_PATH="/home/kloros/src/kloros/orchestration/coordinator.py"
ROUTER_PATH="/home/kloros/src/kloros/orchestration/signal_router_v2.py"
CHEM_BUS_PATH="/home/kloros/src/kloros/orchestration/chem_bus_v2.py"

# Check files exist
echo ""
echo "Checking required files..."
check_file() {
    if [ -f "$1" ]; then
        echo "✅ $1 exists"
        return 0
    else
        echo "❌ $1 missing"
        return 1
    fi
}

check_file "$COORDINATOR_PATH" || exit 1
check_file "$ROUTER_PATH" || exit 1
check_file "$CHEM_BUS_PATH" || exit 1

# Check coordinator has SignalRouter import
echo ""
echo "Checking coordinator integration..."

if grep -q "from .signal_router_v2 import SignalRouter" "$COORDINATOR_PATH"; then
    echo "✅ SignalRouter imported in coordinator"
else
    echo "❌ SignalRouter import missing in coordinator"
    exit 1
fi

if grep -q "SIGNAL_ROUTER_AVAILABLE" "$COORDINATOR_PATH"; then
    echo "✅ SIGNAL_ROUTER_AVAILABLE flag found"
else
    echo "❌ SIGNAL_ROUTER_AVAILABLE flag missing"
    exit 1
fi

if grep -q "def _get_signal_router" "$COORDINATOR_PATH"; then
    echo "✅ _get_signal_router() function found"
else
    echo "❌ _get_signal_router() function missing"
    exit 1
fi

if grep -q "def _try_chemical_routing" "$COORDINATOR_PATH"; then
    echo "✅ _try_chemical_routing() function found"
else
    echo "❌ _try_chemical_routing() function missing"
    exit 1
fi

if grep -q "if _try_chemical_routing(intent_type, intent):" "$COORDINATOR_PATH"; then
    echo "✅ Chemical routing check in _process_intent()"
else
    echo "❌ Chemical routing check missing in _process_intent()"
    exit 1
fi

if grep -q "routed_via_chemical_signal" "$COORDINATOR_PATH"; then
    echo "✅ Chemical routing archive status found"
else
    echo "❌ Chemical routing archive status missing"
    exit 1
fi

# Check signal_router_v2 has feature flag
echo ""
echo "Checking SignalRouter feature flag..."

if grep -q 'CHEM_ENABLED = os.environ.get("KLR_CHEM_ENABLED"' "$ROUTER_PATH"; then
    echo "✅ KLR_CHEM_ENABLED feature flag found"
else
    echo "❌ KLR_CHEM_ENABLED feature flag missing"
    exit 1
fi

if grep -q "return False" "$ROUTER_PATH"; then
    echo "✅ Fallback return path exists"
else
    echo "⚠️  No explicit fallback return (may be implicit)"
fi

# Check intent mappings exist
echo ""
echo "Checking intent mappings..."

if grep -q "integration_fix" "$ROUTER_PATH"; then
    echo "✅ integration_fix mapped"
else
    echo "⚠️  integration_fix not in mapping (will use legacy)"
fi

if grep -q "spica_spawn_request" "$ROUTER_PATH"; then
    echo "✅ spica_spawn_request mapped"
else
    echo "⚠️  spica_spawn_request not in mapping (will use legacy)"
fi

# Check chem_bus_v2 has observability
echo ""
echo "Checking chem_bus_v2 observability features..."

if grep -q "schema_version" "$CHEM_BUS_PATH"; then
    echo "✅ Schema versioning found"
else
    echo "❌ Schema versioning missing"
    exit 1
fi

if grep -q "_is_duplicate" "$CHEM_BUS_PATH"; then
    echo "✅ Replay defense found"
else
    echo "❌ Replay defense missing"
    exit 1
fi

if grep -q "_heartbeat_loop" "$CHEM_BUS_PATH"; then
    echo "✅ Heartbeat emission found"
else
    echo "❌ Heartbeat emission missing"
    exit 1
fi

# Syntax check
echo ""
echo "Checking Python syntax..."

python3 -m py_compile "$COORDINATOR_PATH" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ coordinator.py syntax valid"
else
    echo "❌ coordinator.py syntax error"
    python3 -m py_compile "$COORDINATOR_PATH"
    exit 1
fi

python3 -m py_compile "$ROUTER_PATH" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ signal_router_v2.py syntax valid"
else
    echo "❌ signal_router_v2.py syntax error"
    python3 -m py_compile "$ROUTER_PATH"
    exit 1
fi

python3 -m py_compile "$CHEM_BUS_PATH" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ chem_bus_v2.py syntax valid"
else
    echo "❌ chem_bus_v2.py syntax error"
    python3 -m py_compile "$CHEM_BUS_PATH"
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ All structural validations passed!"
echo "============================================================"
echo ""
echo "Integration Summary:"
echo "  1. SignalRouter properly imported into coordinator"
echo "  2. Feature flag KLR_CHEM_ENABLED controls routing"
echo "  3. Chemical routing attempted before legacy fallback"
echo "  4. Observability layers (heartbeat, replay defense) present"
echo "  5. Python syntax valid for all components"
echo ""
echo "Next Steps:"
echo "  1. Set KLR_CHEM_ENABLED=0 for safe start (legacy mode)"
echo "  2. Monitor coordinator logs for routing decisions"
echo "  3. When ready: Set KLR_CHEM_ENABLED=1 to enable colony"
echo "  4. Install ZeroMQ: pip install pyzmq"
echo "  5. Deploy zooid implementations"
echo ""
echo "Feature Flag Usage:"
echo "  export KLR_CHEM_ENABLED=0  # Disable chemical routing (legacy only)"
echo "  export KLR_CHEM_ENABLED=1  # Enable chemical routing (colony mode)"
echo "============================================================"
