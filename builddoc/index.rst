===========================================================
mimoCoRB - multiple-in multile-out Configurable Ring Buffer
===========================================================


mimoCoRB -  multiple-in multile-out Configurable Ring Buffer: Overview
----------------------------------------------------------------------

**mimoCoRB**: multiple-in multiple-out Configurable Ring Buffer

The package **mimoCoRB** provides a central component of each data acquisition
system needed to record and pre-analyze data from randomly occurring processes.
Typical examples are waveform data as provided by detectors common in quantum
mechanical measurements, or in nuclear, particle physics and astro particle
physics, e. g. photo tubes, Geiger counters, avalanche photo-diodes or modern
SiPMs.

The random nature of such processes and the need to keep read-out dead
times low requires an input buffer for fast collection of data
and an efficient buffer manager delivering a constant data stream to
the subseqent processing steps. While a data source feeds data into the
buffer, consumer processes recieve the data to filter, reduce, analyze
or simply visualize data. In order to optimally use the available
resources, multi-core and multi-processing techniques must be applied.
Data consumers may be obligatory ones, i. e. data acquisition pauses if
all input buffers are full and an obligatory consumer is still busy
processing. A second type of random consumers ("observers") receives
an event copy from the buffer manager upon request, without pausing the
data acquisition process. Typical examples of random consumers are
displays of a subset of the wave forms or of intermediate analysis
results.

This project originated from an effort to structure and generalize
data acquistion for several experiments in advanced physics laboratory
courses at Karlsruhe Institute of Technology (KIT).

As a simple demonstration, we provide data from simulated signals as would
be recorded by a detector for cosmic muons with three detection layers.
Occasionally, such muons stop in an absorber between the 2nd and 3rd layer,
where they decay at rest and emit a high-energetic electron recorded as a
2nd pulse in one or two of the detection layers. After data acquisition, a
search for typical puls shapes is performed and data with detected double
pulses are selected and copied into a second buffer. A third buffer receives
data in a reduced format which only contains the parameters of accepted pulses.
These data and the wave forms of all double-pulses are finally stored
on disk. Such an application is a very typical example of the general
process of on-line data processing in modern physics experiments and may
serve as a starting point for own projects.


.. toctree::
   :maxdepth: 2
   :caption: Contents:



Description of components
..................................


In order to decouple the random occurrence of "events" one needs a
buffer capable of rapidly storing new incoming data and delivering
a constant data stream to subsequent consumer processes. 
This is typically implemented as a first-in, first out ringbuffer 
providing storage space in memory for incoming data, which is 
released and overwritten by new data when all consuming processes 
have finished.

As digital filtering of incoming data may be very CPU intensive,
multi-processing and multi-core capable components are needed to
ensure sufficient processing power to process and analyze data.
`mimoCoRB.mimo_buffer` implements such a buffer allowing multiple 
processes to read ("multiple out") or write ("multiple in") to the 
buffer space. 

Because processing of the data, i.e. digital filtering, selection, 
compression and storage or real-time visualization of the data may 
be a complex workflow, buffers may be arranged in chains where one 
or several reader processes of a buffer write to one or several 
output buffer(s). 

The central component takes care of memory management and access
control provided by the class **newBuffer**. To control the data
flow in a full data acquisition suite, three types of access are
needed, implemented as  **Writer**, **Reader** and **Observer**
classes. Readers of the same type are grouped together for
multi-processing of compute-intense tasks and form a Reader-group. 
Observers receive only a sub-set of the data and are mainly 
intended to be used for visual inspection or graphical representation
of samples of the recorded or processed data. 

Processes for data provisioning from front-end hardware or 
from other sources, like disk files, web streams or simulation,
rely on these basic classes. Any Writer-process blocks if no
free buffer slot is available. Reader processes block if no
slot is left that has not yet been processed by any process
belonging to the same Reader-group. Note that the buffer
manager ensures that every slot assigned to a Reader (or a group 
of Readers) is actually processed; therefore, input to a buffer
blocks if the buffer is filled up completely; data input resumes
as soon as a Reader or member of a Reader-group has finished
processing and thus freed a slot in the buffer.

Multiprocessing is enabled by use of the *shared_memory* module
of the *multiprocessing* package available since Python 3.8 for
direct access to shared memory across processes. Other modules
of the package (*Process*, *Lock*, *Event*, and *SimpleQueue*
or *Queue*) are used to create and control sub-processes and for
message or data exchange and signalling across processes. 

