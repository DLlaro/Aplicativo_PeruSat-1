import torch.nn as nn
import segmentation_models_pytorch as smp
import torch
from torch.optim import lr_scheduler


class BuildingRoadModel(nn.Module):
    """
    Modelo de segmentación semántica multiclase para detección de edificios y vías.

    Envuelve una arquitectura de `segmentation_models_pytorch` (smp) e incorpora
    el ciclo de entrenamiento, validación y prueba compatible con PyTorch Lightning.
    Normaliza las imágenes internamente usando los parámetros del encoder seleccionado
    y guarda en memoria el mejor estado del modelo según la pérdida de validación.

    Args
    ----------
    arch: str
        Nombre de la arquitectura smp, ej: "Unet", "FPN", "DeepLabV3Plus"
    encoder_name: str
        Nombre del encoder/backbone, ej: "resnet34", "efficientnet-b4".
    in_channels: int
        Número de canales de entrada, ej: 3 para RGB.
    out_classes: int
        Número de clases de salida (incluyendo fondo si aplica).
    **kwargs
        Argumentos adicionales pasados a `smp.create_model`.

    Attributes
    ---------
    model: nn.Module
        Sub-modelo smp instanciado con la arquitectura y encoder indicados.
    number_of_classes : int
        Número de clases de salida.
    loss_fn: smp.losses.JaccardLoss
        Función de pérdida Jaccard multiclase con ignore_index=255.
    best_val_loss: float
        Mejor pérdida de validación registrada durante el entrenamiento.
    best_model_state_dict: dict | None
        Copia en CPU del state_dict correspondiente a `best_val_loss`.
    mean, std: torch.Tensor
        Buffers de normalización del encoder, shape (1, 3, 1, 1).

    Notes
    -----
    - La normalización se aplica internamente en `forward`, por lo que las
      imágenes de entrada deben estar en rango [0, 1] sin normalizar.
    - Los píxeles con etiqueta 255 son ignorados en la pérdida y en las métricas.
    - Para acceder a métricas por clase, define `self.class_names` como una lista
      de strings antes del entrenamiento, ej: ["background", "building", "road"].
    """
    def __init__(self, arch, encoder_name, in_channels, out_classes, **kwargs):
        super().__init__()
        self.model = smp.create_model(
            arch,
            encoder_name=encoder_name,
            in_channels=in_channels,
            classes=out_classes,
            **kwargs,
        )

        # Preprocessing parameters for image normalization
        params = smp.encoders.get_preprocessing_params(encoder_name)
        self.number_of_classes = out_classes
        self.register_buffer("std", torch.tensor(params["std"]).view(1, 3, 1, 1))
        self.register_buffer("mean", torch.tensor(params["mean"]).view(1, 3, 1, 1))

        # Loss function for multi-class segmentation

        ce = smp.losses.JaccardLoss (mode =  smp.losses.MULTICLASS_MODE, ignore_index=255 )
        #focal = smp.losses.FocalLoss(mode = smp.losses.MULTICLASS_MODE, ignore_index=255)
        self.loss_fn = ce#+ focal

        # Step metrics tracking
        self.training_step_outputs = []
        self.validation_step_outputs = []
        self.test_step_outputs = []

        #Faltaba
        self.best_val_loss = float("inf")
        self.best_model_state_dict = None


    def forward(self, image):
        """
        Normaliza la imagen y calcula los logits de segmentación.

        Args
        ----------
        image : torch.Tensor
            Tensor de shape (B, C, H, W) en rango [0, 1].

        Return
        -------
        torch.Tensor
            Logits crudos de shape (B, out_classes, H, W).
        """
        image = (image - self.mean) / self.std
        mask = self.model(image)
        return mask

    def shared_step(self, batch, stage):
        """
        Ejecuta un paso de forward + cálculo de pérdida y métricas para un batch.

        Ignora los píxeles con etiqueta 255 al calcular tp/fp/fn/tn. Si todos
        los píxeles del batch son ignorados (bloque negro), retorna tp=None
        para que `shared_epoch_end` lo filtre correctamente.

        args
        ----------
        batch : tuple[torch.Tensor, torch.Tensor]
            Par (image, mask) donde image es (B, C, H, W) y mask es (B, H, W).
        stage : str
            Prefijo para el logging, ej: "train", "valid", "test".

        return
        -------
        dict: 
            "loss", "tp", "fp", "fn", "tn". tp/fp/fn/tn son None si no hubo píxeles válidos en el batch.
        """
        image, mask = batch

        # Ensure that image dimensions are correct
        assert image.ndim == 4  # [batch_size, channels, H, W]

        # Ensure the mask is a long (index) tensor
        mask = mask.long()

        # Mask shape
        assert mask.ndim == 3  # [batch_size, H, W]

        # Predict mask logits
        logits_mask = self.forward(image)

        assert (
            logits_mask.shape[1] == self.number_of_classes
        )  # [batch_size, number_of_classes, H, W]

        # Ensure the logits mask is contiguous
        logits_mask = logits_mask.contiguous()

        # Compute loss using multi-class Dice loss (pass original mask, not one-hot encoded)
        loss = self.loss_fn(logits_mask, mask)

        # Apply softmax to get probabilities for multi-class segmentation
        prob_mask = logits_mask.softmax(dim=1)

        # Convert probabilities to predicted class labels
        pred_mask = prob_mask.argmax(dim=1)

        valid = (mask != 255)

        #Por si hay un bloque negro
        if valid.sum() == 0:
            return {"loss": loss, "tp": None, "fp": None, "fn": None, "tn": None}

        pred_v = pred_mask[valid]
        mask_v = mask[valid]

        tp, fp, fn, tn = smp.metrics.get_stats(
            pred_v, mask_v, mode="multiclass", num_classes=self.number_of_classes
        )

        return {
            "loss": loss,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        }

    def shared_epoch_end(self, outputs, stage):
        """
        Agrega las métricas de todos los steps de una época y las loguea.

        Filtra los outputs con tp=None (batches de píxeles ignorados) antes
        de concatenar. Loguea IoU y F1 globales y por clase si `self.class_names`
        está definido.

        args
        ----------
        outputs : list[dict]
            Lista de dicts retornados por `shared_step` durante la época.
        stage : str
            Prefijo para el logging, ej: "train", "valid", "test".

        return
        -------
        torch.Tensor
            Pérdida promedio de la época (scalar), usada para comparar
            con `best_val_loss` en `on_validation_epoch_end`.
        """
        avg_loss = torch.stack([x["loss"] for x in outputs]).mean()

        metric_outputs = [x for x in outputs if x["tp"] is not None]
        if len(metric_outputs) == 0:
            return avg_loss

        tp = torch.cat([x["tp"] for x in metric_outputs])
        fp = torch.cat([x["fp"] for x in metric_outputs])
        fn = torch.cat([x["fn"] for x in metric_outputs])
        tn = torch.cat([x["tn"] for x in metric_outputs])

        per_image_iou = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro-imagewise")
        dataset_iou   = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro")
        iou_per_class = smp.metrics.iou_score(tp, fp, fn, tn, reduction="none")
        f1_per_class  = smp.metrics.f1_score(tp, fp, fn, tn, reduction="none")

        metrics = {
            f"{stage}_per_image_iou": per_image_iou,
            f"{stage}_dataset_iou":   dataset_iou,

        }

        for c in range(self.number_of_classes):
            cname = self.class_names[c] if hasattr(self, "class_names") else f"class_{c}"
            metrics[f"{stage}_iou_{cname}"] = iou_per_class[c]
            metrics[f"{stage}_f1_{cname}"]  = f1_per_class[c]
            metrics[f"{stage}_loss"] = avg_loss

        self.log_dict(metrics, prog_bar=True, on_epoch=True, on_step=False)
        return avg_loss

    def training_step(self, batch, batch_idx):
        train_loss_info = self.shared_step(batch, "train")
        self.training_step_outputs.append(train_loss_info)
        return train_loss_info

    def on_train_epoch_end(self):
        self.shared_epoch_end(self.training_step_outputs, "train")
        self.training_step_outputs.clear()

    def validation_step(self, batch, batch_idx):
        valid_loss_info = self.shared_step(batch, "valid")
        self.validation_step_outputs.append(valid_loss_info)
        return valid_loss_info

    def on_validation_epoch_end(self):
        avg_val_loss = self.shared_epoch_end(self.validation_step_outputs, "valid")

        # Save best model based on validation loss
        if avg_val_loss < self.best_val_loss:
            self.best_val_loss = avg_val_loss
            self.best_model_state_dict = {k: v.cpu().clone() for k, v in self.state_dict().items()}
            print(f"\n✓ New best model saved with validation loss: {self.best_val_loss:.4f}")

        self.validation_step_outputs.clear()

    def test_step(self, batch, batch_idx):
        test_loss_info = self.shared_step(batch, "test")
        self.test_step_outputs.append(test_loss_info)
        return test_loss_info

    def on_test_epoch_end(self):
        self.shared_epoch_end(self.test_step_outputs, "test")
        self.test_step_outputs.clear()

    def configure_optimizers(self):
        """
        Configura el optimizador y el scheduler de tasa de aprendizaje.

        Optimizador : Adam con lr=2e-4.
        Scheduler   : CosineAnnealingLR con T_max=50, eta_min=1e-5,
                      ejecutado por época (interval='epoch').

        return
        ----------
        dict:
            compatible con PyTorch Lightning con claves
            'optimizer' y 'lr_scheduler'.
        """
        optimizer = torch.optim.Adam(self.parameters(), lr=2e-4)
        scheduler = lr_scheduler.CosineAnnealingLR(optimizer, T_max=50, eta_min=1e-5)
        return {
            "optimizer": optimizer,
            "lr_scheduler": {
                "scheduler": scheduler,
                "interval": "epoch",
                "frequency": 1,
            },
        }

    def save_best_model(self, filepath):
        """
        Guarda el mejor state_dict registrado durante el entrenamiento en disco.

        El checkpoint guardado contiene:
            - 'state_dict' : pesos del mejor modelo (en CPU).
            - 'best_val_loss' : pérdida de validación asociada.

        args
        ----------
        filepath : str
            Ruta completa del archivo de destino, ej: "checkpoints/best.pt".
        """
        if self.best_model_state_dict is not None:
            torch.save({
                'state_dict': self.best_model_state_dict,
                'best_val_loss': self.best_val_loss,
            }, filepath)
            print(f"Best model saved to {filepath} with validation loss: {self.best_val_loss:.4f}")
        else:
            print("No best model available to save. Training may not have started yet.")

    def load_best_model(self):
        """
        Restaura el modelo al mejor state_dict guardado en memoria.

        No lee desde disco; usa `self.best_model_state_dict` almacenado
        en RAM durante el entrenamiento. Si no hay estado guardado
        (entrenamiento no iniciado), imprime un aviso y no hace nada.
        """
        if self.best_model_state_dict is not None:
            self.load_state_dict(self.best_model_state_dict)
            print(f"Loaded best model with validation loss: {self.best_val_loss:.4f}")
        else:
            print("No best model available to load.")