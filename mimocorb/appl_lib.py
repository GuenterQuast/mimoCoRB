import os
import yaml
import numpy as np
from multiprocessing import Value  # Pool as po  # Process
import pandas as pd
import matplotlib.pyplot as plt
import time


# global objects
file_counter = Value('L')
# rate determination
start_val = list()
stop_val = list()


def appl_init():
    """Called in main_application: define user initialization logic (optional)"""
    pass


def appl_after_start():
    """Called in main_application: define logic after start - before stop (optional)"""
    pass


def appl_after_stop():
    """Called in main_application: define logic after stop (optional)"""
    pass


#   *** service function section ***
def user_appl_count():
    """to be used outside main"""
    file_counter.value += 1


def user_appl_print_count(loc=None):
    """to be used outside main"""
    swtc: bool = False
    if loc is not None:
        try:
            swtc = get_switch_config(loc, "count")
        except (KeyError, TypeError):
            pass
    if swtc:
        print('... files processed: ', file_counter.value, 'from', loc.split("/")[-1])


def user_appl_get_count():
    """to be used outside main"""
    return file_counter.value


def user_appl_loop_rate(loc=None):
    """to be used outside main"""
    # idea: use Timer / wait() / new thread / decorators / ...
    # switch info
    swtc: bool = False
    if loc is not None:
        try:
            swtc = get_switch_config(loc, "looprate")
        except (KeyError, TypeError):
            pass
    if swtc:
        # logic
        current_count = file_counter.value
        if not start_val and not stop_val:
            start_val.append([current_count, time.time()])
        elif start_val and not stop_val:
            stop_val.append([current_count, time.time()])

        if start_val and stop_val:
            delta_counts = stop_val[0][0] - start_val[0][0]  # should be 1
            delta_time = stop_val[0][1] - start_val[0][1]
            rate = delta_counts / delta_time  # try ...
            print('LoopRate :', rate, 'Hz', 'tdif: ', delta_time, 's', 'from', loc.split("/")[-1])
            del start_val[:]
            del stop_val[:]


def user_appl_direct_rate(starttime=None, stoptime=None, loc=None):
    """to be used outside main"""
    # idea: calculate time difference from outside ...
    # switch info
    swtc: bool = False
    if loc is not None:
        try:
            swtc = get_switch_config(loc, "deltarate")
        except (KeyError, TypeError):
            pass
    if swtc:
        # logic
        delta_time = stoptime - starttime
        rate = 1 / delta_time  # try ...
        print('DirectRate :', rate, 'Hz', 'tdif: ', delta_time, 's', 'from', loc.split("/")[-1])


def get_switch_config(loc=None, key=None):
    """to be used outside main"""
    cfg_name = "config/switch_config.yaml"  # always fix
    ret_swtc = False
    with open(os.path.abspath(cfg_name), "r") as stream:
        c_struc = yaml.load(stream, Loader=yaml.FullLoader)

    if loc is not None and key is not None:
        try:
            ret_swtc = c_struc[loc][key]
        except KeyError:
            ret_swtc = False
    return ret_swtc
    

def plot_source_content():   # (source_list=None, sink_list=None, observe_list=None, config_dict=None):
    directory = "source/"  # from config file or from a separate buffer
    for file in os.listdir(directory):
        if file.endswith(".txt"):
            print(os.path.join(directory, file))
            data = np.loadtxt(os.path.join(directory, file), skiprows=1)
            time, chA, chB, chC = [], [], [], []
            for t, a, b, c in data:
                time.append(t / 250)
                chA.append(a)
                chB.append(b)
                chC.append(c)
            plt.style.context("seaborn")
            plt.plot(time, chA, color='red', marker="", lw=0.5, label="Channel A")
            plt.plot(time, chB, color='green', marker="", lw=0.5, label="Channel B")
            plt.plot(time, chC, color='blue', marker="", lw=0.5, label="Channel C")
            plt.title("Muon lifetime pulses: " + file)
            plt.legend()
            plt.ylabel('Signal (mV)')
            plt.ylim(-500, 500)
            plt.xlim(0, 17)
            plt.xlabel('Time (µs)')
            plt.grid(color='grey', linestyle='-', linewidth=0.1)

            plt.ion()
            plt.show()
            plt.pause(2)
            plt.close()
            plt.ioff()
    print("Done - Plot(s)")
