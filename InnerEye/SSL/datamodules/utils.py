import multiprocessing
import torch
import pytorch_lightning as pl
from pl_bolts.datamodules import CIFAR10DataModule
from pl_bolts.models.self_supervised.simclr.transforms import SimCLREvalDataTransform, SimCLRTrainDataTransform
from .chestxray_datamodule import RSNAKaggleDataModule
from ..configs.config_node import ConfigNode

num_gpus = torch.cuda.device_count()
num_devices = num_gpus if num_gpus > 0 else 1


def create_ssl_data_modules(config: ConfigNode) -> pl.LightningDataModule:
    """
    Returns torch lightning data module.
    """
    num_workers = config.dataset.num_workers if config.dataset.num_workers else multiprocessing.cpu_count()

    if config.dataset.name == "RSNAKaggle":
        dm = RSNAKaggleDataModule(config, num_devices=num_devices, num_workers=num_workers)  # type: ignore
    elif config.dataset.name == "CIFAR10":
        dm = CIFAR10DataModule(num_workers=num_workers,
                                batch_size=config.train.batch_size // num_devices,
                                seed=1234,
                                val_split=5000)
        dm.prepare_data()  # downloads data if necessary
        dm.train_transforms = SimCLRTrainDataTransform(32)
        dm.val_transforms = SimCLREvalDataTransform(32)
        dm.setup()
        dm.class_weights = None
    else:
        raise NotImplementedError(f"No pytorch data module implemented for dataset type: {config.dataset.name}")
    return dm
