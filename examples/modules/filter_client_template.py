"""
This template of a filter client can be used as a starting point for writing you own filter client.
A filter in this context transfers the data of a ringbuffer to the next if certain conditions are met.
"""

from mimocorb.buffer_control import rbTransfer
import os
import sys


# define condx(input_data, confx) functions here or in a seperate file
# from filters import *


def filter_name(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    # filter client framework for mimoCoRB

    if config_dict is None:
        raise ValueError("ERROR! Wrong configuration passed in filter_name")

    # Load configuration
    conf1 = config_dict["conf1"]
    conf2 = config_dict["conf2"]

    def filter(input_data):
        """
        This function is a template of a filter function.

        Args:
            input_data (numpy structured array): The input data to be filtered. It can be accessed by the names from the setup file or by iterating over the keys.
        Returns:
            numpy structured array: The filtered input data.
        """
        keys = input_data.dtype.names
        # return None if cond1(input_data, conf1) # -> takes the whole input_data as an argument
        for key in keys:
            # return None if cond2(input_data[key], conf2) # -> takes only a single column of the input_data as an argument
            pass
        # if none of the conditions is met, transfer data to next ringbuffer
        return input_data

    p_filter = rbTransfer(
        source_list=source_list, sink_list=sink_list, config_dict=config_dict, ufunc=filter, **rb_info
    )
    p_filter()


if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, "-"))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
