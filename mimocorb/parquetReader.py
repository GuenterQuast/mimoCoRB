import numpy as np
import pandas as pd
import pathlib
import tarfile
import os
import time


class parquetReader:
    """read wavefoem data from parquet file"""

    def __init__(self, config_dict=None):
        supported_suffixes = [".tar", ".gz", ".tgz", ".bz2"]
        # evaluate configuration dictionary
        self.path = config_dict["path"]
        self.sleeptime = 0.10 if "sleeptime" not in config_dict else config_dict["sleeptime"]
        self.random = False if "random" not in config_dict else config_dict["random"]
        self.number_of_samples = config_dict["number_of_samples"]

        self.filenames = iter(
            [
                os.path.join(self.path, f)
                for f in os.listdir(self.path)
                if os.path.isfile(os.path.join(self.path, f)) and pathlib.Path(f).suffix in supported_suffixes
            ]
        )

        f = next(self.filenames)
        # print("** file_source: opening file: ", f, 10*' ' + '\n')
        self.in_tar = tarfile.open(f, "r:*")  # open with transparent compression

    def init(self, number_of_channels=None, number_of_values=None, channel_names=None):
        """set parameters from buffer configuration and initialize"""
        self.number_of_channels = number_of_channels
        self.number_of_values = number_of_values
        self.channel_names = channel_names

    def __call__(self):
        parquet = self.in_tar.next()
        if parquet is None:
            # open next file, if any
            try:
                f = next(self.filenames)
            except StopIteration:
                return None
            # print("** file_source: opening file: ", f, 10*' ' + '\n')
            self.in_tar = tarfile.open(f, "r:*")  # open with transparent compression
            parquet = self.in_tar.next()
            if parquet is None:
                return None

        # introduce random wait to mimic true data flow
        if self.random:
            time.sleep(-self.sleeptime * np.log(np.random.rand()))  # random Poisson sleep time
        else:
            time.sleep(self.sleeptime)  # fixed sleep time
        try:
            pd_data = pd.read_parquet(self.in_tar.extractfile(parquet))
        except FileNotFoundError:
            print("Could not open '" + str(parquet) + "' in '" + str(f) + "'")
            return None

        # data from file is pandas format, convert to array
        data = []
        for i in range(self.number_of_channels):
            data.append(pd_data[self.channel_names[i]].to_numpy())
        # deliver data
        return data
