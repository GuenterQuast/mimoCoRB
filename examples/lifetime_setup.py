#  Application example for mimoCoRB
#  --------------------------------
#
# three buffers:
#  - RB_1 for (simuated) raw waveforms
#  - RB_2 for selected double-pulses
#  - RB_3 for derived pulse parameters
#
#  data from RB_2 and RB_3 are saved to files in tarred parquet format
#  or in text format.
#
#  data from RB_2 are passed to an observer process driving a real-time display
#
# Notes:
# 
#    1. additional config files controlling the user functions are
#       located in the subdirectory config/
#    2. user necessary application-specific user code is located
#       in the subdirectory modules/
#
# ----------------------------------------------------------------------------
#

# general control options
output_directory: target     # directory to store output data
GUI_control: true            # control daq via Grapical User Interface
KBD_control: true            # control daq via KeyBoarD

RingBuffer:
  # define ring buffers
  - RB_1:
      # raw input data buffer (waveforms from PicoScope, file_source or simulation)
      number_of_slots: 128
      channel_per_slot: 4250
      data_type:
          1: ['chA', "float32"]
          2: ['chB', "float32"]
          3: ['chC', "float32"]
          4: ['chD', "float32"]          
  - RB_2:
      # buffer with accepted signatures (here double-pulses)
      number_of_slots: 128
      channel_per_slot: 4250
      data_type:
          1: ['chA', "float32"]
          2: ['chB', "float32"]
          3: ['chC', "float32"]
          4: ['chD', "float32"]          
  - RB_3:
      # buffer with pulse parameters (derived from waveforms)
      number_of_slots: 32
      channel_per_slot: 1
      data_type:
          1: ['decay_time', "int32"]
          3: ['1st_chA_h', "float32"]
          4: ['1st_chB_h', "float32"]
          5: ['1st_chC_h', "float32"]          
          6: ['1st_chA_p', "int32"]
          7: ['1st_chB_p', "int32"]
          8: ['1st_chC_p', "int32"]
          9: ['1st_chA_int', "float32"]
          10: ['1st_chB_int', "float32"]
          11: ['1st_chC_int', "float32"]
          12: ['2nd_chA_h', "float32"]
          13: ['2nd_chB_h', "float32"]
          14: ['2nd_chC_h', "float32"]
          15: ['2nd_chA_p', "int32"]
          16: ['2nd_chB_p', "int32"]
          17: ['2nd_chC_p', "int32"]
          18: ['2nd_chA_int', "float32"]
          19: ['2nd_chB_int', "float32"]
          20: ['2nd_chC_int', "float32"]
          21: ['1st_chD_h', "float32"]
          22: ['1st_chD_p', "int32"]
          23: ['1st_chD_int', "float32"]
          24: ['2nd_chD_h', "float32"]
          25: ['2nd_chD_p', "int32"]
          26: ['2nd_chD_int', "float32"]
Functions:
  # define functions and assignments
  - Fkt_main:
      config_file: "config/simulation_config.yaml"
  - Fkt_1:
       file_name: "modules/simul_source"
       fkt_name: "simul_source"
       num_process: 1
       RB_assign:
           RB_1: "write"
  - Fkt_2:
       file_name: "modules/lifetime_filter"
       fkt_name: "calculate_decay_time"
       num_process: 2
       RB_assign:
           RB_1: "read"     # input
           RB_2: "write"    # waveform to save (if double pulse was found)
           RB_3: "write"    # pulse data
  - Fkt_3:
      file_name: "modules/exporters"
      fkt_name: "save_to_txt"
      config_file: "config/save_lifetime.yaml"
      num_process: 1
      RB_assign:
           RB_3: "read"     # pulse data
  - Fkt_4:
      file_name: "modules/exporters"
      fkt_name: "save_parquet"
      num_process: 1
      RB_assign:
           RB_2: "read"     # waveform to save
  - Fkt_5:
      file_name: "modules/plot_waveform"
      fkt_name: "plot_waveform"
      num_process: 1
      RB_assign:
           RB_2: "observe"  # double pulse waveform
  - Fkt_6:
      file_name: "modules/plot_histograms"
      fkt_name: "plot_histograms"
      num_process: 1
      RB_assign:
           RB_3: "read"  # pulse parameters
