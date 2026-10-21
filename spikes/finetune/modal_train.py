"""Fine-tune Qwen3.5-35B-A3B with Unsloth on Modal (spec: specs/finetune-35b-pilot.md).

Same recipe as qwen35_35b_graphiti_lora.ipynb (bf16 LoRA r16, 6,144-token sequences, 2 epochs, loss on
the gold JSON only, thinking off), moved to Modal because Colab has no 80 GB GPU on this account.

    modal volume put kb-finetune ../memory-gen/out/hf-release/examples examples   # data, once
    modal run modal_train.py::download                  # CPU: weights into the HF cache volume, once
    modal run modal_train.py --max-steps 8              # GPU test: peak memory + speed, longest examples
    modal run modal_train.py --run r1                   # full run; adapter -> kb-finetune:/adapters/r1

No Hugging Face token on Modal: data comes from the volume and the adapter is pushed to the Hub from
your machine afterwards. GPU (default H100) and TIMEOUT (seconds, default 7200) come from the
environment, so a stuck run stops before it eats the remaining credit. The full run checkpoints to
kb-finetune:/checkpoints/<run> every 40 steps and resumes from there if Modal preempts the container.
"""
import os
import time

import modal

GPU = os.environ.get("GPU", "H200")  # H100 (80 GB) ran out of memory: 67 GB of weights + ~5 GB of expert LoRA state
TIMEOUT = int(os.environ.get("TIMEOUT", "7200"))
MODEL = "unsloth/Qwen3.5-35B-A3B"
UNSLOTH = "f2ebbb77b48cdf6777d228600f95c225d63f2939"  # pinned 2026-10-19
UNSLOTH_ZOO = "dbd5758aa497c0042800fe26d5951061ac8e6398"

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu24.04", add_python="3.12")
    .apt_install("git")
    .uv_pip_install("torch==2.8.0", "torchvision", "torchaudio==2.8.0", "triton>=3.3.0", "bitsandbytes",
                    "xformers==0.0.32.post2",
                    f"unsloth_zoo[base] @ git+https://github.com/unslothai/unsloth-zoo@{UNSLOTH_ZOO}",
                    f"unsloth[base] @ git+https://github.com/unslothai/unsloth@{UNSLOTH}")
    .uv_pip_install("tokenizers>=0.22.0,<=0.23.0", "trl==0.22.2", extra_options="--no-deps")
    .uv_pip_install("transformers==5.2.0")
    .uv_pip_install("torchao>=0.16.0", extra_options="--no-deps")
    .run_commands("unsloth install-kernels", gpu="L4")  # flash_attn / mamba_ssm only install when a GPU is visible
    .env({"HF_HOME": "/root/.cache/huggingface", "HF_HUB_ENABLE_HF_TRANSFER": "0",
          # experimental hybrid packing failed on Qwen3_5MoeGatedDeltaNet (varlen kernels not invoked)
          "UNSLOTH_EXPERIMENTAL_HYBRID_PACKING": "0"})
)
hf_cache = modal.Volume.from_name("kb-bench-hf-cache", create_if_missing=True)  # shared with modal_vllm.py
data = modal.Volume.from_name("kb-finetune", create_if_missing=True)
app = modal.App("kb-finetune-qwen35", image=image)
VOLUMES = {"/root/.cache/huggingface": hf_cache, "/data": data}


@app.function(cpu=4, memory=8192, timeout=3600, volumes=VOLUMES)
def download() -> None:
    """Weights into the cache volume on a CPU box, so the GPU never waits on a 70 GB download."""
    from huggingface_hub import snapshot_download
    path = snapshot_download(MODEL)
    hf_cache.commit()
    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)
    print(f"{MODEL}: {total / 2**30:.1f} GiB in {path}")


