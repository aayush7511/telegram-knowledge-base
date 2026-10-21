"""Serves one open model with vLLM on a Modal A100, as an OpenAI-compatible endpoint for bench.py.

We load the exact Hugging Face weights ourselves, so nobody can swap the model (DeepInfra redirected
retired small models to bigger ones). Scales to zero 5 minutes after the last request.

    MODEL=Qwen/Qwen3.5-4B modal serve modal_vllm.py   # ephemeral: stops when this process exits
    MODEL=openai/gpt-oss-120b GPU=H100 modal serve modal_vllm.py

One app per model (name from MODEL), so several models can be served at once.

With LORA_REPO (a private HF repo), the adapter is downloaded at startup with the Modal secret
`huggingface` (HF_TOKEN) and served as model name `graphiti` next to the base model:

    MODEL=unsloth/Qwen3.5-35B-A3B LORA_REPO=aayush7511/qwen3.5-35b-a3b-graphiti-lora GPU=H100 TIMEOUT=9000 modal serve modal_vllm.py

Needs MODAL_VLLM_KEY in .env (any random string); bench.py sends it as the API key.
"""
import os
import subprocess

import modal

# CUDA devel base: FlashInfer JIT-compiles kernels at startup and needs nvcc.
image = (modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu24.04", add_python="3.12")
         .uv_pip_install("vllm==0.30.0"))
hf_cache = modal.Volume.from_name("kb-bench-hf-cache", create_if_missing=True)  # weights download once
if modal.is_local() and len(os.environ.get("MODAL_VLLM_KEY", "")) < 16:
    # An empty key starts vLLM with no auth: a public URL anyone could use on our credit (happened 2026-10-18).
    raise SystemExit("MODAL_VLLM_KEY missing or too short in the environment; refusing to start an open endpoint")
app = modal.App("kb-bench-" + "".join(c if c.isalnum() else "-" for c in os.environ.get("MODEL", "none").split("/")[-1].lower()))


@app.function(image=image, cpu=4, memory=8192, timeout=3600, volumes={"/root/.cache/huggingface": hf_cache},
              secrets=[modal.Secret.from_dict({"MODEL": os.environ.get("MODEL", "")})])
def download() -> None:
    """Base weights into the cache volume on a CPU box (cents), so the GPU never waits on the download:
    MODEL=... modal run modal_vllm.py::download"""
    from huggingface_hub import snapshot_download
    print(snapshot_download(os.environ["MODEL"]))
    hf_cache.commit()


@app.function(image=image, gpu=os.environ.get("GPU", "A100-40GB"), volumes={"/root/.cache/huggingface": hf_cache},
              secrets=[modal.Secret.from_dict({"MODEL": os.environ.get("MODEL", ""),
                                               "LORA_REPO": os.environ.get("LORA_REPO", ""),
                                               "MAX_LEN": os.environ.get("MAX_LEN", "32768"),
                                               "VLLM_API_KEY": os.environ.get("MODAL_VLLM_KEY", "")})]
              + ([modal.Secret.from_name("huggingface")] if os.environ.get("LORA_REPO") else []),
              scaledown_window=300, timeout=int(os.environ.get("TIMEOUT", "3600")), max_containers=1)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=900)
def serve():
    model = os.environ["MODEL"]
    lora = []
    if os.environ.get("LORA_REPO"):  # adapter from a private repo; HF_TOKEN comes from the `huggingface` secret
        from huggingface_hub import snapshot_download
        path = snapshot_download(os.environ["LORA_REPO"], token=os.environ["HF_TOKEN"],
                                 allow_patterns=["adapter_*", "*.json", "*.jinja"])  # not the resume/ state
        lora = ["--enable-lora", "--lora-modules", f"graphiti={path}", "--max-lora-rank", "16", "--max-loras", "1"]
    subprocess.Popen(["vllm", "serve", model, "--served-model-name", model, "--host", "0.0.0.0", "--port", "8000",
                      "--max-model-len", os.environ.get("MAX_LEN", "32768"), "--api-key", os.environ["VLLM_API_KEY"], *lora])
    # No --enforce-eager: without CUDA graphs these small models generated only ~20–35 tokens/s.
