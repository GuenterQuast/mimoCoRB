"""
Unittest: test ring buffer module (here: modules/mimo_ringbuffer.py) as part of a project:
This module can be copied into a new project and used as unittest if
the module 'mimo_ringbuffer.py' is located in the directory 'modules'.
In case names are changing adapt them here.

Logic: 2 ring buffers are defined:
    RP1: 10 ch x 1024 slots (int32)
    RP2: 10 ch x 2 slots/ch (float64)
"""
import time
import unittest
import numpy as np
from multiprocessing import Process, Value
from mimocorb import mimo_buffer as bm


def data_generator(sink_dict):
    # fills RP1 with integers continuously (into all slots)
    sink = bm.Writer(sink_dict)
    n = 0
    for x in range(1, 36):
        buffer = sink.get_new_buffer()
        buffer[:] = n + 1
        time.sleep(0.1)
        n = n + 1
    sink.process_buffer()


def test_analyzer(source_dict, sink_dict):
    # read RP1 content and fill RP2 with the first element of RP1 and a time difference
    source = bm.Reader(source_dict)
    sink = bm.Writer(sink_dict)
    start_time = time.time()
    for x in range(1, 36):
        input_data = source.get()
        output_data = sink.get_new_buffer()
        for ind in range(2):
            if ind == 0:
                output_data[ind] = input_data[0]
            elif ind == 1:
                output_data[ind] = time.time() - start_time
    sink.process_buffer()


def check_test(source_dict, res):
    # reads RP2 and sum up the integer content (value should be sum(1 -35) = 630);
    # sum is returned as Value-object
    source = bm.Reader(source_dict)
    sum_rp = 0
    for x in range(1, 36):
        input_data = source.get()
        sum_rp = sum_rp + int(input_data[0])
    res.value = sum_rp


def process_buffer():
    runtime = 4  # Time in seconds how long the program should run

    # test: num of cpu's
    ncpu1 = 1  # os.cpu_count()
    # Create ring buffers: #2: 10 channel, 2 value per channel (1: buffer content; 2: time difference as int)
    #  d_type = [('chA', np.float)] #not necessary: always the same type
    generator_buffer = bm.NewBuffer(10, 1024, np.int32)
    eval_buffer = bm.NewBuffer(10, 2, np.float32)
    # create readers first
    source_dic_gen = generator_buffer.new_reader_group()
    source_dic_eval = eval_buffer.new_reader_group()

    # Create worker processes (correct sequence: first action at last)
    process_list = []
    # fill buffer (generator_buffer) with data first

    # some fake evaluation to test ring buffer behavior
    result = Value('i', 0)
    process_list.append(Process(target=check_test,
                                args=(source_dic_eval, result)))
    # data transfer between the 2 buffers: generator_buffer -> eval_buffer
    sink_dic_eval = eval_buffer.new_writer()
    # work with all cpu's present
    number_of_workers = ncpu1
    for i in range(number_of_workers):
        process_list.append(Process(target=test_analyzer,
                                    args=(source_dic_gen, sink_dic_eval)))
    # fill buffer (generator_buffer) with data first
    sink_dic_gen = generator_buffer.new_writer()
    process_list.append(Process(target=data_generator,
                                args=(sink_dic_gen,)))

    for p in process_list:
        p.start()

    time.sleep(runtime)  # wait n seconds

    generator_buffer.shutdown()
    eval_buffer.shutdown()
    del generator_buffer, eval_buffer

    for p in process_list:
        p.join()

    return result.value


class RPTest(unittest.TestCase):

    def test_process(self):
        # start python test module and check result
        a = process_buffer()
        self.assertEqual(a, 630)  # expected result: sum(i); i = 1, 35 -> 630


if __name__ == "__main__":
    unittest.main(verbosity=2)
