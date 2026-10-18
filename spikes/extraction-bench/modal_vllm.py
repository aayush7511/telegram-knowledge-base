"""Serves one open model with vLLM on a Modal A100, as an OpenAI-compatible endpoint for bench.py.

We load the exact Hugging Face weights ourselves, so nobody can swap the model (DeepInfra redirected
retired small models to bigger ones). Scales to zero 5 minutes after the last request.

    MODEL=Qwen/Qwen3.5-4B modal serve modal_vllm.py   # ephemeral: stops when this process exits
    MODEL=openai/gpt-oss-120b GPU=H100 modal serve modal_vllm.py

One app per model (name from MODEL), so several models can be served at once.

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


@app.function(image=image, gpu=os.environ.get("GPU", "A100-40GB"), volumes={"/root/.cache/huggingface": hf_cache},
              secrets=[modal.Secret.from_dict({"MODEL": os.environ.get("MODEL", ""),
                                               "VLLM_API_KEY": os.environ.get("MODAL_VLLM_KEY", "")})],
              scaledown_window=300, timeout=3600, max_containers=1)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=900)
def serve():
    model = os.environ["MODEL"]
    subprocess.Popen(["vllm", "serve", model, "--served-model-name", model, "--host", "0.0.0.0", "--port", "8000",
                      "--max-model-len", "32768", "--api-key", os.environ["VLLM_API_KEY"]])
    # No --enforce-eager: without CUDA graphs these small models generated only ~20–35 tokens/s.
