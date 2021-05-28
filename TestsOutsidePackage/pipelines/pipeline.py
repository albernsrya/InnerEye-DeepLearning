#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------

import os
import logging
from pathlib import Path

from azureml.core import Workspace, Experiment, Dataset as AMLDataset
from azureml.core.compute import AmlCompute
from azureml.core.conda_dependencies import CondaDependencies
from azureml.core.run import Run
from azureml.core.runconfig import DEFAULT_CPU_IMAGE, RunConfiguration
from azureml.data.abstract_datastore import AbstractDatastore
from azureml.data.datapath import DataPath
from azureml.data.output_dataset_config import OutputFileDatasetConfig
from azureml.pipeline.core import Pipeline
from azureml.pipeline.steps import PythonScriptStep

import numpy as np
import pandas as pd


logging.getLogger().setLevel(logging.INFO)

csv_file_path = "test_pipeline.csv"
datastore_target_path = "test_pipeline_path"


def line_func(x: np.ndarray, a: float, b: float) -> np.ndarray:
    """Line function."""
    return a * x + b


def create_test_data(add_noise: bool, filename: Path) -> None:
    xs = np.linspace(0, 10, 101)
    ys = line_func(xs, 2, 3)
    if add_noise:
        ys = ys + np.random.normal(0, 1, ys.size)

    df = pd.DataFrame({'x': xs, 'y': ys})
    df.to_csv(filename)


def prepare_test_data(datastore: AbstractDatastore) -> None:
    create_test_data(False, csv_file_path)

    datastore.upload_files([csv_file_path], target_path=datastore_target_path, overwrite=True)
    logging.info("Upload call completed")


def create_pipeline(ws: Workspace, datastore: AbstractDatastore, aml_compute: AmlCompute,
                    exp: Experiment) -> Run:
    prepare_test_data(datastore)

    input_datapath = DataPath(datastore=datastore,
                              path_on_datastore=datastore_target_path,
                              name="input_test_data")
    input_file_dataset = AMLDataset.File.from_files(path=input_datapath)
    step1_input_dataset_consumption = input_file_dataset.as_mount()

    prepared_data = OutputFileDatasetConfig(name='prepared_data',
                                            destination=(datastore, '/data')).as_mount()

    step2_input_dataset_consumption = prepared_data.as_input(name="training_data")

    processed_data2 = OutputFileDatasetConfig(name='processed_data2',
                                              destination=(datastore, '/data')).as_mount()

    step3_input_dataset_consumption = processed_data2.as_input(name="linear_regression_model")

    processed_data3 = OutputFileDatasetConfig(name='processed_data3',
                                              destination=(datastore, '/data')).as_mount()

    # create a new runconfig object
    run_config = RunConfiguration()

    # enable Docker
    run_config.environment.docker.enabled = True

    # set Docker base image to the default CPU-based image
    run_config.environment.docker.base_image = DEFAULT_CPU_IMAGE

    # use conda_dependencies.yml to create a conda environment in the Docker image for execution
    run_config.environment.python.user_managed_dependencies = False

    # specify CondaDependencies obj
    run_config.environment.python.conda_dependencies = CondaDependencies("environment.yml")

    source_directory = './step1'
    logging.info('Source directory for the step is %s.', os.path.realpath(source_directory))

    step1 = PythonScriptStep(script_name="step1.py",
                             name="data_preparation",
                             arguments=[
                                 "--input_step1_folder", step1_input_dataset_consumption,
                                 "--input_step1_file", csv_file_path,
                                 "--output_step1_folder", prepared_data,
                                 "--output_step1_file", "step1.csv"
                             ],
                             compute_target=aml_compute,
                             inputs=[step1_input_dataset_consumption],
                             outputs=[prepared_data],
                             source_directory=source_directory,
                             allow_reuse=True)
    logging.info("Step1 created: %s", step1)

    source_directory = './step2'
    logging.info('Source directory for the step is %s.', os.path.realpath(source_directory))

    # All steps use the same Azure Machine Learning compute target as well
    step2 = PythonScriptStep(script_name="step2.py",
                             name="training",
                             arguments=[
                                 "--input_step2_folder", step2_input_dataset_consumption,
                                 "--input_step2_file", "step1.csv",
                                 "--output_step2_folder", processed_data2,
                                 "--output_step2_file", "linear_regression.pt"],
                             compute_target=aml_compute,
                             runconfig=run_config,
                             inputs=[step2_input_dataset_consumption],
                             outputs=[processed_data2],
                             source_directory=source_directory,
                             allow_reuse=True)
    logging.info("Step2 created: %s", step2)

    source_directory = './step3'
    logging.info('Source directory for the step is %s.', os.path.realpath(source_directory))

    step3 = PythonScriptStep(script_name="step3.py",
                             name="step3",
                             arguments=[
                                 "--input_step3_folder", step3_input_dataset_consumption,
                                 "--input_step3_file", "step2.csv",
                                 "--output_step3", processed_data3,
                                 "--output_step3_file", "step3.csv"],
                             compute_target=aml_compute,
                             runconfig=run_config,
                             inputs=[step3_input_dataset_consumption],
                             outputs=[processed_data3],
                             source_directory=source_directory,
                             allow_reuse=True)
    logging.info("Step3 created")

    pipeline1 = Pipeline(workspace=ws, steps=[step3])
    logging.info("Pipeline is built")

    pipeline1.validate()
    logging.info("Pipeline validation complete")

    pipeline_run = exp.submit(pipeline1, regenerate_outputs=False)
    logging.info("Pipeline is submitted for execution")
    return pipeline_run