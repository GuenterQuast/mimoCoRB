===========================================================
mimoCoRB - multiple-in multile-out Configurable Ring Buffer
===========================================================


mimoCoRB -  multiple-in multile-out Configurable Ring Buffer: Overview
----------------------------------------------------------------------

**mimoCoRB**: multiple-in multiple-out Configurable Ring Buffer

The package **mimoCoRB** provides a central component of each data acquisition
system needed to record and pre-analyze data from randomly occurrig processes.
Typical examples are waveform data as provided by single-photon
counters or typical detectors common in quantum mechanical measurements
or in nuclear, particle physics and astro particle physics, e. g.
photo tubes, Geiger counters, avalanche photo-diodes or modern SiPMs.

The random nature of such processes and the need to keep read-out dead
times low requires an input buffer and a buffer manager running as
a background process. While a data source feeds data into the
ringbuffer, consumer processes are fed with an almost constant stream
of data to filter, reduce, analyze or simply visualize data and
on-line analysis results. Such consumers may be obligatory ones,
i. e. data acquisition pauses if all input buffers are full and an 
obligatory consumer is still busy processing. A second type of
random consumers or "observers" receives an event copy from the buffer
manager upon request, without pausing the data acquisition process.
Typical examples of random consumers are displays of a subset of the
wave forms or of intermediate analysis results.

This project originated from an attempt to structure and generalize
data acquision for several experiments in advanced physics laboratory
courses at Karlruhe Institute of Technology (KIT).

As a simple demonstration, we provide data from simulatd signals as would
be recored by a detector for comsmic myons with three detection layers.
Occasionally, such muons stop in an absorber between the 2nd and 3rd layer,
where they decay at rest and emit a high-energetic electron recorded as a
2nd pulse in one or two of the detection layers. After data acquitision, a
search for typical pulses is performed, data with detected double pulses are
selected and fed into a second buffer. A third buffer receives data in a
reduced format which only contains the parameters of found pulses.
These data and the wave forms of all double-pulses are finally stored
on disk. This application is a very typical example of the general
process of on-line data processing in modern experiments and may
serve as a starting point for own applications.


.. toctree::
   :maxdepth: 2
   :caption: Contents:



Detailed description of components
..................................


Ring buffer


Writer, Reader and Observer classes


User Access classes wrapping the mimoCoRB classes


Configuraion of DAQ with yaml files


### Simple application example (also provided as a unittest)

An application example of *mimo_buffer* is shown below.  
This code may serve as a starting point for own projects.
The set-up is as follows:

  2 ring buffers are defined:
  
    - input Buffer  RB_1: 10 ch x 1024 slots (int32)

    - output Buffer RB_2: 10 ch x 2 slots/ch (float64)
   
    Simple data is filled into RB_1, copied and extended by a process
    writing data into RB_2, and finally a reader process to check
    integrity and completenss of thd data. The most complex part of
    the code is in function *run_control()*, which demonstrates
    how to set up the buffers, define Reader and Writer instances
    and start the prallel processes for generating, processing
    and reading the data. 
   
The example including comment lines for explanation is shown here:

