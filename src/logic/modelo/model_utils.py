import gc
import os

import torch

from logic.modelo.model_architecture import BuildingRoadModel
from logic.utils.config_manager import settings


def _infer_out_classes(state_dict: dict) -> int:
    """
    Intenta inferir numero de clases desde la capa de salida del checkpoint.
    Retorna 1 por defecto (flujo binario actual).
    """
    candidate_keys = (
        "model.segmentation_head.0.weight",
        "segmentation_head.0.weight",
    )
    for key in candidate_keys:
        weight = state_dict.get(key)
        if hasattr(weight, "shape") and len(weight.shape) >= 1:
            return int(weight.shape[0])
    return 1


def cargar_recargar_modelo(
    model: BuildingRoadModel | None = None,
) -> tuple[bool, BuildingRoadModel | None, str]:
    """
    Libera el modelo previo y carga un checkpoint para inferencia.
    Soporta:
    - Checkpoint wrapper con clave "state_dict".
    - Checkpoint directo del sub-modelo smp.
    """
    if model is not None:
        limpiar_memoria(model)
        model = None

    nueva_ruta = settings.model_path

    try:
        if not os.path.exists(nueva_ruta):
            settings.model_path = ""
            model = None
            return False, None, "Archivo no encontrado"
        checkpoint = torch.load(
            nueva_ruta,
            map_location=settings.torch_device,
            weights_only=True,
        )

        state_dict = checkpoint["state_dict"] if isinstance(checkpoint, dict) and "state_dict" in checkpoint else checkpoint
        out_classes = _infer_out_classes(state_dict if isinstance(state_dict, dict) else {})
        encoder_name = settings.model_encoder
        model = BuildingRoadModel("Unet", encoder_name, in_channels=3, out_classes=out_classes)

        if not isinstance(state_dict, dict):
            return False, None, "Formato de checkpoint no soportado"

        is_wrapper_state = any(k.startswith("model.") or k in ("mean", "std") for k in state_dict.keys())

        if is_wrapper_state:
            model.load_state_dict(state_dict)
            print(f"Pesos cargados. Mejor perdida registrada: {checkpoint.get('best_val_loss', 'N/A') if isinstance(checkpoint, dict) else 'N/A'}")
        else:
            model.model.load_state_dict(state_dict)
            print("Pesos cargados directamente en sub-modelo.")

        model.to(settings.torch_device)
        model.eval()

        return True, model, f"Modelo cargado: {os.path.basename(nueva_ruta)} ({encoder_name})"

    except Exception as e:
        detailed_error = str(e)
        print(f"Error detallado: {detailed_error}")
        if "Error(s) in loading state_dict" in detailed_error:
            return (
                False,
                None,
                (
                    f"Error: pesos incompatibles con encoder '{settings.model_encoder}'. "
                    f"Verifica que el modelo haya sido entrenado con ese encoder.\n{detailed_error}"
                ),
            )
        return False, None, f"Error: {detailed_error}"


def limpiar_memoria(model: BuildingRoadModel = None):
    """
    Libera memoria RAM/VRAM asociada al modelo.
    """
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
