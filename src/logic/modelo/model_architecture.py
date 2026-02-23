import torch.nn as nn
import segmentation_models_pytorch as smp
import torch
from torch.optim import lr_scheduler


class BuildingRoadModel(nn.Module):
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
        # Normalize image
        image = (image - self.mean) / self.std
        mask = self.model(image)
        return mask

    def shared_step(self, batch, stage):
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

        self.log(f"{stage}_loss", loss, prog_bar=True, on_step=False, on_epoch=True)

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
        # promedio de loss SIEMPRE (incluye batches todo-ignore)
        avg_loss = torch.stack([x["loss"] for x in outputs]).mean()

        # filtra los que sí tienen métricas
        metric_outputs = [x for x in outputs if x["tp"] is not None]
        if len(metric_outputs) == 0:
            # no hubo píxeles válidos en toda la epoch
            return avg_loss

        tp = torch.cat([x["tp"] for x in metric_outputs])
        fp = torch.cat([x["fp"] for x in metric_outputs])
        fn = torch.cat([x["fn"] for x in metric_outputs])
        tn = torch.cat([x["tn"] for x in metric_outputs])

        per_image_iou = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro-imagewise")
        dataset_iou = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro")

        self.log_dict({
            f"{stage}_per_image_iou": per_image_iou,
            f"{stage}_dataset_iou": dataset_iou,
        }, prog_bar=True)

        return avg_loss
###############
    def shared_epoch_end(self, outputs, stage):
        # Aggregate step metrics
        tp = torch.cat([x["tp"] for x in outputs], dim=0)
        fp = torch.cat([x["fp"] for x in outputs], dim=0)
        fn = torch.cat([x["fn"] for x in outputs], dim=0)
        tn = torch.cat([x["tn"] for x in outputs], dim=0)

        # --------- IoU por clase (vector de tamaño C) ----------
        iou_per_class = smp.metrics.iou_score(tp, fp, fn, tn, reduction="none")
        # --------- F1 por clase (Dice/F1) ----------
        f1_per_class = smp.metrics.f1_score(tp, fp, fn, tn, reduction="none")

        # (Mantén también tus métricas globales si quieres)
        per_image_iou = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro-imagewise")
        dataset_iou = smp.metrics.iou_score(tp, fp, fn, tn, reduction="micro")

        metrics = {
            f"{stage}_per_image_iou": per_image_iou,
            f"{stage}_dataset_iou": dataset_iou,
        }

        # Log por clase
        for c in range(self.number_of_classes):
            cname = self.class_names[c] if hasattr(self, "class_names") else f"class_{c}"
            metrics[f"{stage}_iou_{cname}"] = iou_per_class[c]
            metrics[f"{stage}_f1_{cname}"] = f1_per_class[c]

        self.log_dict(metrics, prog_bar=True, on_epoch=True, on_step=False)


########################


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
        optimizer = torch.optim.Adam(self.parameters(), lr=2e-4)
        scheduler = lr_scheduler.CosineAnnealingLR(optimizer, T_max=50, eta_min=1e-5)
        return {
            "optimizer": optimizer,
            "lr_scheduler": {
                "scheduler": scheduler,
                "interval": "step",
                "frequency": 1,
            },
        }

    def save_best_model(self, filepath):
        if self.best_model_state_dict is not None:
            torch.save({
                'state_dict': self.best_model_state_dict,
                'best_val_loss': self.best_val_loss,
            }, filepath)
            print(f"Best model saved to {filepath} with validation loss: {self.best_val_loss:.4f}")
        else:
            print("No best model available to save. Training may not have started yet.")

    def load_best_model(self):
        if self.best_model_state_dict is not None:
            self.load_state_dict(self.best_model_state_dict)
            print(f"Loaded best model with validation loss: {self.best_val_loss:.4f}")
        else:
            print("No best model available to load.")