.. code-block:: python

  import time
  import unittest
  import numpy as np
  from multiprocessing import Process, Value
  from mimocorb import mimo_buffer as bm

  # global variables 
  N_requested = 1000  # numer of data injectios ("events")
  Time_tick = 0.001   # time between events
  Ncpu1 = 2           # number of parallel abalyzer processes

  def data_generator(sink_dict):
    """writes continuously rising integers to buffer specified in sink_dict
    """
    sink = bm.Writer(sink_dict)
    n=0
    # inject data
    for x in range(N_requested):
        buffer = sink.get_new_buffer() # get new buffer and pass last item
        #  random wait for next data item
        time.sleep(-Time_tick*np.log(np.random.rand() ))
        # fill "data"
        n += 1
        buffer[:] = n
    # process last data item
    sink.process_buffer()


  def analyzer(source_dict, sink_dict):
    """read from source and write first element and a time difference to sink
    """
    source = bm.Reader(source_dict)
    sink = bm.Writer(sink_dict)
    start_time = time.time()
    
    while True:
        input_data = source.get()
        output_data = sink.get_new_buffer()
        # process data
        output_data[0] = input_data[0]
        # mimick processing time
        time.sleep(2*Time_tick)
        output_data[1] = time.time() - start_time

        # 
        sink.process_buffer()


  def check_result(source_dict, res):
    """reads RB_2 and sum up the integer content (value should be sum(1 -35) = 630);

       sum is returned as shared memory Value-object
    """
    source = bm.Reader(source_dict)
    sum_rb = 0
    while True:
        input_data = source.get()
        res.value +=int(input_data[0])

  def run_control():
    """Setup buffers, start processes and shut_down when 1st writer done 
    """

    # Create ring buffers: #2: 10 channel, 2 value per channel
    #    (1: buffer content; 2: time difference as int)
    #    d_type = [('chA', np.float)]  #not necessary: always the same type
    generator_buffer = bm.NewBuffer(10, 1, np.int32)
    eval_buffer = bm.NewBuffer(10, 2, np.float32)

    # create readers first
    source_dic_gen = generator_buffer.new_reader_group()
    source_dic_eval = eval_buffer.new_reader_group()

    # Create worker processes (correct sequence: first action as last)
    process_list = []
    #  evaluation to test ring buffer behavior
    result = Value('i', 0)   # int variable in shared meomry
    process_list.append(Process(target=check_result,
                                args=(source_dic_eval, result)))
    # data transfer between the 2 buffers: generator_buffer -> eval_buffer
    sink_dic_eval = eval_buffer.new_writer()
    # work with all cpu's requested
    number_of_workers = Ncpu1
    for i in range(number_of_workers):
        process_list.append(Process(target=analyzer,
                                    args=(source_dic_gen, sink_dic_eval)))

    # fill buffer (generator_buffer) with data first
    sink_dic_gen = generator_buffer.new_writer()
    process_list.append(Process(target=data_generator,
                                args=(sink_dic_gen,)))

    for p in process_list:
        p.start()

    run_active = True
    while run_active:
       run_active = False if process_list[-1].exitcode==0 else True
       time.sleep(0.1)  # wait
        
    time.sleep(0.1)  # some grace-time for readers to finish

    generator_buffer.shutdown()
    eval_buffer.shutdown()
    del generator_buffer, eval_buffer

    for p in process_list:
        p.join()

    return result.value


  class RPTest(unittest.TestCase):

    def test_process(self):
        # start python test module and check result
        a = run_control()
        expected_result = N_requested*(N_requested+1)//2
        self.assertEqual(a, expected_result)  # expected result: sum(i); i = 1, N_requested


  if __name__ == "__main__":
    unittest.main(verbosity=2)
  #    print(process_buffer())


Access Classes in module *buffer_control*
-----------------------------------------

To ease user interaction with the buffer manager, a set of
additional classes is provided in the module *buffer_control*
to set-up and manage cascades of ringbuffers and the asscociated
sub-processes for filling, filtering and extracting data. These
classes are of interest for developers wanting to help improving
the package. 

  - `class buffer_control`
     Set-up and management ringbuffers and associated sub-processes

  - `class SourceToBuffer`
      Read data from source (e.g. from file, simulation, PicoScope etc.) 
      and put data in mimo_buffer

  - `class BufferToBuffer`
      Read data from input buffer, filter and write data to output buffer(s)
   
  - `class BufferToTxtfile`:
      Save data to file in csv-format

  - `class run_mimoDAQ`:
      Setup and run data acquisition with mimiCoRB buffer manager   
      
These classes shield much of the complexity from the user, who can
thus concentrate on writing the pieces of code need to acquire and
prcess the data. 

*run_mimoDAQ* contains most of the code needed to run a real example
of a data-acquisition suite defined in a configuraion file with associated,
user-defined functions for data provisioning, filtering and storage.
It also provides an example on how to user the methods provided by the
class *buffer_control*. 


Application example
...................

The subdirectory examples/ contains a rather comlete application use case.
Code snippets and configuration data are provided in the subdirectories
examples/modules/ and examples/config/, respectively.
Waveform data, as provided by, for example, a multi-channel digital
oscilloscope, are generated and filled into the first of a cascaded set
of three ringbuffers. The raw data are analyzed, and accepted data with a
double-pulse signature are selected and directly passed on to a second
ringbuffer. A third buffer contains only the information about found
signal pulses; a result file in *csv* format contains the data extracted
from this buffer. 

