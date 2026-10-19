#!/bin/bash
# Cancel the spawned training call once checkpoint-$1 is committed to the kb-finetune volume.
cd "$(dirname "$0")"
until modal volume ls kb-finetune checkpoints/r1 2>/dev/null | grep -q "checkpoint-$1$"; do sleep 60; done
sleep 30  # let the volume commit finish
python3 -c "
import modal
c = modal.FunctionCall.from_id(open('modal-full-call.txt').read().strip())
c.cancel()
print('cancelled after checkpoint-$1')
"
modal billing summary 2>&1 | grep -E "Ephemeral|Deployed|Billed"
