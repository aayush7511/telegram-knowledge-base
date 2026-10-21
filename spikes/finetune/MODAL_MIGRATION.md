# Moving the fine-tune setup to another Modal workspace

Exported from workspace `ashumili57` on 2026-10-19. Nothing here needs the old workspace again.

## Where everything lives now

| What | Where | Notes |
|---|---|---|
| Training data (examples) | HF dataset `aayush7511/graphiti-memory-synth` (private) | also in `../memory-gen/out/hf-release/examples` |
| LoRA adapter, checkpoint-200 | HF model `aayush7511/qwen3.5-35b-a3b-graphiti-lora` (private) | 1.08 epochs, val loss 0.082 |
| Resume state for checkpoint-200 | same repo, `resume/checkpoint-200/` | optimizer, scheduler, RNG: continue epoch 2 from step 200 |
| cobol2java volume (other project) | HF dataset `aayush7511/cobol2java-modal-export` (private) | data + runs |
| Base / benchmark model weights (142 GB) | not exported: public HF models | re-download with `modal run modal_train.py::download` (CPU, cents) |
| Modal secret `huggingface` | not exportable (Modal never shows values) | re-create in the new workspace yourself |

## Rebuild in a new workspace

```bash
modal profile activate <new-profile>          # check with: modal profile current
modal volume put kb-finetune ../memory-gen/out/hf-release/examples examples
modal run modal_train.py::download            # 67 GB of weights on a CPU box
```

Before any GPU run, check the new workspace's credit, payment method and spending limit on modal.com
(Usage / Billing). The H200 costs ~$4.54/h; a 2-epoch run took ~26 s/step × 372 steps.

To continue training from step 200, put the checkpoint back where `modal_train.py` looks for it
(`kb-finetune:/checkpoints/<run>/checkpoint-200`, adapter files + `resume/checkpoint-200/*`), then
`modal deploy` and spawn `train` with the same `run` name: it resumes automatically. Launch with
deploy + spawn, not `modal run --detach` (killing the launcher cancelled a detached run).