The buffer layout and the associated functions are defined in the main
configuration file `simulsource_setup.py`, which serves as the input to the
execution script `run_daq.py` in the top-level directory of the package. 
The *python* files `simulation_source.py`, `liftime_filter.py` and
`save_files.py` contain the user code for data generation, analysis
and filtering and extraction of the final data to disk files. The
`.yaml` file `simulation_config.yaml` contains configurable parameters
provided to these functions.

An observer process receives a sub-set of the data in the second
buffer and shows them as an oscilloscope display on screen while
data are generated and propagated through the buffers.

This example is executed form the directory examples/ by entering:

  `../run_daq.py simulsource_setup.yaml`

The code needed to run data-acquistion based on the package
*mimocorb.buffer_control.run_mimoDAQ* is shown here: 

.. code-block:: python

  # script run_daq.py

  from mimocorb.buffer_control import run_mimoDAQ
  daq = run_mimoDAQ()
  daq.setup()
  daq.run()

The input *yaml* file for the example provided as part of the package looks
as follows: 

.. code-block:: yaml
		
  #  Application example for mimoCoRB
  #  --------------------------------

  RingBuffer:
    # define ring buffers
    - RB_1:
      # raw input data buffer (waveforms from PicoScope, filele_source or simulation_source)
      number_of_slots: 128
      channel_per_slot: 4250
      data_type:
          1: ['chA', "float64"]
          2: ['chB', "float64"]
          3: ['chC', "float64"]
          4: ['chD', "float64"]          
    - RB_2:
        # buffer with accepted signatures (here double-pulses)
        number_of_slots: 128
        channel_per_slot: 4250
        data_type:
          1: ['chA', "float64"]
          2: ['chB', "float64"]
          3: ['chC', "float64"]
          4: ['chD', "float64"]          
    - RB_3:
        # buffer with pulse parameters (derived from waveforms)
        number_of_slots: 32
        channel_per_slot: 1
        data_type:
          1: ['decay_time', "int32"]
          3: ['1st_chA_h', "float64"]
          4: ['1st_chB_h', "float64"]
          5: ['1st_chC_h', "float64"]          
          6: ['1st_chA_p', "int32"]
          7: ['1st_chB_p', "int32"]
          8: ['1st_chC_p', "int32"]
          9: ['1st_chA_int', "float64"]
          10: ['1st_chB_int', "float64"]
          11: ['1st_chC_int', "float64"]
          12: ['2nd_chA_h', "float64"]
          13: ['2nd_chB_h', "float64"]
          14: ['2nd_chC_h', "float64"]
          15: ['2nd_chA_p', "int32"]
          16: ['2nd_chB_p', "int32"]
          17: ['2nd_chC_p', "int32"]
          18: ['2nd_chA_int', "float64"]
          19: ['2nd_chB_int', "float64"]
          20: ['2nd_chC_int', "float64"]
          21: ['1st_chD_h', "float64"]
          22: ['1st_chD_p', "int32"]
          23: ['1st_chD_int', "float64"]
          24: ['2nd_chD_h', "float64"]
          25: ['2nd_chD_p', "int32"]
          26: ['2nd_chD_int', "float64"]

  Functions:
    # define functions and assignments
    - Fkt_main:
       config_file: "config/simulation_config.yaml"
    - Fkt_1:
       file_name: "modules/simulation_source"
       kt_name: "simulation_source"
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
       file_name: "modules/save_files"
       fkt_name: "save_to_txt"
       num_process: 1
       RB_assign:
         RB_3: "read"     # pulse data
    - Fkt_4:
       file_name: "modules/save_files"
       fkt_name: "save_parquet"
       num_process: 1
       RB_assign:
         RB_2: "read"     # waveform to save
    - Fkt_5:
       file_name: "mimocorb/plot"
       fkt_name: "plot_graph"
       num_process: 1
       RB_assign:
         RB_2: "observe"  # double pulse waveform


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

=====================
Module Documentation 
=====================

..  automodule:: mimocorb
     :imported-members:
     :members:

..  automodule:: mimocorb.mimo_buffer
     :members:

..  automodule:: mimocorb.buffer_control
     :members:

..  automodule:: mimocorb.plot_buffer
     :members:
	
..  automodule:: rb_unittest

..  automodule:: simulation_source
     :members:

..  automodule:: lifetime_filter
     :members:

..  automodule:: plot_waveform
     :members:

..  automodule:: read_from_buffer
     :members:	


