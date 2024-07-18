"""
    This template of a analyzer client can be used as a starting point for writing you own analyzer client.
    A analyzer in this context reads the data of a ringbuffer, analyzes it and writes the result to another ringbuffer
"""

from mimocorb.buffer_control import rbTransfer
import os
import sys
import numpy as np


# define workerx(input_data, confx) functions here or in a separate file
#from analyzers import *



def analyzer_name(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    # filter client framework for mimoCoRB
    
    if config_dict is None:
        raise ValueError("ERROR! Wrong configuration passed in analyzer_name")

    # Load configuration
    conf1 = config_dict['conf1']
    conf2 = config_dict['conf2']
    
    output_dtype = sink_list[-1]['dtype']
    
    def analyzer(input_data):   
        """ 
        This function is a template of a analyzer function.
        
        Args:
            input_data (numpy structured array): The input data to be analyzed. It can be accessed by the names from the setup file or by iterating over the keys.
        Returns:
            numpy structured array: The analyzed data with the names from the setup file.
        """
        keys = input_data.dtype.names
        output_data = np.zeros( (1,), dtype=output_dtype)
        
        # print(output_data.dtype.names)
        
        output_data[0]['key1'] = worker1(input_data, conf1)
        output_data[0]['key2'] = worker2(input_data['key3'], conf2)
        
        return [output_data]
        
    

    p_analyzer = rbTransfer(source_list=source_list, sink_list=sink_list, config_dict=config_dict,
                        ufunc=analyzer, **rb_info)
    p_analyzer()

if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
