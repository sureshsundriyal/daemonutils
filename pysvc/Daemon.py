#!/usr/bin/python

__author__ = "Suresh Sundriyal"
__copyright__ = "Copyright 2014, Suresh Sundriyal"
__license__ = "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2"

import os
import pwd
import sys
import fcntl
import random
import signal
import string
import logging

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

PR_SET_NAME = 15
prctl = None

def noop():
    return

class DaemonException(Exception):
    pass

class DaemonizeFunc(object):
    def __init__(self, func, args=None, kwargs=None, proc_name=None,
                pidfile=True, user=None, outfile=os.devnull, errfile=os.devnull,
                chdir='/', umask=None, close_fds=True, cloexec=True,
                rundir='/var/run'):
        self.func = func
        self.daemon_name = func.__name__
        self.args = args
        self.kwargs = kwargs
        self.proc_name = proc_name
        self.pidfile = pidfile
        self.pidfilename = os.path.join(rundir, "%s-%s.pid" % (self.daemon_name,
                                        ''.join(random.sample(
                                        string.ascii_lowercase, 5))))
        self.uid = None
        self.gid = None
        if user:
            pw = pwd.getpwnam(user)
            self.uid = pw.pw_uid
        self.stdout = outfile
        self.stderr = errfile
        self.chdir = chdir
        self.umask = umask
        self.close_fds = close_fds
        self.cloexec = cloexec
        self.original_umask = None
        self.pid = None
        self.rc = 0

    def perror(self, error):
        return "[%s:%s] %s" % (self.daemon_name, self.pid, error)

    def close_and_redirect_fds(self):
        def __open_file_and_set_cloexec(filename, flags):
            try:
                fd = os.open(filename, flags)
                if self.cloexec:
                    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
                    fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
            except:
                sys.exit(self.perror(
                    "Failed to open and set CLOEXEC on %s" % filename))
            return fd
        if not self.stdout or not self.stderr:
            if self.stdout == self.stderr:
                fd = __open_file_and_set_cloexec(self.stdout,
                             os.O_CREAT | os.O_WRONLY | os.O_APPEND)
                sys.stdout = fd
                sys.stderr = fd
            else:
                if self.stdout:
                    sys.stdout = __open_file_and_set_cloexec(self.stdout,
                                    os.O_CREAT | os.O_WRONLY | os.O_APPEND)
                if self.stderr:
                    sys.stderr = __open_file_and_set_cloexec(self.stderr,
                                    os.O_CREAT | os.O_WRONLY | os.O_APPEND)

        if not self.close_fds:
            return

        if hasattr(os, 'closerange'):
            try:
                os.closerange(3, MAXFD)
            except OSError:
                pass
        else:
            for fd in xrange(3, MAXFD):
                try:
                    os.close(fd)
                except OSError:
                    pass

    def set_proc_name(self):
        global prctl
        if self.proc_name:
            if prctl == None:
                try:
                    import ctypes, ctypes.util

                    _libc = ctypes.CDLL(ctypes.util.find_library("c"),
                                        use_errno=True)

                    if hasattr(_libc, "prctl"):
                        prctl = _libc.prctl
                    else:
                        prctl = 0
                except Exception, e:
                    prctl = 0
                    logging.exception("Failed to initialize prctl")

            if prctl == 0:
                return
            try:
                prctl(PR_SET_NAME, ctypes.c_char_p(self.proc_name),
                      0, 0, 0)
            except:
                logging.exception(
                        self.perror("Failed to set process name: %s" %\
                                    self.proc_name))
                pass

    def setup_daemon(self):
        # set sid
        process_id = os.setsid()
        if process_id == -1:
            sys.exit(self.perror("Failed to setsid"))

        # Change the running directory
        if self.chdir:
            try:
                os.chdir(self.chdir)
            except Exception, e:
                sys.exit(self.perror("Failed to chdir : %s" % e))

        # set the current process' umask
        if self.umask:
            try:
                self.original_umask = os.umask(self.umask)
            except Exception, e:
                sys.exit(self.perror("Failed to set the umask : %s" % e))

        # set the current process' uid
        if self.uid:
            try:
                os.setuid(self.uid)
            except Exception, e:
                sys.exit(self.perror("Failed to setuid : %s" % e))

        # Close all the file descriptors
        self.close_and_redirect_fds()
        if prctl != 0 and not self.proc_name:
            self.set_proc_name()


    def write_pid_file(self):
        if self.pidfile:
            _pidfile = os.open(self.pidfilename, 'w')
            _pidfile.write("%s" % self.pid)
            _pidfile.close()

    def delete_pid_file(self):
        if self.pidfile:
            try:
                os.remove(self.pidfilename)
            except (OSError, IOError):
                pass

    def start(self):
        self.pid = os.fork()
        if self.pid != 0:
            return
        self.pid = os.getpid()

        self.setup_daemon()

        try:
            self.write_pid_file()
            if self.args and self.kwargs:
                self.func(*self.args, **self.kwargs)
            elif self.args:
                self.func(*self.args)
            elif self.kwargs:
                self.func(**self.kwargs)
            else:
                self.func()
        finally:
            self.delete_pid_file()

    def is_alive(self):
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            self.delete_pid_file()
            return False

    def stop(self):
        if not self.pid:
            return

        for signum in [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]:
            sigalrm_handler = None
            try:
                sigalrm_handler = signal.signal(signal.SIGALRM, noop)
                signal.alarm(3)
                os.kill(self.pid, signum)
                pid, exit_status = os.waitpid(self.pid, 0)
                signal.alarm(0)
                self.rc = os.WEXITSTATUS(exit_status)
                break
            except:
                pass
            finally:
                signal.signal(signal.SIGALRM, sigalrm_handler)
