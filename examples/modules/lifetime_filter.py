from mimocorb.access_classes import Buffer_to_buffer
import numpy as np
import pandas as pd
import os, sys


from modules.filter import *


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

    def find_double_pulses(input_data):   
        
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
        # Look for double pulses (hinting towards a muon decay)
        for sig in signatures:
            if match_signature(correlation_matrix, sig):
                pulse_parameters= pd.DataFrame()
                # pulse_parameters[:] = 0
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
                        pulse_parameters["1st_{:s}_p".format(ch)] = [p_pos,]
                        pulse_parameters["1st_{:s}_h".format(ch)] = [p_height,]
                        pulse_parameters["1st_{:s}_int".format(ch)] = [p_int,]
                    
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

        if pulse_parameters is not None:
            return input_data, pulse_parameters
        else:
            return None

    accessor = Buffer_to_buffer(
        source_list, sink_list, observe_list, config_dict, filter=find_double_pulses, **rb_info)
    accessor.process_data()

    
if __name__ == "__main__":
    print("Script: " + os.path.basename(sys.argv[0]))
    print("Python: ", sys.version, "\n".ljust(22, '-'))
    print("THIS IS A MODULE AND NOT MEANT FOR STANDALONE EXECUTION")
