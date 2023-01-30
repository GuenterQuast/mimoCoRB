from mimocorb import mimo_buffer as bm
import os, sys
import numpy as np
import pandas as pd
import pathlib
import tarfile
import time
import ctypes

class SimulationSource:
    def __init__(self, source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):

        # general part for each function (template)
        if sink_list is None:
            raise ValueError("ERROR! Faulty ring buffer configuration (sink in picoscope_source: OscilloscopeSource)!!")

        self.sink = None
        for key, value in rb_info.items():
            if value == 'read':
                for i in range(len(source_list)):
                    pass
            elif value == 'write':
                for i in range(len(sink_list)):
                    self.sink = bm.Writer(sink_list[i])
            elif value == 'observe':
                for i in range(len(observe_list)):
                    pass

        if self.sink is None:
            raise ValueError("ERROR! Faulty ring buffer configuration passed!")

        #print(config_dict)

        # evaluate configuration dictionary
        self.events_required = 1000 if "eventcount" not in config_dict \
            else config_dict["eventcount"]            
        self.sleeptime = 0.10 if "sleeptime" not in config_dict \
            else config_dict["sleeptime"]
        self.random = False if "random" not in config_dict \
            else config_dict["random"]
        self.number_of_samples = config_dict["number_of_samples"]
        self.sample_time_ns = config_dict["sample_time_ns"]
        self.pre_trigger_samples = config_dict["pre_trigger_samples"]
        self.analogue_offset_mv = config_dict["analogue_offset"]*1000.
        self.number_of_channels = len(self.sink.dtype)
        
        # initialisation
        self.event_count = 0
        self.init_simulation()
        
    def init_simulation(self):
        self.plen = 400//self.sample_time_ns # 400 ns pulse windowd 
        tau = self.plen/4. # decay time of exponential pulse
        self.mn_position = self.pre_trigger_samples
        self.mx_position = self.number_of_samples - self.plen
        self.maxheight= 750.        
        self.pulse_template = \
          np.exp(-np.float64(np.linspace(0., self.plen, self.plen, endpoint=False))/tau)
        self.tau_mu = 2200 # muyon life time in ns
        self.detector_efficiency = 0.95
        self.stopping_probability = 0.10
        
    def get_simpulses(self, nchan=3):
        """generate simulated data
        """

        # initialise with noise signal
        noise=self.maxheight/50.
        pulse = np.float64(noise * (0.5-np.random.rand(nchan, self.number_of_samples)) ) 

        # one pulse at trigger position in layers one and two
        for ip in range(min(2,nchan)):
            # random pulse height for trigger pulse
            pheight = np.random.rand()*self.maxheight
            if np.random.rand() < self.detector_efficiency:
              pulse[ip, self.mn_position:self.mn_position+self.plen] += pheight*self.pulse_template

        # return if muon was not stopped      
        if np.random.rand() > self.stopping_probability:
            return pulse + self.analogue_offset_mv
              
        # add delayed pulse(s)
        t_mu = -self.tau_mu * np.log(np.random.rand()) # muon life time
        pos2 = int(t_mu/self.sample_time_ns) + self.pre_trigger_samples
        if np.random.rand() > 0.5:  # upward decay electron
          for ip in range(0,min(nchan,2)):
           # random pulse height and position for 2nd pulse
             pheight2 = np.random.rand()*self.maxheight        
             if np.random.rand() < self.detector_efficiency and pos2 < self.mx_position:
               pulse[ip, pos2:pos2+self.plen] += pheight2 * self.pulse_template
        else:
          for ip in range(min(nchan,2), min(nchan,4)):
           # random pulse height and position for 2nd pulse
            pheight2 = np.random.rand()*self.maxheight        
            if np.random.rand() < self.detector_efficiency and pos2 < self.mx_position:
              pulse[ip, pos2:pos2+self.plen] += pheight2 * self.pulse_template

        return pulse + self.analogue_offset_mv
    
    def __del__(self):
        pass
        # TODO: remove debug or change to logger
        # print("?>", self.status)

    def start_data_capture(self):
        while self.event_count < self.events_required:
            self.event_count += 1
            if self.random: 
                 time.sleep(-self.sleeptime*np.log(np.random.rand())) # random Poisson sleept time
            else:
                 time.sleep(self.sleeptime)  # fixed sleep time
            # get new simulated pulses
            pulses = self.get_simpulses(self.number_of_channels)
            # get new buffer abd store event data and meta-data
            buffer = self.sink.get_new_buffer()
            buffer[:self.number_of_samples]['chA'] = pulses[0]
            if self.number_of_channels > 1:
                buffer[:self.number_of_samples]['chB'] = pulses[1]
            if self.number_of_channels > 2:
                buffer[:self.number_of_samples]['chC'] = pulses[2]
            if self.number_of_channels > 3:
                buffer[:self.number_of_samples]['chD'] = pulses[3]
            self.sink.set_metadata(self.event_count, time.time(), 0)
        self.sink.process_buffer()


def simulation_source(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    simulsource = SimulationSource(source_list, sink_list, observe_list, config_dict,  **rb_info)
    # TODO: Change to logger!
    # print("** simulation_source ** started, config_dict: \n", config_dict)
    # print("?> sample interval: {:02.1f}ns".format(osci.time_interval_ns.value))
    simulsource.start_data_capture()
