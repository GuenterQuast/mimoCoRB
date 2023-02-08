from mimocorb.buffer_control import SourceToBuffer
import numpy as np
import sys, time

def simulation_source(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    """Generate simulated data and pass data to class mimoCoRB.Source
    """
    
    # evaluate configuration dictionary
    events_required = 1000 if "eventcount" not in config_dict \
        else config_dict["eventcount"]            
    sleeptime = 0.10 if "sleeptime" not in config_dict \
        else config_dict["sleeptime"]
    random = False if "random" not in config_dict \
        else config_dict["random"]
    number_of_samples = config_dict["number_of_samples"]
    sample_time_ns = config_dict["sample_time_ns"]
    pre_trigger_samples = config_dict["pre_trigger_samples"]
    analogue_offset_mv = config_dict["analogue_offset"]*1000.

    plen = 400//sample_time_ns # 400 ns pulse windowd 
    tau = plen/4. # decay time of exponential pulse
    mn_position = pre_trigger_samples
    mx_position = number_of_samples - plen
    maxheight= 750.        
    noise=maxheight/50.
    pulse_template = \
        np.exp(-np.float64(np.linspace(0., plen, plen, endpoint=False))/tau)
    tau_mu = 2200 # muyon life time in ns
    detector_efficiency = 0.95
    stopping_probability = 0.10

    global event_count
    event_count = 0 
    
    def get_simpulses(nchan=3):
        """generate simulated data, called by instance of class mimoCoRB.SourceToBuffer
        """
        global event_count

        event_count +=1 
        if event_count > events_required:
            sys.exit()
    
        # repect wait time (rate adjustment)
        if random: # random ...
            time.sleep(-sleeptime*np.log(np.random.rand())) # random Poisson sleept time
        else:           # ... or fixed time 
            time.sleep(sleeptime)  # fixed sleep time

        # initialise with noise signal
        pulse = np.float64(noise * (0.5-np.random.rand(nchan, number_of_samples)) ) 

        # one pulse at trigger position in layers one and two
        for ip in range(min(2,nchan)):
            # random pulse height for trigger pulse
            pheight = np.random.rand()*maxheight
            if np.random.rand() < detector_efficiency:
              pulse[ip, mn_position:mn_position+plen] += pheight*pulse_template

        # return if muon was not stopped      
        if np.random.rand() < stopping_probability:              
            # add delayed pulse(s)
            t_mu = -tau_mu * np.log(np.random.rand()) # muon life time
            pos2 = int(t_mu/sample_time_ns) + pre_trigger_samples
            if np.random.rand() > 0.5:  # upward decay electron
              for ip in range(0,min(nchan,2)):
                 # random pulse height and position for 2nd pulse
                 pheight2 = np.random.rand()*maxheight        
                 if np.random.rand() < detector_efficiency and pos2 < mx_position:
                   pulse[ip, pos2:pos2+plen] += pheight2 * pulse_template
            else:
              for ip in range(min(nchan,2), min(nchan,4)):
                # random pulse height and position for 2nd pulse
                pheight2 = np.random.rand()*maxheight        
                if np.random.rand() < detector_efficiency and pos2 < mx_position:
                  pulse[ip, pos2:pos2+plen] += pheight2 * pulse_template

        pulse += analogue_offset_mv  # apply analogue offset
        return pulse
        
    simulsource = SourceToBuffer(
           sink_list, observe_list, config_dict, ufunc=get_simpulses, **rb_info)
    # TODO: Change to logger!
    # print("** simulation_source ** started, config_dict: \n", config_dict)
    # print("?> sample interval: {:02.1f}ns".format(osci.time_interval_ns.value))
    simulsource()
