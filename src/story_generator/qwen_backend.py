"""Qwen backend lazy-load; CPU tests inject loader, không cần GPU packages."""

from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import platform
import re
from time import perf_counter
from typing import Any, Callable

from .prompts import PROMPT_VERSION, build_story_messages


MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
MODEL_REVISION = "aa8e72537993ba99e69dfaafa59ed015b17504d1"


def _load_qwen_components(
    *, model_id: str, revision: str, device: str, cache_dir: str | None
) -> tuple[Any, Any, Any]:
    """Chỉ được gọi qua load/generate rõ ràng; không auto device_map/quantization."""
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("Qwen inference cần PyTorch riêng; không thuộc CPU requirements.") from exc
    device_index = int(device.split(":")[1])
    if not torch.cuda.is_available() or device_index >= torch.cuda.device_count():
        raise RuntimeError(f"Thiết bị {device} không khả dụng; không fallback sang CPU/mock.")
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Qwen inference cần Transformers trong môi trường Kaggle riêng.") from exc

    tokenizer = AutoTokenizer.from_pretrained(
        model_id, revision=revision, trust_remote_code=False, cache_dir=cache_dir
    )
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        dtype=torch.float16,
        trust_remote_code=False,
        use_safetensors=True,
        cache_dir=cache_dir,
    )
    return tokenizer, model, torch


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


class QwenStoryBackend:
    """Một model/tokenizer trên một GPU rõ ràng; không thread-safe hoặc auto retry."""

    def __init__(
        self,
        *,
        device: str = "cuda:0",
        max_new_tokens: int = 1024,
        repetition_penalty: float = 1.0,
        cache_dir: str | None = None,
        loader: Callable[..., tuple[Any, Any, Any]] | None = None,
    ) -> None:
        if not isinstance(device, str) or re.fullmatch(r"cuda:[0-9]+", device) is None:
            raise ValueError("Chọn một GPU rõ ràng dạng cuda:N; không tự phân phối model.")
        if type(max_new_tokens) is not int or max_new_tokens <= 0:
            raise ValueError("max_new_tokens phải là integer dương.")
        if (
            type(repetition_penalty) not in (int, float)
            or not math.isfinite(repetition_penalty)
            or repetition_penalty <= 0
        ):
            raise ValueError("repetition_penalty phải là số hữu hạn lớn hơn 0.")
        self._device = device
        self._cache_dir = cache_dir
        self._parameters = {
            "do_sample": False,
            "max_new_tokens": max_new_tokens,
            "num_beams": 1,
            "num_return_sequences": 1,
            "repetition_penalty": float(repetition_penalty),
            "return_dict_in_generate": False,
            "output_scores": False,
        }
        self._loader = loader if loader is not None else _load_qwen_components
        self._execution_mode = "injected" if loader is not None else "transformers"
        self._components: tuple[Any, Any, Any] | None = None
        self._last_run: dict[str, Any] | None = None

    @property
    def generation_parameters(self) -> dict[str, Any]:
        """Caller không sửa trực tiếp cấu hình bên trong instance."""
        return deepcopy(self._parameters)

    @property
    def last_run(self) -> dict[str, Any] | None:
        """Snapshot metadata, không tự log/save; validation do caller ghi riêng."""
        return deepcopy(self._last_run)

    def load(self) -> None:
        """Explicit load hoặc gọi lazy từ generate; cache sau khi load thành công."""
        if self._components is not None:
            return
        tokenizer, model, runtime = self._loader(
            model_id=MODEL_ID, revision=MODEL_REVISION,
            device=self._device, cache_dir=self._cache_dir,
        )
        model.to(self._device)
        model.eval()
        self._components = tokenizer, model, runtime

    def generate(self, summary: str) -> str:
        """Trả decoded continuation nguyên trạng; parsing/repair không thuộc backend."""
        self._last_run = {
            "model_id": MODEL_ID, "revision": MODEL_REVISION,
            "prompt_version": PROMPT_VERSION,
            "generation_parameters": self.generation_parameters,
            "device": self._device, "precision": "float16", "batch_size": 1,
            "execution_mode": self._execution_mode,
            "model_generation_config": None,
            "package_versions": {"python": platform.python_version()},
            "input_tokens": None, "generated_tokens": None,
            "generation_latency_seconds": None, "peak_allocated_vram_bytes": None,
            "gpu_model": None, "raw_output": None, "hit_max_new_tokens": None,
            "validation_outcome": "not_checked", "error_category": None,
        }
        phase = "input"
        try:
            messages = build_story_messages(summary)
            self._last_run["messages"] = messages
            self._last_run["prompt_sha256"] = hashlib.sha256(
                json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            phase = "load"
            self.load()
            tokenizer, model, runtime = self._components
            model_config = getattr(model, "generation_config", None)
            if model_config is not None:
                self._last_run["model_generation_config"] = model_config.to_dict()
            measured = self._execution_mode == "transformers"
            if measured:
                self._last_run["package_versions"].update({
                    name: _package_version(name)
                    for name in ("torch", "transformers", "huggingface-hub", "safetensors")
                })
                self._last_run["gpu_model"] = runtime.cuda.get_device_name(self._device)

            phase = "tokenization"
            chat_text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = tokenizer(
                chat_text, return_tensors="pt", add_special_tokens=False
            ).to(self._device)
            if inputs["input_ids"].shape[0] != 1:
                raise ValueError("QwenStoryBackend chỉ hỗ trợ batch size 1.")
            input_length = inputs["input_ids"].shape[1]
            self._last_run["input_tokens"] = input_length
            parameters = self.generation_parameters
            if tokenizer.eos_token_id is not None:
                parameters["pad_token_id"] = tokenizer.eos_token_id
            self._last_run["generation_parameters"] = deepcopy(parameters)

            phase = "generation"
            if measured:
                runtime.cuda.synchronize(self._device)
                runtime.cuda.reset_peak_memory_stats(self._device)
            start = perf_counter() if measured else None
            with runtime.inference_mode():
                output_ids = model.generate(**inputs, **parameters)
            if measured:
                runtime.cuda.synchronize(self._device)
                self._last_run["generation_latency_seconds"] = perf_counter() - start
                self._last_run["peak_allocated_vram_bytes"] = runtime.cuda.max_memory_allocated(self._device)
            if output_ids.shape[0] != 1 or output_ids.shape[1] < input_length:
                raise ValueError("Model phải trả một sequence gồm input và continuation.")
            continuation = output_ids[0, input_length:]
            count = continuation.numel()
            self._last_run["generated_tokens"] = count
            self._last_run["hit_max_new_tokens"] = count >= parameters["max_new_tokens"]
            phase = "decode"
            raw_output = tokenizer.decode(
                continuation, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )
            self._last_run["raw_output"] = raw_output
            return raw_output
        except Exception:
            self._last_run["error_category"] = f"{phase}_error"
            raise
