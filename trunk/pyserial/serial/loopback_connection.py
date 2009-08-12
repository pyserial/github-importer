#! python
#
# Python Serial Port Extension for Win32, Linux, BSD, Jython
# see __init__.py
#
# This module implements a loop back connection receiving itself what it sent.
#
# The purpose of this module is.. well... You can run the unit tests with it.
# and it was so easy to implement ;-)
#
# (C) 2001-2009 Chris Liechti <cliechti@gmx.net>
# this is distributed under a free software license, see license.txt
#
# URL format:    loop://[option[/option...]]
# options:
# - "debug" print diagnostic messages

from serialutil import *
import threading
import time
import logging

# map log level names to constants. used in fromURL()
LOGGER_LEVELS = {
    'debug': logging.DEBUG,
    'info': logging.INFO,
    'warning': logging.WARNING,
    'error': logging.ERROR,
    }


class LoopbackSerial(SerialBase):
    """Serial port implementation for plain sockets."""

    BAUDRATES = (50, 75, 110, 134, 150, 200, 300, 600, 1200, 1800, 2400, 4800,
                 9600, 19200, 38400, 57600, 115200)

    def open(self):
        """Open port with current settings. This may throw a SerialException
           if the port cannot be opened."""
        self.debug_output = None
        self.buffer_lock = threading.Lock()
        self.loop_buffer = bytearray()
        self.cts = False
        self.dsr = False

        if self._port is None:
            raise SerialException("Port must be configured before it can be used.")
        # not that there is anything to open, but the function applies the
        # options found in the URL
        self.fromURL(self.port)

        # not that there anything to configure...
        self._reconfigurePort()
        # all things set up get, now a clean start
        self._isOpen = True
        if not self._rtscts:
            self.setRTS(True)
            self.setDTR(True)
        self.flushInput()
        self.flushOutput()

    def _reconfigurePort(self):
        """Set communication parameters on opened port. for the loop://
        protocol all settings are ignored!"""
        # not that's it of any real use, but it helps in the unit tests
        if not isinstance(self._baudrate, (int, long)) or not 0 < self._baudrate < 2**32:
            raise ValueError("invalid baudrate: %r" % (self._baudrate))
        if self.debug_output:
            self.debug_output.info('_reconfigurePort()')

    def close(self):
        """Close port"""
        if self._isOpen:
            self._isOpen = False
            # in case of quick reconnects, give the server some time
            time.sleep(0.3)

    def makeDeviceName(self, port):
        raise SerialException("there is no sensible way to turn numbers into URLs")

    def fromURL(self, url):
        """extract host and port from an URL string"""
        if url.lower().startswith("loop://"): url = url[7:]
        try:
            # process options now, directly altering self
            for option in url.split('/'):
                if not option:
                    pass
                if '=' in option:
                    option, value = option.split('=', 1)
                else:
                    value = None
                if option == 'logging':
                    logging.basicConfig()   # XXX is that good to call it here?
                    self.debug_output = logging.getLogger('pySerial.loop')
                    self.debug_output.setLevel(LOGGER_LEVELS[value])
                    self.debug_output.debug('enabled logging')
                else:
                    raise ValueError('unknown option: %r' % (option,))
        except ValueError, e:
            raise SerialException('expected a string in the form "[loop://][option[/option...]]": %s' % e)

    #  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -  -

    def inWaiting(self):
        """Return the number of characters currently in the input buffer."""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            # attention the logged value can differ from return value in
            # threaded environments...
            self.debug_output.debug('inWaiting() -> %d' % (len(self.loop_buffer),))
        return len(self.loop_buffer)

    def read(self, size=1):
        """Read size bytes from the serial port. If a timeout is set it may
        return less characters as requested. With no timeout it will block
        until the requested number of bytes is read."""
        if not self._isOpen: raise portNotOpenError
        if self._timeout is not None:
            timeout = time.time() + self._timeout
        else:
            timeout = None
        data = bytearray()
        while len(data) < size:
            self.buffer_lock.acquire()
            try:
                block = to_bytes(self.loop_buffer[:size])
                del self.loop_buffer[:size]
            finally:
                self.buffer_lock.release()
            data += block
            # check for timeout now, after data has been read.
            # useful for timeout = 0 (non blocking) read
            if timeout and time.time() > timeout:
                break
        return bytes(data)

    def write(self, data):
        """Output the given string over the serial port. Can block if the
        connection is blocked. May raise SerialException if the connection is
        closed."""
        if not self._isOpen: raise portNotOpenError
        # calculate aprox time that would be used to send the data
        time_used_to_send = 10.0*len(data) / self._baudrate
        # when a write timeout is configured check if we would be successful
        # (not sending anything, not even the part that would have time)
        if self._writeTimeout is not None and time_used_to_send > self._writeTimeout:
            time.sleep(self._writeTimeout) # must wait so that unit test succeeds
            raise writeTimeoutError
        self.buffer_lock.acquire()
        try:
            self.loop_buffer += bytes(data)
        finally:
            self.buffer_lock.release()
        return len(data)

    def flushInput(self):
        """Clear input buffer, discarding all that is in the buffer."""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('flushInput()')
        self.buffer_lock.acquire()
        try:
            del self.loop_buffer[:]
        finally:
            self.buffer_lock.release()

    def flushOutput(self):
        """Clear output buffer, aborting the current output and
        discarding all that is in the buffer."""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('flushOutput()')

    def sendBreak(self, duration=0.25):
        """Send break condition. Timed, returns to idle state after given
        duration."""
        if not self._isOpen: raise portNotOpenError

    def setBreak(self, level=True):
        """Set break: Controls TXD. When active, to transmitting is
        possible."""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('setBreak(%r)' % (level,))

    def setRTS(self, level=True):
        """Set terminal status line: Request To Send"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('setRTS(%r) -> state of CTS' % (level,))
        self.cts = level

    def setDTR(self, level=True):
        """Set terminal status line: Data Terminal Ready"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('setDTR(%r) -> state of DSR' % (level,))
        self.dsr = level

    def getCTS(self):
        """Read terminal status line: Clear To Send"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('getCTS() -> state of RTS (%r)' % (self.cts,))
        return self.cts

    def getDSR(self):
        """Read terminal status line: Data Set Ready"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('getDSR() -> state of DTR (%r)' % (self.dsr,))
        return self.dsr

    def getRI(self):
        """Read terminal status line: Ring Indicator"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('returning dummy for getRI()')
        return False

    def getCD(self):
        """Read terminal status line: Carrier Detect"""
        if not self._isOpen: raise portNotOpenError
        if self.debug_output:
            self.debug_output.info('returning dummy for getCD()')
        return True

    # - - - platform specific - - -
    # None so far


# assemble Serial class with the platform specific implementation and the base
# for file-like behavior. for Python 2.6 and newer, that provide the new I/O
# library, derive from io.RawIOBase
try:
    import io
except ImportError:
    # classic version with our own file-like emulation
    class Serial(LoopbackSerial, FileLike):
        pass
else:
    # io library present
    class Serial(LoopbackSerial, io.RawIOBase):
        pass


# simple client test
if __name__ == '__main__':
    import sys
    s = Serial('socket://localhost:7000')
    sys.stdout.write('%s\n' % s)

    sys.stdout.write("write...\n")
    s.write("hello\n")
    s.flush()
    sys.stdout.write("read: %s\n" % s.read(5))

    s.close()
