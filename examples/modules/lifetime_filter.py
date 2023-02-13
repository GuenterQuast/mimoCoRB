"""Module **lifetime_filter** 

This (rather complex) module filters waveform data to search for valid
signal pulses in the channel data. The goal is to clearly identify coincidences
of signals in different layers (indiating the passage of a cosmic ray particle,
a muon) and find double-pulse signatures that a muon was stopped in
or near a detection layer where the resulting decay-electron produced a delayed
pulse. The time difference between the initial and the delayed pulses is
the individual lifetime of the muon.

Wave forms passing this filter-criterion an passed on to a new buffer; the 
decay time and the properties of the signal pulses (height, integral and 
postition in time) are written to another buffer. 

The relevant configuration parameters can be found in the section 
*calculate_decay_time:* of the configuration file. 

""" 

from mimocorb.buffer_control import BufferToBuffer
import numpy as np
import pandas as pd
import os, sys

from filters import *

def calculate_decay_time(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    """Calculate decay time as time between double pulses

       Input: 
         pulse wave forms

       Returns: 
         None if failed, input data and pulse parameters if successful
    """
    
    if config_dict is None:
        raise ValueError("ERROR! Wrong configuration passed (in lifetime_modules: calculate_decay_time)!!")

    # Load configuration
    sample_time_ns = config_dict["sample_time_ns"]
    analogue_offset = config_dict["analogue_offset"]*1000
    peak_minimal_prominence_initial = config_dict["peak_minimal_prominence_initial"]
    peak_minimal_prominence_secondary = config_dict["peak_minimal_prominence_secondary"]
    peak_minimal_prominence = min(peak_minimal_prominence_initial, peak_minimal_prominence_secondary)
    peak_minimal_distance = config_dict["peak_minimal_distance"]
    peak_minimal_width = config_dict["peak_minimal_width"]
    pre_trigger_samples = config_dict["pre_trigger_samples"]
    trigger_position_tolerance = config_dict["trigger_position_tolerance"]
    signatures = config_dict["signatures"]

    # get format of pulse parameter array from sink[1]
    if len(sink_list) > 1:
        store_pulse_parameters = True  
        pulse_par_dtype = sink_list[1]['dtype']
    else:
        store_pulse_parameters = False        
    
#    pulse_par_dtype = np.dtype( [('decay_time', 'int32'), 
#                        ('1st_chA_h', 'float64'), ('1st_chB_h', 'float64'), ('1st_chC_h', 'float64'), 
#                        ('1st_chA_p', 'int32'), ('1st_chB_p', 'int32'), ('1st_chC_p', 'int32'), 
#                        ('1st_chA_int', 'float64'), ('1st_chB_int', 'float64'), ('1st_chC_int', 'float64'), 
#                        ('2nd_chA_h', 'float64'), ('2nd_chB_h', 'float64'), ('2nd_chC_h', 'float64'), 
#                        ('2nd_chA_p', 'int32'), ('2nd_chB_p', 'int32'), ('2nd_chC_p', 'int32'), 
#                        ('2nd_chA_int', 'float64'), ('2nd_chB_int', 'float64'), ('2nd_chC_int', 'float64'), 
#                        ('1st_chD_h', 'float64'), ('1st_chD_p', 'int32'), ('1st_chD_int', 'float64'), 
#                        ('2nd_chD_h', 'float64'), ('2nd_chD_p', 'int32'), ('2nd_chD_int', 'float64')] )
    
    def find_double_pulses(input_data):   
        """filter data, function to be called by instance of class mimoCoRB.BufferToBuffer

           Args:  input data as structured ndarray
    
           Returns: list of parameterized data
        """

        # Find all the peaks and store them in a dictionary
        peaks, peaks_prop = tag_peaks(input_data, peak_minimal_prominence, peak_minimal_distance, peak_minimal_width)
        
        # Group the found peaks (assumtion from here on: 1st group = muon, 2nd group = electron/positron)
        correlation_matrix = correlate_peaks(peaks, trigger_position_tolerance)
        
        # Are there at least two peaks?
        if len(correlation_matrix) < 2:
            return None   

        # Make sure "minimal prominence" criteria are met
        for ch in correlation_matrix.dtype.names:
            idx = correlation_matrix[ch][0]     # 1st pulse
            if idx >= 0:
                if peaks_prop[ch]["prominences"][idx]*config_dict["{:s}_scaling".format(ch)] < peak_minimal_prominence_initial:
                    correlation_matrix[ch][0] = -1
            idx = correlation_matrix[ch][1]     # 2nd pulse
            if idx >= 0:
                if peaks_prop[ch]["prominences"][idx]*config_dict["{:s}_scaling".format(ch)] < peak_minimal_prominence_secondary:
                    correlation_matrix[ch][1] = -1
        
        pulse_parameters = None
        signature_type= None  
        # Look for double pulses (hinting towards a muon decay)
        for _sigtype, sig in enumerate(signatures):
            if match_signature(correlation_matrix, sig):
                pulse_parameters= np.zeros( (1,), dtype=pulse_par_dtype)
                first_pos = []
                second_pos = []
                for ch in correlation_matrix.dtype.names:
                    # Process first peak (muon)
                    idx = correlation_matrix[ch][0]
                    if idx >= 0:
                        p_pos = peaks[ch][idx]
                        p_height = peaks_prop[ch]["prominences"][idx]
                        this_pulse, p_new_pos, p_int = normed_pulse(input_data[ch], p_pos, p_height, analogue_offset)
                        first_pos.append(p_pos)
                        pulse_parameters["1st_{:s}_p".format(ch)] = p_pos
                        pulse_parameters["1st_{:s}_h".format(ch)] = p_height
                        pulse_parameters["1st_{:s}_int".format(ch)] = p_int,
                    
                    # Process second peak (electron/positron)
                    idx = correlation_matrix[ch][1]
                    if idx >= 0:
                        p_pos = peaks[ch][idx]
                        p_height = peaks_prop[ch]["prominences"][idx]
                        this_pulse, p_new_pos, p_int = normed_pulse(input_data[ch], p_pos, p_height, analogue_offset)
                        second_pos.append(p_pos)
                        pulse_parameters["2nd_{:s}_p".format(ch)] = [p_pos,]
                        pulse_parameters["2nd_{:s}_h".format(ch)] = [p_height,]
                        pulse_parameters["2nd_{:s}_int".format(ch)] = [p_int,]

                pulse_parameters['decay_time'] = [(np.mean(second_pos) - np.mean(first_pos)) * sample_time_ns,]
                signature_type = _sigtype

        if pulse_parameters is None:
            return None
        else:
            if store_pulse_parameters:
                if len(sink_list) == 2:
                    return [pulse_parameters]  # send pulse parameters
                elif len(sink_list) == 3:
                    if signature_type == 0:
                         return [pulse_parameters, None]  # pulse parameters decay to top              
                    elif signature_type == 1:
                         return [None, pulse_parameters]  # pulse paramerters decay to bottom              
            else:
                return 1                   # only copy data   


    accessor = BufferToBuffer(
        source_list, sink_list, observe_list, config_dict, ufunc=find_double_pulses, **rb_info)
    accessor()

    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