The format of data stored in the buffers is based on structured
*numpy* arrays with (configurable) field names and *numpy* *dtypes*.  
Each buffer entry is also associated with a unique number and a time 
stamp in microseconds (*time.time_ns()//1000*) of type *longlong* 
(64 bit integer) and a deadtime fraction to be provided by the initial
data producer. The deadtime accounts for inefficiencies of the
data acquisition due to processing in *mimoCoRB*. These metadata are 
set by the initial producer and must not be changed at a later stage 
in the processing chain. 


Simple application example 
...........................


An application example of *mimo_buffer* is shown below;
it is also provided as a unit test.
The set-up is as follows:

  2 ring buffers are defined:

    - input Buffer  RB_1: 10 ch x 1024 slots (int32)

    - output Buffer RB_2: 10 ch x 2 slots/ch (float64)

    Simple data is filled into RB_1, copied and extended by a process
    writing data into RB_2, and finally a reader process to check
    integrity and completeness of the data. The most complex part of
    the code is in function *run_control()*, which demonstrates
    how to set up the buffers, define Reader and Writer instances
    and start the parallel processes for generating, processing
    and reading the data. 

The example including comment lines for explanation is shown here:

.. code-block:: python

  import time
  import unittest
  import numpy as np
  from multiprocessing import Process, Value
  from mimocorb import mimo_buffer as bm

  # global variables 
  N_requested = 1000  # number of data injections ("events")
  Time_tick = 0.001   # time between events
  Ncpu1 = 2           # number of parallel analyzer processes

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
    """reads RB_2 and sum up the integer content

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
               # expected result: sum(i); i = 1, N_requested	
        self.assertEqual(a, expected_result)

  if __name__ == "__main__":
    unittest.main(verbosity=2)
  #    print(process_buffer())


Access Classes in the module *buffer_control*
---------------------------------------------

To ease user interaction with the buffer manager, a set of additional classes 
is provided in the module *buffer_control* to set-up and manage cascades of 
ringbuffers and the associated functions for filling, filtering and extracting
data. These classes are also interesting for developers wanting to help improving
the package. 

The classes are: 

  - `class buffer_control`
      Set-up and management of ringbuffers and associated sub-processes.
      This is the overarching class with access to all created buffers and sub-processes.

  - `class rbImport`
      Read data from source (front-end like a PicoScope USB oscilloscope, of from file or simulation) 
      and put data in a mimo_buffer. Data is input is handled by a call of a user-supplied
      generator function for data and metadata.

  - `class rbTransfer`
      Read data from a mimo_buffer, filter and/or reformat data and write to output mimo_buffer(s).
      Data is provided as the argument to a user-defined filter function returning *None* if data 
      is to be discarded, a number if data is to be copied to another buffer, or - otionally - a 
      list of data records produced from processed input data. If such data are provided, a 
      respective number of ringbuffers as destination must be configured.
      
  - `class rbExport`
      Read data from mimo_buffer and analyze (with user-supplied code),
      without writing to another ringbuffer. Data is provided by a generator
      function in the __call__() method of the class yielding a tuple of
      data and metadata. 
      
  - `class rbObserver`
      Deliver data from a buffer to an observer process. A tuple (data, metadata) 
      is provided by a generator function ( i.e. via yield()) implemented in the
      __call__() method of the class. 
      
  - `class rb_toTxtfile`:
      Save mimo_buffer data to a file in csv-format. The header line of this file contains
      the keys of the respective columns, which are derived from the datatype of the structured
      ringbuffer array. Aliases for improved clarity can be provided in the configuration file. 
      
  - `class rb_toParquetfile`:
      Save mimo_buffer data to an archive in  *tar* foramt; each data record is packed in
      Parquet format.

  - `class run_mimoDAQ`
      Setup and run Data Acquisition suite with mimoCoRB buffer manager.   
      The layout of ringbuffers and associated functions are defined in
      a configuration file in *yaml* format. All configured functions are 
      executed as worker processes in separate sub-processes and therefore 
      optimal use is made of of multi-core architectures. 

  -  class `bufferinfoGUI`:
      A graphical interface showing buffer rates and status information 
      and providing some control buttons interacting with the runDAQ
      class 
    
These classes shield much of the complexity from the user, who can
thus concentrate on writing the pieces of code need to acquire and
process the data. 
The access classes expect as input lists of dictionaries with the parameters
of buffers to read from (**source_list**), to write to (**sink_list**) or to
observe (**observe_list**). An additional dictionary (**config_dict**) provides
the additional parameters needed for the specific functionality, for example names of
functions to read, filter or manipulate data or the names of target files.
The interface for passing data between the user-defined functions and ringbuffers
relies on Python generators (i.e. the *yield* instruction).

The overarching class **buffer_control** provides methods to setup buffers and 
worker processes and to control the data acquisition process. The methods 
collected in the class *run_mimoDAQ*, in particular the function **run_mimoDAQ**,
contains the code needed to run a real example of a data-acquisition suite defined
in a configuration file specifying the associated, user-defined functions for 
data provisioning, filtering and storage. *run_mimoDAQ* is controlled either
by keyboard commands of from a graphical user interface; pre-defined conditions
on the total number of events processed, the duration of the data taking run
or finishing of the writer process to the first buffer due to source exhaustion
can also be defined to end data taking. The class structure and dependencies
are shown in the figure below.

.. image:: class_structure.png
  :width: 1024
  :alt: The structure of a mimoCoRB project

For complex setups and longer data-taking periods it is important to gain 
a quick overview of the status of all buffers and to monitor long-term stability. 
Therefore, a graphical display with the processing rate of all buffers is
provided by the class **bufferinfoGUI**. A text window receives frequent 
updates of the number of events processed by each buffer and of the buffer 
fill-levels. Klickable control buttons send information via a dedicated
command queue to the calling process *run_mimoDAQ* and enable pausing,
resuming and controlled ending of the data-acquisition processes.

The suggested structure of the project work-space for mimiCoRB applications 
is as follows:

.. code-block::

  |--> <user working directory>       # the main configuration script resides here
                    |
                    | --> modules     # project-specific, user-supplied python code
                    | --> config      # configuration files in yaml format
                    | --> target      # output of data-acquisition run(s)

For illustration and as a starting point for own applications, a stand-alone example 
is provided as part of the package, as described in the following section. 
                    

Application example
...................

The subdirectory *examples/* contains a rather complete application use case.
It runs stand-alone and uses as input simulated waveform data of short pulses
in a scintillator detector. The simulated physics process corresponds to 
signatures produced by cosmic muons. Of particular interest in this case are 
(rare) signatures with a double-pulse structure, where the first pulse originates
from a detected muon and the second one from a decay electron of a muon that
is stopped in or near a detection layer. 

Examples of code snippets and configuration data are provided in the 
subdirectories `examples/modules/` and `examples/config/`, respectively.
Waveform data, as provided by, for example, a multi-channel digital
oscilloscope, are generated and filled into the first one of a cascaded set
of three ringbuffers. The raw data are analyzed, and accepted data with a
double-pulse signature are selected and directly passed on to a second
ringbuffer. A third buffer contains only the information on found
signal pulses; a result file in *csv* format contains the data extracted
from this buffer. Configuration files and the recorded data files are stored
in the subdirectory `examples/target/<projectname>_<date_and_time>`. 

A graphical representation of the set-up is shown in the figure 
below [source: Master's Thesis Christoph Mayer, ETP 2022].
Note that the oscilloscope is replaced by a signal simulation in the 
provided example. 

.. image:: mimoCoRB_lifetime.png
  :width: 650
  :alt: The signal processing chain for the lifetime measurement	  

The buffer layout and the associated functions are defined in the main
configuration file `simulsource_setup.py`, which serves as the input to 
the execution script `run_daq.py` in the top-level directory of the package. 
The *python* files `simulation_source.py`, `liftime_filter.py` and
`save_files.py` contain the user code for data generation, analysis
and filtering and extraction of the final data to disk files. The
`.yaml` files `simulation_config.yaml` and `save_lifetimes.yaml` contain 
configurable parameters provided to these functions.

This example is executed form the directory `examples/` by entering:

  `../run_daq.py simulsource_setup.yaml`

The code needed to run a data acquisition based on the package
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
         fkt_name: "simulation_source"
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
        config_file: "config/save_lifetime.yaml"
        num_process: 1
        RB_assign:
             RB_3: "read"     # pulse data
    - Fkt_4:
        file_name: "modules/save_files"
        fkt_name: "save_parquet"
        num_process: 1
        RB_assign:
             RB_2: "read"     # waveform to save

The configuration file referenced in the line 
`config_file: "config/simulation_config.yaml"` provides the
information needed by the user-supplied functions.

The example coming with this package contains two more convenience
functions, one for an observer process displaying a random sample of
waveforms in an oscilloscope display, and a second one for on-line
analysis and histogramming of buffer data. The addendum to the
configuration looks as follows: 

.. code-block:: yaml
		
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

These additional functions rely on the modules `mimocorb.plot_buffer` and
`mimocorb.histogram_buffer`, which provide animated displays of waveforms
similar to an oscilloscope and a histogram package for life-updates of
frequency distributions of scalar variables. A screenshot of a data-acquistion
run with input from simulated datat is shown in the figure below.


.. image:: mimoCoRB_screenshot.png
  :width: 1024
  :alt: Screenshot of a simulation run


====================
Module Documentation 
====================

.. automodule:: mimocorb
     :imported-members:
     :members:

.. automodule:: mimocorb.mimo_buffer
     :members:

.. automodule:: mimocorb.buffer_control
     :members:

.. automodule:: mimocorb.bufferinfoGUI
      :members:

.. automodule:: mimocorb.plot_buffer
     :members:

.. automodule:: mimocorb.histogram_buffer
     :members:
       
.. automodule:: rb_unittest

.. automodule:: simulation_source
     :members:

.. automodule:: lifetime_filter
     :members:

.. automodule:: plot_waveform
     :members:

.. automodule:: read_from_buffer
     :members:	
