import os
import gc
import torch
from logic.modelo.model_architecture import BuildingRoadModel
from logic.utils.config_manager import settings

def cargar_recargar_modelo(model: BuildingRoadModel = None)-> tuple[bool, BuildingRoadModel, str]:
    # Limpieza de memoria PyTorch
    if model is not None:
        del model
        model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    nueva_ruta = settings.model_path
    device = torch.device('cuda' if torch.cuda.is_available() and settings.use_gpu else 'cpu')
    
    try:
        if not os.path.exists(nueva_ruta):
            settings.model_path = ""
            model = None
            return False, None, "Archivo no encontrado"
        
            # 1. Cargamos el diccionario (checkpoint)

        checkpoint = torch.load(nueva_ruta, map_location=device)
        
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
        model.to(device)
        model.eval()

        return True, model, f"Modelo cargado: {os.path.basename(nueva_ruta)}"
            
    except Exception as e:
        print(f"Error detallado: {e}")
        return False, None, f"Error: {str(e)}"