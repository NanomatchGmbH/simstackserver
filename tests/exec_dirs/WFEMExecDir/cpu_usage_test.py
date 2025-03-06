#!/usr/bin/env python3
import time
import numpy as np
import psutil
from multiprocessing import Process as MPProcess
#from threading import Thread

class PinnedException(Exception):
    pass

class CheckCPUAffinity(object):
    def __init__(self,verbose = True, outstream = None, target_cpus = None):
        self._num_logical = psutil.cpu_count()
        self._num_real = psutil.cpu_count(logical=False)
        if target_cpus is None:
            # We assume full node in this case.
            self._target_cpus = self._num_real
        else:
            self._target_cpus = target_cpus
        self._process = psutil.Process()
        self._initial_affinity = self._process.cpu_affinity()
        self._verbose = verbose

    def check_affinity(self):
        self._initial_affinity = self._process.cpu_affinity()
        is_pinned = False
        if len(self._initial_affinity) < self._num_logical:
            # This is not verbose, because it needs to be communicated.
            print("Process seems to be pinned, number of CPUs in system (logical,real) : (%d,%d). Process was pinned to CPU numbers: %s"%(self._num_logical,self._target_cpus,self._affinity_to_string(self._initial_affinity)))
            is_pinned = True
        return is_pinned

    @staticmethod
    def _affinity_to_string(affinity_list):
        return ",".join([str(number) for number in affinity_list])

    def try_reset_affinity(self):
        previous_affinity = self._initial_affinity
        self._process.cpu_affinity([*range(0,self._num_logical)])
        current_affinity = self._process.cpu_affinity()
        if previous_affinity == current_affinity and len(current_affinity) == self._num_logical:
            print("CPU affinity reset did not do anything.\n Previous affinity %s.\n Current affinity %s\n" %(self._affinity_to_string(previous_affinity),self._affinity_to_string(current_affinity)))
        else:
            if self._verbose:
                print("CPU affinities changed successfully:\n Previous affinity %s.\n Current affinity %s\n" %(self._affinity_to_string(previous_affinity),self._affinity_to_string(current_affinity)))
        self._initial_affinity = current_affinity
        """
        parent = psutil.Process(self._process.ppid())
        while True:
            print("Parent process %d had affinity: %s"% (parent.pid,self._affinity_to_string(parent.cpu_affinity())) )
            if parent.ppid() == 1:
                break
            parent = psutil.Process(parent.ppid())
        """

    def stress_for_seconds(self,integer_seconds):
        # This function produces stress for approximately integer seconds.
        start = time.time()
        while True:
            for i in range(1,50):
                in_array = np.random.randn((10000))
                in_array = np.exp(in_array)
            now = time.time()
            if int(now - start) >= integer_seconds:
                break
        me = psutil.Process()
        print(self._affinity_to_string(me.cpu_affinity()))

    def burn_tests(self, seconds_per_test, raise_exception = False):
        verbose = self._verbose
        if seconds_per_test < 4.9:
            print("Please allocate at least 5.0 seconds per test for good results. Testing anyways.")
        processes = []

        ### Multiprocess benchmark starting here:
        for i in range(0,self._target_cpus):
            p = MPProcess(target=self.stress_for_seconds,args=(seconds_per_test,) )
            processes.append(p)

        now = time.time()
        if verbose:
            print("Burning on %d individual threads."%(self._target_cpus))

        for i in range(0,self._target_cpus):
            processes[i].start()

        process_children = self._process.children(recursive=True)
        for child in process_children:
            child.cpu_percent(interval=None)
        # We wait about 3/4 of the time and check cpu usage
        sleeptime = time.sleep(seconds_per_test*3.0/4.0)

        total_cpu_percent = 0.0
        for child in process_children:
            total_cpu_percent += child.cpu_percent(interval=None)



        for i in range(0,self._target_cpus):
            processes[i].join()

        processes.clear()

        if verbose:
            print("The total cpu percent of these processes is: %3.2f%%" %total_cpu_percent)
            print("If the complete node was allocated this should be roughly %d%%"%(self._target_cpus * 100))
        if total_cpu_percent < self._target_cpus*100*0.8:
            message = "The total cpu percent in the multiprocess benchmark was %3.2f%%, which was significantly less than the expected %d%%."%(total_cpu_percent,self._target_cpus*100)
            print(message)
            if raise_exception == True:
                raise PinnedException(message)

        # Multithread benchmark here, doesn't work yet, due to GIL
        """
        threads = []
        for i in range(0,self._target_cpus):
            t = Thread(target=self.stress_for_seconds,args=(seconds_per_test,) )
            threads.append(t)
 
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
        """

        runtime = time.time() - now
        if verbose:
            print("Individual process stress done, Runtime: %d seconds"%(runtime))


if __name__ == '__main__':
    from mpi4py import MPI
    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    p = psutil.Process()
    cca = CheckCPUAffinity()

    if cca.check_affinity():
       cca.try_reset_affinity()

    if rank == 0:
        #cca = CheckCPUAffinity()

        #if cca.check_affinity():
        #   cca.try_reset_affinity()

        cca.burn_tests(5, raise_exception = False)
    else:
        import time
        time.sleep(5)
    comm.barrier()