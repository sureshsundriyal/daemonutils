#!/usr/bin/python

__author__ = "Suresh Sundriyal"
__copyright__ = "Copyright 2014, Suresh Sundriyal"
__license__ = "The BSD 2-Clause License"

import os
import sys
import fcntl
import atexit
import signal
import logging

try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256

PR_SET_NAME = 15
prctl = None

def _perror(error):
    return("[%s] %s" % (os.getpid(), error))


def _open_file_and_set_cloexec(filename, flags, cloexec):
    try:
        fd = os.open(filename, flags)
        if cloexec:
            flags = fcntl.fcntl(fd, fcntl.F_GETFD)
            fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
        return fd
    except Exception, err:
        sys.exit(_perror(
            "Failed to open and set CLOEXEC on %s, %s" % (filename, err)))

def _close_and_redirect_fds(stdout, stderr, close_fds, cloexec):
    if stdout or stderr:
        if stdout == stderr:
            fd = _open_file_and_set_cloexec(stdout,
                        os.O_CREAT | os.O_WRONLY | os.O_APPEND, cloexec)
            os.dup2(fd, sys.stdout.fileno())
            os.dup2(fd, sys.stderr.fileno())
        else:
            if stdout:
                os.dup2(_open_file_and_set_cloexec(stdout,
                        os.O_CREAT | os.O_WRONLY | os.O_APPEND, cloexec),
                        sys.stdout.fileno())
            if stderr:
                os.dup2(_open_file_and_set_cloexec(stderr,
                        os.O_CREAT | os.O_WRONLY | os.O_APPEND, cloexec),
                        sys.stderr.fileno())

        if not close_fds:
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

def _set_proc_name(proc_name):
    global prctl
    if proc_name:
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
                logging.exception("Failed to initialize prctl")
                prctl = 0

        if prctl == 0:
            return

        try:
            prctl(PR_SET_NAME, ctypes.c_char_p(proc_name), 0, 0, 0)
        except:
            logging.exception(
                    _perror("Failed to set process name: %s" %\
                            proc_name))


def _setup_process_environment(chdir, umask, uid, gid):
    # set sid
    process_id = os.setsid()
    if process_id == -1:
        sys.exit(_perror("Failed to setsid"))

    # Change the running directory
    if chdir:
        try:
            os.chdir(chdir)
        except Exception, e:
            sys.exit(_perror("Failed to chdir : %s" % e))

    # set the current process' umask
    if umask:
        try:
            os.umask(umask)
        except Exception, e:
            sys.exit(_perror("Failed to set the umask : %s" % e))

    # set the current process' uid
    if uid:
        try:
            os.setuid(uid)
        except Exception, e:
            sys.exit(_perror("Failed to setuid : %s" % e))

    # set the process' gid
    if gid:
        try:
            os.setgid(gid)
        except Exception, e:
            sys.exit(_perror("Failed to setgid : %s" % e))


def _write_pid_file(pidfile):
    if pidfile:
        _pidfile = open(pidfile, 'w')
        _pidfile.write("%s" % os.getpid())
        _pidfile.close()

def _delete_pid_file(pidfile):
    if pidfile:
        try:
            print "Deleting file"
            os.remove(pidfile)
        except (OSError, IOError):
            pass

def background_process(func=None, args=None, kwargs=None, proc_name=None,
        uid=None, gid=None, stdout=os.devnull, stderr=os.devnull, chdir='/',
        umask=None, close_fds=True, cloexec=True, pidfile=None, daemonize=True):

    pid = os.fork()

    if pid != 0:
        if daemonize:
            # The child will be exiting. Wait for it's return code.
            pid, status = os.waitpid(pid, 0)
        return pid
    else:
        _setup_process_environment(chdir, umask, uid, gid)
        _close_and_redirect_fds(stdout, stderr, close_fds, cloexec)

        if prctl != 0 and proc_name:
            _set_proc_name(proc_name)

        # If daemonizing, double fork and exit, so that the child can be
        # re-parented to init.
        if daemonize:
            try:
                pid = os.fork()
            except OSError:
                sys.exit(_perror("Failed to daemonize process"))
            if pid != 0:
                sys.exit(0)

        try:
            atexit.register(_delete_pid_file, pidfile)
            _write_pid_file(pidfile)
            if args and kwargs:
                return_code = func(*args, **kwargs)
            if args:
                return_code = func(*args)
            if kwargs:
                return_code = func(**kwargs)
            else:
                return_code = func()
        except KeyboardInterrupt:
            _delete_pid_file(pidfile)
            sys.exit()
        except:
            _delete_pid_file(pidfile)
            sys.exit(1)
        finally:
            _delete_pid_file(pidfile)

def sleep():
    while True:
        import time
        print "Sleeping"
        time.sleep(10)
