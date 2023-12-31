"""
**simulation_source**: Generate simulated wave form data
"""

from mimocorb.buffer_control import rbImport
import numpy as np
import sys, time


def simulation_source(source_list=None, sink_list=None, observe_list=None, config_dict=None, **rb_info):
    """
    Generate simulated data and pass data to buffer

    The class mimocorb.buffer_control/rbImport is used to interface to the
    newBuffer and Writer classes of the package mimoCoRB.mimo_buffer

    :param config_dict: configuration dictionary

      - events_required: number of events to be simulated or 0 for infinite
      - sleeptime: (mean) time between events
      - random: random time between events according to a Poission process
      - number_of_samples, sample_time_ns, pretrigger_samples and analogue_offset
        describe the waveform data to be generated (as for oscilloscope setup)

    Internal parameters of the simulated physics process (the decay of a muon)
    are (presently) not exposed to user.
    """

    # evaluate configuration dictionary
    events_required = 1000 if "eventcount" not in config_dict else config_dict["eventcount"]
    sleeptime = 0.10 if "sleeptime" not in config_dict else config_dict["sleeptime"]
    random = False if "random" not in config_dict else config_dict["random"]
    number_of_samples = config_dict["number_of_samples"]
    analogue_offset_mv = config_dict["analogue_offset"] * 1000.0
    trigger_level = 0.0 if "trigger_level" not in config_dict else config_dict["trigger_level"] - analogue_offset_mv
    sample_time_ns = config_dict["sample_time_ns"]
    pre_trigger_samples = config_dict["pre_trigger_samples"]

    # parameters for simulation
    plen = 400 // sample_time_ns  # 400 ns pulse window
    tau = plen / 4.0  # decay time of exponential pulse
    mn_position = pre_trigger_samples
    mx_position = number_of_samples - plen
    pulse_width = 100.0
    pulse_height = 250.0
    pulse_template = np.exp(-np.float32(np.linspace(0.0, plen, plen, endpoint=False)) / tau)
    noise = pulse_height / 30.0
    tau_mu = 2200  # muyon life time in ns
    detector_efficiency = 0.95
    stopping_probability = 0.10

    def simulate(nchan):
        def get_pulse_height():
            """Function to generate random pulse height"""
            return pulse_height + pulse_width * np.random.normal() - pulse_width * np.log(np.random.rand())

        # initialize with noise signal
        pulse = np.float32(noise * (0.5 - np.random.rand(nchan, number_of_samples)))

        if np.random.rand() < stopping_probability:  # stopped muon ?
            stopped_mu = True
            n1st = min(2, nchan)  # only 2 layers for 1st pulse
        else:
            stopped_mu = False  # 4 layers for passing muon
            n1st = nchan

        # one pulse at trigger position in layers one and two
        for i_layer in range(n1st):
            # random pulse height for trigger pulse
            pheight = get_pulse_height()
            if i_layer == 0:
                #  respect trigger condition in layer 1
                while pheight < trigger_level:
                    pheight = get_pulse_height()
            if np.random.rand() < detector_efficiency:
                pulse[i_layer, mn_position : mn_position + plen] += pheight * pulse_template

        # return if muon was not stopped
        if stopped_mu:
            # add delayed pulse(s)
            t_mu = -tau_mu * np.log(np.random.rand())  # muon life time
            pos2 = int(t_mu / sample_time_ns) + pre_trigger_samples
            if np.random.rand() > 0.5:  # upward decay electron
                for i_layer in range(0, min(nchan, 2)):
                    # random pulse height and position for 2nd pulse
                    ## pheight2 = np.random.rand()*maxheight
                    pheight2 = get_pulse_height()
                    if np.random.rand() < detector_efficiency and pos2 < mx_position:
                        pulse[i_layer, pos2 : pos2 + plen] += pheight2 * pulse_template
            else:
                for i_layer in range(min(nchan, 2), min(nchan, 4)):
                    # random pulse height and position for 2nd pulse
                    ## pheight2 = np.random.rand()*maxheight
                    pheight2 = get_pulse_height()
                    if np.random.rand() < detector_efficiency and pos2 < mx_position:
                        pulse[i_layer, pos2 : pos2 + plen] += pheight2 * pulse_template

        pulse += analogue_offset_mv  # apply analogue offset
        return pulse

    def yield_simpulses():
        """generate simulated data, called by instance of class mimoCoRB.rbImport"""

        event_count = 0

        while events_required == 0 or event_count < events_required:
            # repect wait time (rate adjustment)
            if random:  # random ...
                time.sleep(-sleeptime * np.log(np.random.rand()))  # random Poisson sleept time
            else:  # ... or fixed time
                time.sleep(sleeptime)  # fixed sleep time

            pulse = simulate(number_of_channels)
            # deliver pulse data and no metadata
            yield (pulse, None)
            event_count += 1

    simulsource = rbImport(config_dict=config_dict, sink_list=sink_list, ufunc=yield_simpulses, **rb_info)
    number_of_channels = len(simulsource.sink.dtype)
    # possibly check consistency of provided dtype with simulation !

    # TODO: Change to logger!
    # print("** simulation_source ** started, config_dict: \n", config_dict)
    # print("?> sample interval: {:02.1f}ns".format(osci.time_interval_ns.value))
    simulsource()
