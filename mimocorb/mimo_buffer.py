"""**mimo-ringbuffer**:

Module implementing a multiple-in multiple-out ringbuffer appropriate for multi-core multiprocessing.

The ringbuffer creation and management is handled by the class ``NewBuffer``.
Buffer access is managed by the``Reader``, ``Writer`` and ``Observer``  classes.

classes:

  - NewBuffer: create a new ringbuffer, assign writer(s) and reader(s) or observer(s)

      methods:

       - new_writer
       - new_reader_group
       - new_observer
       - buffer_staus

  - Writer:   write elements into a ringbuffer
  - Reader:   read all elements from a ringbuffer
  - Observer: read selected elements from a ringbuffer.
"""

import os
import time
import numpy as np
from multiprocessing import shared_memory, Lock, SimpleQueue, Queue, Event
import threading
import heapq


class NewBuffer:
    """Class to create a new ringbuffer object according to the 'FIFO' principle (first-in first-out).

    Memory shares, IPC queues, lock and event objects as well as background threads are defined
    for the multiprocessing ringbuffer management. Methods are provided to build the setup dictionaries
    (necessary parameter objects) for the ``Reader``, ``Writer`` or ``Observer`` instances, respectively.
    Further, methods are provided to allow an index processing (e.g. listeners) and to pause data processing.

    Index processing overview: to achieve a proper handling for writing and reading data into a
    ringbuffer slot regarding the possible definition of more than one reader for a ringbuffer
    (multiprocessing mode on function level) the determination of the correct slot index is essential.
    For a ``Writer`` or ``Reader`` two SimpleQueues are defined, respectively. In principle one queue
    contains the index to be used next and the other the index just processed. An ``Observer`` is
    treated in a simpler way by using an own global index variable for each instance.

    The queues are passed via the setup dictionary to the corresponding Reader or Writer instance,
    respectively, and processed there. In addition, the buffer manager provides methods to control
    the index determination (_writer/_reader/_observer_queue_listener()), started in own threads.

    Writer index:

    - writer_empty_queue: contains the slot numbers (initially filled); defines the next free ringbuffer slot.

      - fetched (removed) in the class Writer -> get_new_buffer()
      - last processed slot number is refilled in _increment_reader_pointer()

    - writer_filled_queue: empty; contains the last processed slot number (distributed to all defined readers).

      - process_buffer()

    Reader index:

    - manually incremented in _increment_reader_pointer() via global variable read_pointer
    - done_queue: empty; already processed slot number

     - fetched in _reader_queue_listener()
     - filled in the class Reader -> get() via the global variable _last_get_index

    - todo_queue: empty; slot number to be processed next

     - fetched in the class Reader -> get()
     - filled in _writer_queue-listener (within the list reader_todo_queue_list)

    Observer index:

    - the global variable obs_pointer is used; it is an early copy of the write_pointer variable

      - defined in _writer_queue_listener()
      - directly used as index in _observeQ_listener()

    important methods:

     - __init__() constructor to create a new 'FIFO' ringbuffer
     - new_writer() create new writer
     - new_reader_group() create reader group
     - new_observer() create observer
     - buffer_status() display status: event count, processing rate, occupied slots
     - pause() disable writer(s) to ringbuffer
     - resume() (re-)enable writers
     - set_ending() stop data-taking (gives processes time to finish before shutdown)
     - close() release shared memory
     - shutdown() end connected processes, delete ringbuffer
    """

    def __init__(self, number_of_slots, values_per_slot, dtype, debug=False):
        """Constructor to create a new 'FIFO' ringbuffer.

        :param number_of_slots: The number of elements the ringbuffer can hold
        :type number_of_slots: int
        :param values_per_slot: The length of the structured NumPy array of each ringbuffer element.
        :type values_per_slot: int
        :param dtype: The data-type of a ringbuffer element. Typically, ringbuffer elements are structured
            NumPy arrays, so the syntax is a list of tuples of the form:
            ``[ (column_name, np.dtype), (coulmn_name, np.dtype), ... ]``
            See the NumPy "structured arrays" documentation for
            `more detail <https://numpy.org/doc/stable/user/basics.rec.html#structured-datatype-creation>`_
        :type dtype: np.dtype
        :param debug: Print debug symbols during execution (This should only be used during
            development), defaults to False
        :type debug: bool, optional
        """
        # TODO: Change naive print to logger
        # print(" > Creating MimoRingBuffer")
        self._debug = debug
        # Create the memory share for data and metadata
        self.number_of_slots = number_of_slots
        self.values_per_slot = values_per_slot
        self.dtype = dtype
        m_bytes = number_of_slots * values_per_slot * np.dtype(dtype).itemsize
        self.m_share = shared_memory.SharedMemory(create=True, size=m_bytes)
        self.metadata_dtype = [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
        m_bytes = number_of_slots * np.dtype(self.metadata_dtype).itemsize
        self.m_metadata_share = shared_memory.SharedMemory(create=True, size=m_bytes)

        # !!! access to (meta)data in shared-memory
        self._buffer = np.ndarray(
            shape=(self.number_of_slots, self.values_per_slot),
            dtype=self.dtype,
            buffer=self.m_share.buf,
        )
        self._metadata = np.ndarray(
            shape=self.number_of_slots,
            dtype=self.metadata_dtype,
            buffer=self.m_metadata_share.buf,
        )

        # Setup queues
        # > Queue with all EMPTY memory slots ready to be used by a writer (implicitly kept in order)
        self.writer_empty_queue = SimpleQueue()
        for i in range(self.number_of_slots):
            self.writer_empty_queue.put(i)
        # > Queue with all freshly FILLED memory slots. Will be redistributed to each reader group queue
        self.writer_filled_queue = SimpleQueue()
        # > List containing the 'to do'-queues of all reader groups. Each queue contains elements ready to be processed
        self.reader_todo_queue_list = []
        # > List containing the 'done'-queues of all reader groups. Each queue contains elements ready to be overwritten
        self.reader_done_queue_list = []
        # > List containing the 'done'-heaps of all reader groups.
        self.reader_done_heap_list = []

        # Setup threading locks
        self.read_pointer_lock = Lock()  # Lock to synchronise self.read_pointer manipulations
        self.write_pointer_lock = Lock()  # Lock to synchronise self.write_pointer access
        self.heap_lock = Lock()  # Lock to synchronise manipulations on the reader group 'done'-heaps

        # Setup pointers
        self.read_pointer = 0  # Pointer referencing the oldest element that is currently worked on by any reader
        self.write_pointer = 0  # Pointer referencing the newest element added to the buffer (might be wrong at startup)
        self.obs_pointer = 0  # early copy of the write_pointer to handle the observer index

        # Setup events for a graceful shutdown
        self.writers_active = Event()
        self.writers_active.set()
        self.observers_active = Event()
        self.observers_active.set()
        self.readers_active = Event()
        self.readers_active.set()
        self.writers_paused = Event()
        self.writers_paused.clear()

        # Setup filled buffer dispatcher (in background thread)
        self._writer_queue_thread = threading.Thread(target=self._writer_queue_listener, name="Main writer queue listener")
        self._writer_queue_thread.start()
        self.writer_created = False
        self.reader_queue_listener_thread_list = []

        # variables for buffer statitiscs (evaluated in buffer_status() )
        self.Tstart = time.time()
        self._init_buffer_status()

    def new_reader_group(self):
        """Method to create a new reader group.
        The processing workload of a group can be distributed to multiple processes by using
        the same setup dictionary (``setup_dict``) defined for a ``Reader``-object.
        Each ringbuffer element is processed by one reader group process. It's possible to create multiple
        reader groups per ringbuffer, where each reader group gets every element written to the ringbuffer.
        If a reader group is created, at least one ``Reader``-class instance MUST steadily call its ``get()``
        method to prevent the ringbuffer from blocking and to allow a safe shutdown.

        :return: The ``setup_dict`` object passed to a ``Reader``-instance to grant read access to this ringbuffer.
        :rtype: dict
        """
        # Temporary fix to prevent 'new reader after write' problem
        assert self.read_pointer == 0, "All readers must be created before the first element is written to the buffer!"
        # Create basic data structure
        done_queue = SimpleQueue()  # Queue containing elements a worker process is done processing with
        todo_queue = SimpleQueue()  # Queue containing elements ready to be processed next
        self.reader_todo_queue_list.append(todo_queue)
        self.reader_done_queue_list.append(done_queue)
        # > Heap the 'done'-queue gets flushed into. Used to keep 'self.writer_empty_queue' in order
        done_heap = []
        self.reader_done_heap_list.append(done_heap)
        # Start background thread to listen on the done-queue (in lack of an event driven queue implementation)
        queue_listener = threading.Thread(
            target=self._reader_queue_listener,
            args=(done_queue, done_heap),
            name="Main reader queue listener",
        )
        queue_listener.start()
        self.reader_queue_listener_thread_list.append(queue_listener)
        setup_dict = {
            "number_of_slots": self.number_of_slots,
            "values_per_slot": self.values_per_slot,
            "dtype": self.dtype,
            "mshare_name": self.m_share.name,
            "metadata_share_name": self.m_metadata_share.name,
            "todo_queue": todo_queue,
            "done_queue": done_queue,
            "active": self.readers_active,
            "paused": self.writers_paused,
            "debug": self._debug,
        }
        return setup_dict

    def _reader_queue_listener(self, done_queue, done_heap):
        """
        Internal method run in a background thread (one for each reader group). It handles dispatching free
        ringbuffer elements.

        :param done_queue: the multiprocessing.queue created in ``new_reader_group()``
        :param done_heap: the heap created in ``new_reader_group()``
        """
        while self.readers_active.is_set():
            last_index = done_queue.get()
            if last_index is None:
                continue
            with self.heap_lock:
                with self.read_pointer_lock:
                    if last_index < self.read_pointer:
                        last_index += self.number_of_slots
                heapq.heappush(done_heap, last_index)
                self._increment_reader_pointer()
        if self._debug:
            print(" > DEBUG: Reader dispatcher closed in main thread!")

    def _increment_reader_pointer(self):
        """
        Internal method called by a ``_reader_queue_listener()``-thread after a new element was marked
        as 'processing is done'. It is checked whether all reader groups have completed processing the oldest
        ringbuffer element, and if so, adds it to the 'free ringbuffer elements' queue used by the ``Writer``-instances.
        For this function to work properly and without race conditions self.heap_lock has to be acquired
        BEFORE entering the function (see ``_reader_queue_listener()``-method).
        """
        # Check if every reader group is done with the last element (this implicitly keeps the write queue in the right
        # order at the cost of possible buffer overruns if one reader hangs/takes too long to process the data)
        pop_last_element = True
        with self.read_pointer_lock:
            # Check the oldest element of each heap
            for reader_heap in self.reader_done_heap_list:
                try:
                    if reader_heap[0] != self.read_pointer:
                        pop_last_element = False
                        break
                except IndexError:
                    # This error is thrown if the heap is empty! In that case we can't increment the reader pointer!
                    pop_last_element = False
                    break
            if pop_last_element:
                # All reader groups are done processing the oldest buffer element...
                if self._debug:
                    with self.write_pointer_lock:
                        print("?> pop last element: {:d} (writer right now: {:d})".format(self.read_pointer, self.write_pointer))
                    for reader_heap in self.reader_done_heap_list:
                        print(reader_heap)
                # ... so remove it from each heap ...
                for reader_heap in self.reader_done_heap_list:
                    heapq.heappop(reader_heap)
                # ... and add it to the queue of empty buffer slots
                self.writer_empty_queue.put(self.read_pointer)
                self.read_pointer += 1
                # Handle "lapping" the ring buffer
                if self.read_pointer >= self.number_of_slots:
                    if self._debug:
                        print("?> BUFFER IS LAPPING. {:d} -> {:d}".format(self.read_pointer, self.write_pointer))
                    self.read_pointer -= self.number_of_slots
                    for reader_heap in self.reader_done_heap_list:
                        for i in range(len(reader_heap)):
                            if reader_heap[i] >= self.number_of_slots:
                                reader_heap[i] -= self.number_of_slots
                        heapq.heapify(reader_heap)
                    with self.write_pointer_lock:
                        if self.write_pointer > self.number_of_slots:
                            self.write_pointer = self.write_pointer % self.number_of_slots
                        else:
                            self.write_pointer = 0
                        if self._debug:
                            print("?>        MOD WRITER: {:d} -> {:d}".format(self.read_pointer, self.write_pointer))
        # If the write pointer was incremented, check if it's possible to further increment it (enabeling the writer
        # pointer to 'catch up' if an element was stuck for a long time)
        if pop_last_element:
            self._increment_reader_pointer()

    def _writer_queue_listener(self):
        """Internal method run in a background thread.
        It takes the index (a 'pointer' in the array) of the 'ready to process' ringbuffer element from
        the ``writer_filled_queue`` and distributes it to every reader group (reader_todo_queue).
        """
        while self.writers_active.is_set():
            new_data_index = self.writer_filled_queue.get()
            if new_data_index is not None:
                self.cumulative_event_count += 1  # increment event count
                with self.write_pointer_lock:
                    if new_data_index < self.read_pointer:
                        self.write_pointer = max(new_data_index + self.number_of_slots, self.write_pointer)
                    else:
                        self.write_pointer = max(new_data_index, self.write_pointer)
                # define observer index
                self.obs_pointer = self.write_pointer if self.write_pointer < self.number_of_slots else self.write_pointer % self.number_of_slots
                # spy on metadata
                self.sum_deadtimes += self._metadata[new_data_index]["deadtime"]
                # counter = self._metadata[new_data_index]['counter']
                # timestamp = self._metadata[new_data_index]['timestamp']
                # deadtime = self._metadata[new_data_index]['deadtime']

            for reader_queue in self.reader_todo_queue_list:
                reader_queue.put(new_data_index)

    def new_writer(self):
        """Method to create a new writer.
        It is possible to create multiple writers and simply share a setup dictionary definition
        between different ``Writer``-instances (analogues to the behavior of the ``new_reader_group``).

        :return: The ``setup_dict`` object passed to a ``Writer``-instance to grant write access to this ringbuffer.
        :rtype: dict
        """
        self.writer_created = True
        setup_dict = {
            "number_of_slots": self.number_of_slots,
            "values_per_slot": self.values_per_slot,
            "dtype": self.dtype,
            "mshare_name": self.m_share.name,
            "metadata_share_name": self.m_metadata_share.name,
            "empty_queue": self.writer_empty_queue,
            "filled_queue": self.writer_filled_queue,
            "active": self.writers_active,
            "paused": self.writers_paused,
            "debug": self._debug,
        }
        return setup_dict

    def _observerQ_listener(self):
        """Put latest data and metadata in Queue for observer if empty

        maximum event rate is limited to 20Hz
        """

        # pre-allocate memory for local copy of data
        data = np.empty(shape=(self.values_per_slot,), dtype=self.dtype)
        mdata = np.empty(shape=(1,), dtype=self.metadata_dtype)

        last_ev = 0
        # wait for first data
        while self.cumulative_event_count == 0:
            time.sleep(0.05)
        # put data in oberver Queue if empty
        while self.observers_active.is_set():
            if self.observerQ.empty() and self.cumulative_event_count != last_ev:
                with self.write_pointer_lock:
                    # local copy of the data using a write_pointer copy (observe pointer)
                    mdata[:] = self._metadata[self.obs_pointer].copy()
                    data[:] = self._buffer[self.obs_pointer].copy()
                self.observerQ.put((data, mdata))
                last_ev = self.cumulative_event_count
            time.sleep(0.05)  # limit rate to 20Hz
        # reached end:
        #   send None to signal end-of-run to client, give some grace time before timing-out
        self.observerQ.put(None, block=True, timeout=3.0)

    def new_observer(self):
        """Method to create a new (Queue based) observer.

        Method: a copy of the most recent data (latest write_pointer) is transferred via a
        Queue whenever the Queue (of size 1) is empty. Sending data through the Queue is handled
        in a sparate thread

        :return: The ``setup_dict`` object passed to an ``Observer``-instance to give access to
           the data Queue defined for this ringbuffer.
        :rtype: dict
        """

        # create a Queue with size of one (Queue.empty() can be used to synchronize with client)
        self.observerQ = Queue(1)

        setup_dict = {
            "number_of_slots": self.number_of_slots,
            "values_per_slot": self.values_per_slot,
            "dtype": self.dtype,
            "mshare_name": self.m_share.name,
            "metadata_share_name": self.m_metadata_share.name,
            "dataQ": self.observerQ,
            "active": self.observers_active,
            "paused": self.writers_paused,
            "debug": self._debug,
        }

        self.observerQ_listener_thread = threading.Thread(target=self._observerQ_listener, name="observer_queue_listener")
        self.observerQ_listener_thread.start()

        return setup_dict

    def _init_buffer_status(self):
        self.Tlast = self.Tstart
        self.Nlast = 0
        self.cumulative_event_count = 0  # cumulative number of events
        self.sum_deadtimes = 0.0
        self.dtlast = 0.0

    def buffer_status(self):
        """Processing Rate and approximate number of free slots in this ringbuffer.
        This method is meant for user information purposes only, as the result may
        not be completely accurate due to race conditions.

        :return: cumulative event count, number of free slots, processing rate, average deadtime
        :rtype: tuple
        """
        # estimate number of filled slots in buffer
        with self.read_pointer_lock:
            actually_read = self.read_pointer - 1
        with self.write_pointer_lock:
            actually_written = self.write_pointer
        n_filled = actually_written - actually_read if actually_written >= actually_read else self.number_of_slots - actually_read + actually_written

        # determine event rate handled by this buffer
        T = time.time()
        dT = T - self.Tlast
        self.Tlast = T
        dN = self.cumulative_event_count - self.Nlast
        self.Nlast = self.cumulative_event_count
        rate = dN / dT
        # determine average dead time of events this buffer
        dD = self.sum_deadtimes - self.dtlast
        self.dtlast = self.sum_deadtimes
        av_deadtime = dD / (max(1, dN))

        return self.cumulative_event_count, n_filled, rate, av_deadtime

    def pause(self):
        """Disable writing to ringbuffer (paused)"""
        # Disable writing new data to the buffer
        self.writers_paused.set()

    def resume(self):
        """(Re)enable  writing to ringbuffer (resume)"""
        # re-enable writing new data to the buffer
        self.writers_paused.clear()

    def set_ending(self):
        """Stop data flow (before shut-down)"""
        self.writers_paused.set()  # raise paused flag
        self.writers_active.clear()  #
        time.sleep(0.5)
        self.readers_active.set()  # keep readers still active

    def shutdown(self):
        """Shut down the ringbuffer(s): close background threads, terminate associated processes and
        release the shared memory definitions.

        Affect processes using a ``Reader``, ``Writer`` or ``Observer`` instance to a ringbuffer.

        A 'trickle down' approach is used to have as few ringbuffer elements as possible unprocessed. This may not
        work correctly with more complex signal analysis chains. So always make sure to shut down the ringbuffers
        in data flow order (start with first element of the chain, the ringbuffer closest to the signal source).

        **CAUTION!** If there are loops in the signal analysis chain, this method may end in an infinite loop!
        """
        # Disable writing new data to the buffer
        self.writers_active.clear()
        # In case no new data is written to the buffer, send something to the
        # writer_filled_queue to unblock _writer_queue_listener(...) and allow the thread to terminate
        self.writer_filled_queue.put(None)
        # indicate  end-of-run to observers
        self.observers_active.clear()

        # Get the slot with the latest valid data
        with self.write_pointer_lock:
            latest_observed_index = self.write_pointer
        # Wait for readers to finish their queue
        while self.read_pointer < latest_observed_index:
            # while processing an element, while the following element was already done processing!
            # This could cause an infinite loop! (Only possible if the reader closes prematurely, eg.
            # due to unconventional signal chains!)
            print("Shutdown is waiting for processing to end!\n" "  processing: {:d}, target: {:d}".format(self.read_pointer, latest_observed_index))
            time.sleep(0.5)
            # We have to update latest_observed_index since self.write_pointer might change
            # in case self.read_pointer lapped the ring buffer
            with self.write_pointer_lock:
                latest_observed_index = self.write_pointer

        # set status flags to indicate end-of-run (not paused, active cleared)
        self.readers_active.clear()
        self.writers_paused.clear()
        # Now quit all reader processes (they are currently all blocking and waiting on the reader_todo_queue)

        wait_shutdown = True
        while wait_shutdown:
            wait_shutdown = False
            for q in self.reader_todo_queue_list:
                if q.empty():
                    wait_shutdown = True
                    q.put(None)
            time.sleep(0.1)
        # And quit the reader threads waiting to dispatch new data
        for q in self.reader_done_queue_list:
            q.put(None)

    def close(self):
        self._writer_queue_thread.join()
        for t in self.reader_queue_listener_thread_list:
            t.join()
        self.m_share.close()
        self.m_share.unlink()
        self.m_metadata_share.close()
        self.m_metadata_share.unlink()

    def __del__(self):
        # unlink shared memory if not done yet
        try:
            self.m_share.close()
            self.m_share.unlink()
            self.m_metadata_share.close()
            self.m_metadata_share.unlink()
        except Exception:
            pass


# <<-- end class NewBuffer


class Writer:
    """
    Class to write elements into a ringbuffer (multiple-in part).

    Ringbuffer elements are structured NumPy arrays. Writing is triggered by a call of
    ``Writer.process_buffer()`` or at the next call of ``Writer.get_new_buffer()``.
    The ringbuffer element is blocked while writes to the NumPy array are permitted.
    A program design processing the ringbuffer content has to call the ``Writer.process_buffer()``
    or ``Writer.get_new_buffer()``-methods in a way that minimizes the ringbuffer lock time.

    methods:

      - get_new_buffer()
      - set_metadata()
      - process_buffer()

    """

    def __init__(self, setup_dict):
        """
        Constructor to create a ``Writer``-object that grants access to the ringbuffer
        specified in the ``setup_dict`` object.

        :param setup_dict: The setup dictionary for the *writer* this instance is a part of.
            The setup dictionary can be obtained by calling ``NewBuffer.new_writer()`` in
            this instances' parent process. Sharing the same setup dictionary between multiple
            writer processes is possible, calling ``NewBuffer.new_writer()`` multiple times is
            allowed as well. Load balancing between processes is done on a 'first come first
            serve' basis. If multiple processes wait for new free spots, the allocation is
            managed by the scheduler of the host OS.
        """
        # Get buffer configuration from setup dictionary
        self.number_of_slots = setup_dict["number_of_slots"]
        self.values_per_slot = setup_dict["values_per_slot"]
        self.dtype = setup_dict["dtype"]
        # Connect the shared memory for data and metadata and map it into a NumPy array
        self._m_share = shared_memory.SharedMemory(name=setup_dict["mshare_name"])
        array_shape = (self.number_of_slots, self.values_per_slot)
        self._buffer = np.ndarray(shape=array_shape, dtype=self.dtype, buffer=self._m_share.buf)
        self._metadata_share = shared_memory.SharedMemory(name=setup_dict["metadata_share_name"])
        metadata_dtype = [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
        self._metadata = np.ndarray(
            shape=self.number_of_slots,
            dtype=metadata_dtype,
            buffer=self._metadata_share.buf,
        )

        # Get queues for IPC with the buffer manager
        self._empty_queue = setup_dict["empty_queue"]
        self._filled_queue = setup_dict["filled_queue"]

        # Setup class status variables
        self._current_buffer_index = None
        self._write_counter = 0
        self._active = setup_dict["active"]
        self._paused = setup_dict["paused"]
        self._debug = setup_dict["debug"]
        if self._debug:
            print(" > DEBUG: Writer created (PID: {:d})".format(os.getpid()))

    def __del__(self):
        """
        Destructor of the writer class
        """
        if self._debug:
            print(" > DEBUG: Writer destructor called (PID: {:d})".format(os.getpid()))
        # Clean up memory share
        del self._buffer
        self._m_share.close()
        del self._metadata
        self._metadata_share.close()

    def get_new_buffer(self):
        """Get a new free element in the ringbuffer.
            The last element obtained by calling this function is marked as "ready to be processed".
            No memory views of old elements may be accessed after calling this function.
            This function blocks if there are no free elements in the ringbuffer and always returns
            a valid NumPy array that can be written to.

        :raises SystemExit: When the ``shutdown()``-method of the ``NewBuffer`` object has been
            called, a SystemExit is raised which terminates the process.
        :return: One free ringbuffer element (structured numpy.ndarray) as specified in the
            ``NewBuffer()-dtype``-object. Free elements may contain older data, but they
            can be safely overwritten.
        :rtype: numpy.ndarray
        """
        if self._current_buffer_index is not None:
            self.process_buffer()
        # Only return buffer if index is valid!
        self._current_buffer_index = None
        while self._current_buffer_index is None:
            self._current_buffer_index = self._empty_queue.get()
            if not self._active.is_set():
                raise SystemExit
        # Set dummy metadata (to overwrite old metadata in this slot)
        self._metadata[self._current_buffer_index]["timestamp"] = -1
        self._metadata[self._current_buffer_index]["counter"] = self._write_counter
        self._metadata[self._current_buffer_index]["deadtime"] = -1
        self._write_counter += 1
        return self._buffer[self._current_buffer_index, :]

    def set_metadata(self, counter, timestamp, deadtime):
        """Set the metadata defined for the current ringbuffer element.
        If there is no current ringbuffer element (e.g. because ``process_buffer()`` has been
        called or ``get_new_buffer()`` has not been called yet), nothing happens.
        Copying metadata from a ``Reader`` to a ``Writer`` object (here called ``source``
        and ``sink``) can be done with:

            ``sink.set_metadata(*source.get_metadata())``

        :param counter: a unique, 0 based, consecutive integer referencing this element
        :type counter: integer (np.longlong)
        :param timestamp: the UTC timestamp
        :type timestamp: float (np.float64)
        :param deadtime: In a live-data environment, the dead time of the first
            writer in the analyses chain. This is meant to be the fraction of dead
            time to active data capturing time (so 0.0 = no dead time whatsoever;
            0.99 = only 1% of the time between this and the last element was spent
            with active data capturing)
        :type deadtime: float (np.float64)
        """
        if self._current_buffer_index is not None:
            self._metadata[self._current_buffer_index]["counter"] = counter
            self._metadata[self._current_buffer_index]["timestamp"] = timestamp
            self._metadata[self._current_buffer_index]["deadtime"] = deadtime

    def process_buffer(self):
        """Mark the current ringbuffer element as "ready to be processed".

        The content of the array MUST NOT be changed after calling this function.
        If there is no current element, nothing happens.
        As the ringbuffer element is blocked while writing to the NumPy array it is
        recommended to call ``Writer.process_buffer()`` as soon as possible to
        minimize the ringbuffer lock time.
        """
        if self._current_buffer_index is not None:
            if self._metadata[self._current_buffer_index]["timestamp"] == -1:
                self._metadata[self._current_buffer_index]["timestamp"] = time.time_ns() * 1e-9  # in s as type float64
            self._filled_queue.put(self._current_buffer_index)
            self._current_buffer_index = None


# <<-- end class Writer


class Reader:
    """
    Class to read elements from a ringbuffer (multiple-out part).

    Ringbuffer elements are structured NumPy arrays and strictly **read-only**. The returned
    array won't change until the next ``Reader.get()`` call is performed, blocking
    the ringbuffer element for the time being.
    A program design processing the ringbuffer content has to call the ``Reader.get()``-method
    in a way that minimizes the ringbuffer lock time.

    methods:

      - get()
      - get_metadata():

    """

    def __init__(self, setup_dict):
        """
        Constructor to create a ``Reader``-object that grants access to the ringbuffer
        specified in the ``setup_dict`` object.

        :param setup_dict: The setup dictionary for the *reader group* this instance is a part of.
            The setup dictionary can be obtained by calling ``NewBuffer.new_reader_group()`` in
            this instances' parent process. When the same setup dictionary is shared by several
            reader processes, the elements are distributed among the individual process of the group.
            Each ringbuffer element is processed by the group, but only one process in the group receives
            a particular element at a time.
            Load balancing between processes is done on a 'first come first serve' basis.
            If multiple processes wait on new elements, the allocation is managed by the
            scheduler of the host OS.
        """

        # Get buffer configuration from setup dictionary
        self.number_of_slots = setup_dict["number_of_slots"]
        self.values_per_slot = setup_dict["values_per_slot"]
        self.dtype = setup_dict["dtype"]
        # Connect the shared memory for data and metadata and map it into a NumPy array
        self._m_share = shared_memory.SharedMemory(name=setup_dict["mshare_name"])
        array_shape = (self.number_of_slots, self.values_per_slot)
        self._buffer = np.ndarray(shape=array_shape, dtype=self.dtype, buffer=self._m_share.buf)
        # self._buffer.flags.writeable = False  # to be tested?
        self._metadata_share = shared_memory.SharedMemory(name=setup_dict["metadata_share_name"])
        self.metadata_dtype = [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
        self._metadata = np.ndarray(
            shape=self.number_of_slots,
            dtype=self.metadata_dtype,
            buffer=self._metadata_share.buf,
        )

        # Get queues for IPC with the buffer manager
        self._todo_queue = setup_dict["todo_queue"]
        self._done_queue = setup_dict["done_queue"]

        # Setup class status variables
        self._last_get_index = None
        self._active = setup_dict["active"]
        self._paused = setup_dict["paused"]
        self._debug = setup_dict["debug"]
        if self._debug:
            print(" > DEBUG: Reader created (PID: {:d})".format(os.getpid()))

    def __del__(self):
        """
        Destructor of the reader class
        """
        if self._debug:
            print(" > DEBUG: Reader destructor called (PID: {:d})".format(os.getpid()))
        # Clean up queue (since there is no further processing done on the current element)
        if self._last_get_index is not None:
            self._done_queue.put(self._last_get_index)
        # Clean up shared memory
        del self._buffer
        self._m_share.close()
        del self._metadata
        self._metadata_share.close()

    def data_available(self):
        """Method to check for new data and avoid blocking of consumers"""
        return not self._todo_queue.empty()

    def get(self):
        """Get a new element from the ringbuffer.
        The last element obtained by calling this function is marked as "processing is done".
        No memory views of old elements may be accessed after calling this function (memory
        might change, be corrupted or be inconsistent).
        This function blocks if there are no new elements in the ringbuffer.


        :raises SystemExit: When the ``shutdown()``-method of the ``NewBuffer`` object has been
            called, a SystemExit is raised which terminates the process.
        :return: One element (structured numpy.ndarray) of the ringbuffer as specified in
            the ``NewBuffer()-dtype``-object.
        :rtype: numpy.ndarray
        """
        # Mark the last element as ready to be overwritten
        if self._last_get_index is not None:
            self._done_queue.put(self._last_get_index)
        self._last_get_index = None
        # Only return a buffer if the index is valid!
        while self._last_get_index is None:
            self._last_get_index = self._todo_queue.get()
            # Check if the parent buffer has been 'shutdown()'.
            # If yes, end this process
            if not self._active.is_set():
                raise SystemExit
        # Create a memory view of the buffer element's array index and
        # return it for further processing
        return self._buffer[self._last_get_index, :]

    def get_metadata(self):
        """Get the metadata defined for a ringbuffer element of the ``Reader.get()``-method.

        :return: Currently a 3-tuple is returned with ``(counter, timestamp , deadtime)``
            which is assigned to the latest element of the ringbuffer. The content of these
            variables is filled by the ``Writer``-process.
            The current convention is:

            -  counter (int): a unique, 0 based, consecutive integer referencing this element
            -  timestamp (float): the UTC timestamp
            -  deadtime (float): In a live-data environment, the dead time of the first
                 writer in the analyses chain. This is meant to be the fraction of dead
                 time to active data capturing time (so 0.0 = no dead time whatsoever;
                 0.99 = only 1% of the time between this and the last element was spent
                 with active data capturing)
        :rtype: tuple
        """
        if self._last_get_index is not None:
            timestamp = self._metadata[self._last_get_index]["timestamp"]
            counter = self._metadata[self._last_get_index]["counter"]
            deadtime = self._metadata[self._last_get_index]["deadtime"]
            return counter, timestamp, deadtime
        else:
            return 0, -1, -1


# <<-- end class Reader


class Observer:
    """
    Class for reading selected elements from a ringbuffer via q multiprocessing Queue

    The data transfer is implemented via a multiprocessing Queue and interfaces
    with the ringbuffer manager (``NewBuffer``-class).
    """

    def __init__(self, setup_dict):
        """Constructor to create an ``Observer``-object that grants access to the ringbuffer
        specified in the ``setup_dict`` object.

        :param setup_dict: The setup dictionary for the *observer* this instance is a part of.
            The setup dictionary can be obtained by calling ``NewBuffer.new_Qobserver()`` in
            this instances' parent process. Sharing the same setup dictionary between multiple
            observer processes is possible, calling ``NewBuffer.new_Qobserver()`` multiple
            times is allowed as well.
        """
        self._active = setup_dict["active"]
        self._paused = setup_dict["paused"]
        self._debug = setup_dict["debug"]
        self.dataQ = setup_dict["dataQ"]

        if self._debug:
            print(" > DEBUG: QObserver  created (PID: {:d})".format(os.getpid()))

    def get(self):
        """
        Get latest element from buffer: metadata  and data

        As new data is provided and transferred as soon as data is read from
        the Queue, the get() method must not be called too frequentls
        """
        # transferred data is either None (end of data taking) or a tuple  (metadata, data)
        d = self.dataQ.get()
        return d

    def __del__(self):
        """
        Destructor of the ``QObserver`` class
        """
        if self._debug:
            print(" > DEBUG: QObserver destructor called (PID: {:d})".format(os.getpid()))


# <<-- end class Observer