@app.function(gpu=GPU, timeout=TIMEOUT, volumes=VOLUMES)
def train(max_steps: int = 0, run: str = "r1") -> dict:
    """max_steps > 0: short test on the longest examples (no eval, nothing saved). 0: the full run."""
    import torch
    from datasets import load_dataset
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only
    from transformers import TrainerCallback
    from trl import SFTConfig, SFTTrainer

    t0 = time.time()
    max_seq_length, lora_rank = 6144, 16
    model, processor = FastLanguageModel.from_pretrained(MODEL, max_seq_length=max_seq_length,
                                                         load_in_4bit=False, fast_inference=False)
    tokenizer = processor.tokenizer
    model = FastLanguageModel.get_peft_model(
        model, r=lora_rank, lora_alpha=lora_rank, lora_dropout=0, bias="none", random_state=3407,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj",
                        "gate_up_proj"],  # LoRA on the MoE experts too
        use_gradient_checkpointing="unsloth")
    load_s = time.time() - t0

    ds = load_dataset("json", data_files={"train": "/data/examples/train.jsonl",
                                          "validation": "/data/examples/validation.jsonl"})

    def to_text(batch):
        return {"text": [tokenizer.apply_chat_template(list(m) + [{"role": "assistant", "content": t}],
                                                       tokenize=False, add_generation_prompt=False,
                                                       enable_thinking=False)
                         for m, t in zip(batch["messages"], batch["target"])]}

    train_ds, val_ds = ds["train"].map(to_text, batched=True), ds["validation"].map(to_text, batched=True)
    lengths = [len(tokenizer(t).input_ids) for t in train_ds["text"]]
    assert max(lengths) <= max_seq_length, f"longest example is {max(lengths)} tokens"
    ga = 4
    ckpt_dir = f"/data/checkpoints/{run}"

    class CommitOnSave(TrainerCallback):  # make each checkpoint survive a preemption
        def on_save(self, args, state, control, **kwargs):
            data.commit()
    if max_steps:  # worst case for memory: the longest examples first
        order = sorted(range(len(lengths)), key=lambda i: -lengths[i])[:max_steps * ga]
        train_ds = train_ds.select(order)
    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=train_ds,
        eval_dataset=None if max_steps else val_ds,
        args=SFTConfig(
            dataset_text_field="text", max_seq_length=max_seq_length, per_device_train_batch_size=1,
            gradient_accumulation_steps=ga, warmup_steps=0 if max_steps else 10,
            max_steps=max_steps or -1, num_train_epochs=2, learning_rate=2e-4, logging_steps=1 if max_steps else 10,
            eval_strategy="no" if max_steps else "epoch", optim="adamw_8bit",
            save_strategy="no" if max_steps else "steps", save_steps=40, save_total_limit=1,
            weight_decay=0.001, lr_scheduler_type="linear", seed=3407, report_to="none",
            output_dir="/tmp/out" if max_steps else ckpt_dir),
        callbacks=[] if max_steps else [CommitOnSave()])
    trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\n",
                                      response_part="<|im_start|>assistant\n")
    torch.cuda.reset_peak_memory_stats()
    t1 = time.time()
    resume = (not max_steps and os.path.isdir(ckpt_dir)
              and any(d.startswith("checkpoint-") for d in os.listdir(ckpt_dir)))
    stats = trainer.train(resume_from_checkpoint=True if resume else None)
    train_s = time.time() - t1
    steps = stats.global_step
    out ={"gpu": torch.cuda.get_device_name(0), "load_s": round(load_s), "train_s": round(train_s), "steps": steps,
           "peak_mem_gib": round(torch.cuda.max_memory_allocated() / 2**30, 1),
           "total_mem_gib": round(torch.cuda.get_device_properties(0).total_memory / 2**30, 1),
           "longest_tokens": max(lengths), "loss": stats.training_loss}
    if max_steps:
        per_token = train_s / max(1, sum(len(x) for x in trainer.train_dataset["input_ids"]))
        out["full_run_train_h_est"] = round(per_token * sum(lengths) * 2 / 3600, 2)
    else:
        path = f"/data/adapters/{run}"
        model.save_pretrained(path)
        tokenizer.save_pretrained(path)
        data.commit()
        out["adapter"] = path
    print(out)
    return out


@app.local_entrypoint()
def main(max_steps: int = 0, run: str = "r1") -> None:
    print(train.remote(max_steps=max_steps, run=run))
