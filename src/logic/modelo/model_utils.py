import os
import gc
import torch
from logic.modelo.model_architecture import BuildingRoadModel
from logic.utils.config_manager import settings

def cargar_recargar_modelo(model: BuildingRoadModel | None = None) -> tuple[bool, BuildingRoadModel, str]:
    """
    Libera el modelo previo de memoria y carga uno nuevo desde disco.

    Lee la ruta del modelo desde `settings.model_path`, valida su existencia,
    carga el checkpoint de PyTorch e instancia la arquitectura `BuildingRoadModel`.
    Soporta checkpoints con wrapper Lightning (`state_dict`) y checkpoints
    directos de `smp.Unet`.

    Args
    ----------
    model : BuildingRoadModel | None, optional
        Instancia del modelo actualmente cargado en memoria. Si se proporciona,
        se libera antes de cargar el nuevo. Por defecto None.

    Return
    -------
    tuple[bool, BuildingRoadModel | None, str]
        (True,  model, mensaje) → Carga exitosa. `model` listo para inferencia.
        (False, None,  mensaje) → Fallo. `model` es None y el mensaje describe el error.
    """
    # Limpieza de memoria PyTorch
    if model is not None:
        limpiar_memoria(model)
        model = None

    nueva_ruta = settings.model_path
    
    try:
        if not os.path.exists(nueva_ruta):
            settings.model_path = ""
            model = None
            return False, None, "Archivo no encontrado"
        
        # 1. Cargamos el diccionario (checkpoint)
        checkpoint = torch.load(nueva_ruta, map_location=settings.torch_device)
        
        # 2. Instanciamos la arquitectura vacía
        model = BuildingRoadModel("Unet", "resnet34", in_channels=3, out_classes=3)
        
        # 3. Extraemos los pesos del diccionario
        if 'state_dict' in checkpoint:
            model.load_state_dict(checkpoint['state_dict'])
            print(f"Pesos cargados. Mejor pérdida registrada: {checkpoint.get('best_val_loss', 'N/A')}")
        else:
            # El checkpoint es solo el state_dict de smp.Unet (sin wrapper Lightning)
            model.model.load_state_dict(checkpoint)
            print("Pesos cargados directamente en sub-modelo.")

        # 4. Preparar para inferencia
        model.to(settings.torch_device)
        model.eval()

        return True, model, f"Modelo cargado: {os.path.basename(nueva_ruta)}"
            
    except Exception as e:
        print(f"Error detallado: {e}")
        return False, None, f"Error: {str(e)}"

def limpiar_memoria(model: BuildingRoadModel = None):
    """
    Libera un modelo de la memoria RAM y VRAM.
    Elimina la referencia local al modelo y fuerza la recolección de basura.

    Args
    ----------
    model : BuildingRoadModel
        Instancia del modelo a liberar. No debe ser None.
    """
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()