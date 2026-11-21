# -*- coding: utf-8 -*-
"""
core/gpu.py - Elige dónde corre onnxruntime: GPU NVIDIA (CUDA) si está disponible,
si no DirectML (cualquier GPU con DirectX 12) y, como último recurso, CPU.
Sin PyTorch: los detectores del nodo son modelos ONNX.

El nodo se instala con onnxruntime-directml (71 MB, sin DLL de CUDA). Medido en la
GTX 1650 Ti: RF-DETR Nano 28 ms (CUDA 30 ms), patentes 25 ms (CUDA 11 ms), mismos
resultados; motor completo con detección p95 83 ms. CUDA queda soportado si en un
equipo se instala onnxruntime-gpu con sus DLL.
"""

import os
import subprocess

import config

_info = None

# TensorRT aparece como disponible en onnxruntime-gpu, pero necesita sus propias
# DLL y compila cada modelo al arrancar: no se usa.
_GPU_PROVIDERS = ("CUDAExecutionProvider", "DmlExecutionProvider")


def _preload_cuda(ort):
    """onnxruntime-gpu no trae las DLL de CUDA/cuDNN: se cargan desde la carpeta
    cuda/ junto al programa (instalación) o, en desarrollo, desde los paquetes
    nvidia-* o la instalación de PyTorch que haya en el equipo."""
    if not hasattr(ort, "preload_dlls"):
        return
    local = os.path.join(config.BASE_DIR, "cuda")
    try:
        ort.preload_dlls(directory=local if os.path.isdir(local) else None)
    except Exception as e:
        print(f"[GPU] No se pudieron precargar las DLL de CUDA: {e}")


def _gpu_name() -> str:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        name = out.stdout.strip().splitlines()[0].strip() if out.returncode == 0 else ""
        return name or "GPU"
    except Exception:
        return "GPU"


def get_device_info() -> dict:
    """Retorna {'use_gpu', 'providers', 'name'} (se calcula una sola vez).
    'providers' es la lista para onnxruntime.InferenceSession, en orden de preferencia."""
    global _info
    if _info is not None:
        return _info

    _info = {"use_gpu": False, "providers": ["CPUExecutionProvider"], "name": "CPU"}
    if not getattr(config, "USE_GPU", True):
        print("[GPU] Desactivada por configuración (USE_GPU=False), usando CPU")
        return _info

    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        gpu = [p for p in _GPU_PROVIDERS if p in available]
        if not gpu:
            print(f"[GPU] onnxruntime sin proveedor de GPU ({available}), usando CPU")
            return _info
        if gpu[0] == "CUDAExecutionProvider":
            _preload_cuda(ort)
        _info = {
            "use_gpu": True,
            "providers": gpu[:1] + ["CPUExecutionProvider"],
            "name": _gpu_name(),
        }
        print(f"[GPU] {gpu[0].replace('ExecutionProvider', '')}: {_info['name']}")
    except Exception as e:
        print(f"[GPU] Error detectando la GPU, usando CPU: {e}")
    return _info


def confirm_provider(session) -> None:
    """Si la sesión no logró usar la GPU (DLL faltantes), lo informa en el HUD y la consola."""
    global _info
    if _info and _info["use_gpu"] and session.get_providers()[0] == "CPUExecutionProvider":
        print("[GPU] ADVERTENCIA: onnxruntime no pudo iniciar la GPU; los modelos corren en CPU")
        _info = {"use_gpu": False, "providers": ["CPUExecutionProvider"], "name": "CPU"}
