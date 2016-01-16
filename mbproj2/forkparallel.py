"""Module to run a forked parallel process."""

from __future__ import division, print_function

import os
import socket
import struct
import select
import signal

try:
    import cPickle as pickle
except ImportError:
    import pickle

# special exit code to break out of child
exitcode = b'*[EX!T}*FORK'

# type used to send object size
sizesize = struct.calcsize('L')

def recvLen(sock, length):
    """Receive exactly length bytes."""
    retn = b''
    while len(retn) < length:
        retn += sock.recv(length-len(retn))
    return retn

def sendItem(sock, item):
    """Pickle and send item using size + pickled protocol."""
    pickled = pickle.dumps(item)
    size = struct.pack('L', len(pickled))
    sock.sendall(size + pickled)

def recvItem(sock):
    """Receive pickled item."""
    retn = sock.recv(64*1024)

    size = struct.unpack('L', retn[:sizesize])[0]
    retn = retn[sizesize:]

    while len(retn) < size:
        retn += sock.recv(size-len(retn))
    return pickle.loads(retn)

class ForkBase:
    """Base class for forking workers."""

    def __init__(self, func):
        self.func = func
        self.sock = None
        self.amparent = False

    def childLoop(self):
        """Wait for commands on the socket and execute."""

        if self.amparent:
            raise RuntimeError('Not child, or not started')

        # ignore ctrl+c
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # repeat until exit code or socket breaks
        try:
            while True:
                # get data to process
                args = recvItem(self.sock)

                #print('received', args)

                # exit if parent is done
                if args == exitcode:
                    break

                retn = []
                # presumably no socket error in below
                try:
                    # iterate over input and add result with index key
                    for arg in args:
                        res = self.func(arg)
                        retn.append(res)
                except Exception as e:
                    # send back an exception
                    retn = e

                # send back the result
                sendItem(self.sock, retn)

        except socket.error:
            #print('Breaking on socket error')
            pass

        #print('Exiting child')
        os._exit(os.EX_OK)

class ForkParallel(ForkBase):
    """Execute function in remote forked process."""

    def __init__(self, func):
        """Parallel forked runner for running func."""

        ForkBase.__init__(self, func)
        self.running = False

        # sockets communicate between forked processes
        parentsock, childsock = socket.socketpair()

        pid = os.fork()
        self.amparent = pid != 0

        if self.amparent:
            self.sock = parentsock
            childsock.close()
        else:
            self.sock = childsock
            parentsock.close()
            self.childLoop()

    def __del__(self):
        """Tell child to close and close sockets."""

        if self.sock is not None:
            try:
                if self.amparent:
                    sendItem(self.sock, exitcode)
                self.sock.close()
            except socket.error:
                pass

    def send(self, args):
        """Send data to be processed."""

        if not self.amparent:
            raise RuntimeError('Not parent, or not started')
        if self.running:
            raise RuntimeError('Remote process is still executing')

        self.running = True
        sendItem(self.sock, [args])

    def query(self, timeout=0):
        """Return isdone,result from remote process."""

        if not self.amparent:
            raise RuntimeError('Not parent, or not started')
        if not self.running:
            raise RuntimeError('Remote process is already done')

        readsock, writesock, errsock = select.select([self.sock], [], [], timeout)
        if readsock:
            retn = recvItem(self.sock)
            self.running = False
            if isinstance(retn, Exception):
                raise retn
            return True, retn[0]
        else:
            return False, None

    def wait(self):
        """Wait until a response, and return value."""
        while True:
            done, res = self.query(timeout=6000)
            if done:
                return res

class ForkQueue(ForkBase):
    """Execute function in multiple forked processes."""

    def __init__(self, func, instances, initfunc=None):
        """Initialise queue for func and with number of instances given.

        if initfunc is set, run this at first
        """

        ForkBase.__init__(self, func)

        self.socks = []

        for i in xrange(instances):
            parentsock, childsock = socket.socketpair()

            if os.fork() == 0:
                # child process
                parentsock.close()
                self.sock = childsock
                self.amparent = False

                # close other children (we don't need to talk to them)
                del self.socks

                # call the initialise function, if required
                if initfunc is not None:
                    initfunc()

                # wait for commands from parent
                self.childLoop()

                # return here, or we get a fork bomb!
                return

            else:
                # parent process - keep track of children
                self.socks.append(parentsock)
                childsock.close()

        self.amparent = True

    def __del__(self):
        """Close child forks and close sockets."""
        if self.amparent:
            for sock in self.socks:
                try:
                    sendItem(sock, exitcode)
                    sock.close()
                except socket.error:
                    pass
        else:
            try:
                self.sock.close()
            except socket.error:
                pass

    def execute(self, argslist):
        """Execute the list of items on the queue.

        This version cheats by just splitting the input up into
        equal-sized chunks.

        An old version used a more sophisticated select on the
        sockets, sending individual items. It was slower than doing
        this. May be an idea to switch to a hybrid method, depending
        on number of items.
        """

        if not self.amparent:
            raise RuntimeError('Not parent, or not started')

        # round up chunk size
        num = len(argslist)
        chunksize = -(-num//len(self.socks))

        i=0
        for s in self.socks:
            sendItem(s, argslist[i:i+chunksize])
            i += chunksize

        results = []
        for s in self.socks:
            res = recvItem(s)
            results += res

        return results