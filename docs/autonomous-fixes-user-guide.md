# Autonomous Fix System User Guide

## Overview

The autonomous fix system enables KLoROS to proactively attempt fixes for integration issues discovered by the curiosity system. Fixes are generated using LLM code generation, tested in isolated SPICA instances, and held in escrow for manual approval before merging.

## How It Works

1. **Discovery**: Curiosity system detects integration issues (orphaned queues, uninitialized components)
2. **Routing**: High-autonomy questions (level 3+) trigger BOTH:
   - Documentation report (for human reference)
   - Autonomous fix attempt (in SPICA sandbox)
3. **Code Generation**: LLM generates code patch based on issue context
4. **Sandbox Testing**: Patch applied to isolated SPICA instance
5. **Validation**: Test suite runs in isolation
6. **Escrow**: Successful fixes held for manual review
7. **Approval**: Human reviews and approves/rejects before merge

## Autonomy Levels

| Level | Behavior |
|-------|----------|
| 1-2   | Documentation only (requires manual implementation) |
| 3     | Parallel: Documentation + autonomous fix attempt |
| 4-5   | (Future) Auto-apply fixes that pass all validation |

## Reviewing Fixes in Escrow

### List pending fixes

```bash
python -c "
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
for entry in escrow.list_pending():
    print(f'{entry[\"escrow_id\"]}: {entry[\"question_id\"]} ({entry[\"spica_id\"]})')
"
```

### Inspect a fix

```bash
# View escrow entry
cat /home/kloros/.kloros/escrow/<escrow_id>.json

# View SPICA instance code
cd /home/kloros/experiments/spica/instances/<spica_id>
git diff

# Run tests manually
cd /home/kloros/experiments/spica/instances/<spica_id>
source ../../template/.venv/bin/activate
pytest tests/ -v
```

### Approve a fix

```python
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
escrow.approve("escrow-abc123", reviewed_by="your_name")

# Manually merge changes
# (Future: automated merge after approval)
```

### Reject a fix

```python
from src.kloros.orchestration.escrow_manager import EscrowManager
escrow = EscrowManager()
escrow.reject("escrow-abc123", reason="Breaks edge case X", reviewed_by="your_name")
```

## Safety Guardrails

1. **Isolation**: All changes applied in SPICA instance, never directly to main
2. **Test Validation**: Must pass existing test suite before escrow
3. **Manual Approval**: Human reviews before merging to production
4. **Auto-Rollback**: Test failures trigger automatic cleanup
5. **Retention Policy**: SPICA instances pruned after 3 days (max 10 instances)
6. **Deduplication**: Questions marked processed to prevent duplicate attempts

## Configuration

Environment variables in `/home/kloros/.kloros_env`:

```bash
# Curiosity system
KLR_CURIOSITY_REPROCESS_DAYS=7
KLR_CURIOSITY_MAX_PROCESSED=500
KLR_DISABLE_CURIOSITY=0

# LLM code generation
OLLAMA_HOST=http://100.67.244.66:11434
```

## Monitoring

### View orchestrator logs

```bash
journalctl -u kloros-orchestrator.service -f
```

### Check SPICA instances

```bash
ls -la /home/kloros/experiments/spica/instances/
```

### View escrow queue

```bash
ls -la /home/kloros/.kloros/escrow/
```

## Troubleshooting

### No autonomous fixes being attempted

1. Check autonomy level: `cat /home/kloros/.kloros/curiosity_feed/<question_id>.json | jq .autonomy`
2. Verify autonomy >= 3 for SPICA spawn
3. Check orchestrator logs for errors

### LLM generation failures

1. Test Ollama connectivity: `curl http://100.67.244.66:11434/api/generate -d '{"model":"qwen2.5:72b","prompt":"test"}'`
2. Check model availability: `curl http://100.67.244.66:11434/api/tags`
3. Review LLM logs in orchestrator output

### SPICA instance failures

1. Verify template exists: `ls /home/kloros/experiments/spica/template/`
2. Check disk space: `df -h`
3. Review SPICA spawner logs

### Test failures in SPICA

1. Manually inspect SPICA instance code
2. Run tests with verbose output: `cd <spica_instance> && pytest -vv`
3. Review test output in escrow entry JSON

## Best Practices

1. **Review escrow regularly** - Don't let fixes pile up unreviewed
2. **Reject with detailed reasons** - Helps improve future fix generation
3. **Monitor SPICA disk usage** - Prune old instances if disk fills
4. **Track approval rates** - Low rates indicate LLM tuning needed
5. **Keep test suite comprehensive** - Better validation in SPICA sandbox

## Future Enhancements

- Auto-merge for high-confidence fixes (autonomy 4-5)
- Multi-file fix support
- Learning from approval/rejection patterns
- Auto-generated regression tests for fixed issues
