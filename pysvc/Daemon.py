#!/usr/bin/python

__author__ = "Suresh Sundriyal"
__copyright__ = "Copyright 2014, Suresh Sundriyal"
__license__ = "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2"

import os
import pwd
import sys
import signal
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
                pidfile=None, user=None, outfile=os.devnull, errfile=os.devnull,
                chdir='/', umask=None, close_fds=True,
                rundir='/var/run'):
        self.func = func
        self.daemon_name = func.__name__
        self.args = args
        self.kwargs = kwargs
        self.proc_name = proc_name
        self.pidfile = os.path.join(rundir, "%s.pid" %pidfile)
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
        self.original_umask = None
        self.pid = None
        self.rc = 0

    def perror(self, error):
        return "[%s:%s] %s" % (self.daemon_name, self.pid, error)

    def close_and_redirect_fds(self):
        if not self.stdout or not self.stderr:
            if self.stdout == self.stderr:
                try:
                    fd = os.open(self.stdout,
                                 os.O_CREAT | os.O_WRONLY | os.O_APPEND)
                    sys.stdout = fd
                    sys.stderr = fd
                except Exception, e:
                    sys.exit(self.perror("Failed to redirect stdout/stderr: %s"\
                             % e))
            else:
                if self.stdout:
                    try:
                        sys.stdout = os.open(self.stdout,
                                        os.O_CREAT | os.O_WRONLY | os.O_APPEND)
                    except Exception, e:
                        sys.exit(self.perror("Failed to redirect stdout: %s" % e))
                if self.stderr:
                    try:
                        sys.stderr = os.open(self.stderr,
                                        os.O_CREAT | os.O_WRONLY | os.O_APPEND)
                    except:
                        sys.exit(self.perror("Failed to redirect stderr: %s" % e))

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
        pidfile = os.open(self.pidfile, 'w')
        pidfile.write("%s" % self.pid)
        pidfile.close()

    def delete_pid_file(self):
        try:
            os.remove(self.pidfile)
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
            except:
                pass
            finally:
                signal.signal(signal.SIGALRM, sigalrm_handler)
