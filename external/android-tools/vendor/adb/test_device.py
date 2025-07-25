#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import print_function

import contextlib
import hashlib
import io
import os
import posixpath
import random
import re
import shlex
import shutil
import signal
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import proto.adb_host_pb2 as adb_host_proto

from datetime import datetime

import adb

def requires_non_root(func):
    def wrapper(self, *args):
        was_root = self.device.shell(['id', '-un'])[0].strip() == 'root'
        if was_root:
            self.device.unroot()
            self.device.wait()

        try:
            func(self, *args)
        finally:
            if was_root:
                self.device.root()
                self.device.wait()

    return wrapper


class DeviceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.device = adb.get_device()


class AbbTest(DeviceTest):
    def test_smoke(self):
        abb = subprocess.run(['adb', 'abb'], capture_output=True)
        cmd = subprocess.run(['adb', 'shell', 'cmd'], capture_output=True)

        # abb squashes all failures to 1.
        self.assertEqual(abb.returncode == 0, cmd.returncode == 0)
        self.assertEqual(abb.stdout, cmd.stdout)
        self.assertEqual(abb.stderr, cmd.stderr)

class ForwardReverseTest(DeviceTest):
    def _test_no_rebind(self, description, direction_list, direction,
                       direction_no_rebind, direction_remove_all):
        msg = direction_list()
        self.assertEqual('', msg.strip(),
                         description + ' list must be empty to run this test.')

        # Use --no-rebind with no existing binding
        direction_no_rebind('tcp:5566', 'tcp:6655')
        msg = direction_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))

        # Use --no-rebind with existing binding
        with self.assertRaises(subprocess.CalledProcessError):
            direction_no_rebind('tcp:5566', 'tcp:6677')
        msg = direction_list()
        self.assertFalse(re.search(r'tcp:5566.+tcp:6677', msg))
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))

        # Use the absence of --no-rebind with existing binding
        direction('tcp:5566', 'tcp:6677')
        msg = direction_list()
        self.assertFalse(re.search(r'tcp:5566.+tcp:6655', msg))
        self.assertTrue(re.search(r'tcp:5566.+tcp:6677', msg))

        direction_remove_all()
        msg = direction_list()
        self.assertEqual('', msg.strip())

    def test_forward_no_rebind(self):
        self._test_no_rebind('forward', self.device.forward_list,
                            self.device.forward, self.device.forward_no_rebind,
                            self.device.forward_remove_all)

    def test_reverse_no_rebind(self):
        self._test_no_rebind('reverse', self.device.reverse_list,
                            self.device.reverse, self.device.reverse_no_rebind,
                            self.device.reverse_remove_all)

    def test_forward(self):
        msg = self.device.forward_list()
        self.assertEqual('', msg.strip(),
                         'Forwarding list must be empty to run this test.')
        self.device.forward('tcp:5566', 'tcp:6655')
        msg = self.device.forward_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))
        self.device.forward('tcp:7788', 'tcp:8877')
        msg = self.device.forward_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))
        self.assertTrue(re.search(r'tcp:7788.+tcp:8877', msg))
        self.device.forward_remove('tcp:5566')
        msg = self.device.forward_list()
        self.assertFalse(re.search(r'tcp:5566.+tcp:6655', msg))
        self.assertTrue(re.search(r'tcp:7788.+tcp:8877', msg))
        self.device.forward_remove_all()
        msg = self.device.forward_list()
        self.assertEqual('', msg.strip())

    def test_forward_old_protocol(self):
        serialno = subprocess.check_output(self.device.adb_cmd + ['get-serialno']).strip()

        msg = self.device.forward_list()
        self.assertEqual('', msg.strip(),
                         'Forwarding list must be empty to run this test.')

        with socket.create_connection(("localhost", 5037)) as s:
            service = b"host-serial:%s:forward:tcp:5566;tcp:6655" % serialno
            cmd = b"%04x%s" % (len(service), service)
            s.sendall(cmd)

        msg = self.device.forward_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))

        self.device.forward_remove_all()
        msg = self.device.forward_list()
        self.assertEqual('', msg.strip())

    def test_forward_tcp_port_0(self):
        self.assertEqual('', self.device.forward_list().strip(),
                         'Forwarding list must be empty to run this test.')

        try:
            # If resolving TCP port 0 is supported, `adb forward` will print
            # the actual port number.
            port = self.device.forward('tcp:0', 'tcp:8888').strip()
            if not port:
                raise unittest.SkipTest('Forwarding tcp:0 is not available.')

            self.assertTrue(re.search(r'tcp:{}.+tcp:8888'.format(port),
                                      self.device.forward_list()))
        finally:
            self.device.forward_remove_all()

    def test_reverse(self):
        msg = self.device.reverse_list()
        self.assertEqual('', msg.strip(),
                         'Reverse forwarding list must be empty to run this test.')
        self.device.reverse('tcp:5566', 'tcp:6655')
        msg = self.device.reverse_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))
        self.device.reverse('tcp:7788', 'tcp:8877')
        msg = self.device.reverse_list()
        self.assertTrue(re.search(r'tcp:5566.+tcp:6655', msg))
        self.assertTrue(re.search(r'tcp:7788.+tcp:8877', msg))
        self.device.reverse_remove('tcp:5566')
        msg = self.device.reverse_list()
        self.assertFalse(re.search(r'tcp:5566.+tcp:6655', msg))
        self.assertTrue(re.search(r'tcp:7788.+tcp:8877', msg))
        self.device.reverse_remove_all()
        msg = self.device.reverse_list()
        self.assertEqual('', msg.strip())

    def test_reverse_tcp_port_0(self):
        self.assertEqual('', self.device.reverse_list().strip(),
                         'Reverse list must be empty to run this test.')

        try:
            # If resolving TCP port 0 is supported, `adb reverse` will print
            # the actual port number.
            port = self.device.reverse('tcp:0', 'tcp:8888').strip()
            if not port:
                raise unittest.SkipTest('Reversing tcp:0 is not available.')

            self.assertTrue(re.search(r'tcp:{}.+tcp:8888'.format(port),
                                      self.device.reverse_list()))
        finally:
            self.device.reverse_remove_all()

    def test_forward_reverse_echo(self):
        """Send data through adb forward and read it back via adb reverse"""
        forward_port = 12345
        reverse_port = forward_port + 1
        forward_spec = 'tcp:' + str(forward_port)
        reverse_spec = 'tcp:' + str(reverse_port)
        forward_setup = False
        reverse_setup = False

        try:
            # listen on localhost:forward_port, connect to remote:forward_port
            self.device.forward(forward_spec, forward_spec)
            forward_setup = True
            # listen on remote:forward_port, connect to localhost:reverse_port
            self.device.reverse(forward_spec, reverse_spec)
            reverse_setup = True

            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with contextlib.closing(listener):
                # Use SO_REUSEADDR so that subsequent runs of the test can grab
                # the port even if it is in TIME_WAIT.
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # Listen on localhost:reverse_port before connecting to
                # localhost:forward_port because that will cause adb to connect
                # back to localhost:reverse_port.
                listener.bind(('127.0.0.1', reverse_port))
                listener.listen(4)

                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                with contextlib.closing(client):
                    # Connect to the listener.
                    client.connect(('127.0.0.1', forward_port))

                    # Accept the client connection.
                    accepted_connection, addr = listener.accept()
                    with contextlib.closing(accepted_connection) as server:
                        data = b'hello'

                        # Send data into the port setup by adb forward.
                        client.sendall(data)
                        # Explicitly close() so that server gets EOF.
                        client.close()

                        # Verify that the data came back via adb reverse.
                        self.assertEqual(data, server.makefile().read().encode("utf8"))
        finally:
            if reverse_setup:
                self.device.reverse_remove(forward_spec)
            if forward_setup:
                self.device.forward_remove(forward_spec)


class ShellTest(DeviceTest):
    def _interactive_shell(self, shell_args, input):
        """Runs an interactive adb shell.

        Args:
          shell_args: List of string arguments to `adb shell`.
          input: bytes input to send to the interactive shell.

        Returns:
          The remote exit code.

        Raises:
          unittest.SkipTest: The device doesn't support exit codes.
        """
        if not self.device.has_shell_protocol():
            raise unittest.SkipTest('exit codes are unavailable on this device')

        proc = subprocess.Popen(
                self.device.adb_cmd + ['shell'] + shell_args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        # Closing host-side stdin doesn't trigger a PTY shell to exit so we need
        # to explicitly add an exit command to close the session from the device
        # side, plus the necessary newline to complete the interactive command.
        proc.communicate(input + b'; exit\n')
        return proc.returncode

    def test_cat(self):
        """Check that we can at least cat a file."""
        out = self.device.shell(['cat', '/proc/uptime'])[0].strip()
        elements = out.split()
        self.assertEqual(len(elements), 2)

        uptime, idle = elements
        self.assertGreater(float(uptime), 0.0)
        self.assertGreater(float(idle), 0.0)

    def test_throws_on_failure(self):
        self.assertRaises(adb.ShellError, self.device.shell, ['false'])

    def test_output_not_stripped(self):
        out = self.device.shell(['echo', 'foo'])[0]
        self.assertEqual(out, 'foo' + self.device.linesep)

    def test_shell_command_length(self):
        # Devices that have shell_v2 should be able to handle long commands.
        if self.device.has_shell_protocol():
            rc, out, err = self.device.shell_nocheck(['echo', 'x' * 16384])
            self.assertEqual(rc, 0)
            self.assertTrue(out == ('x' * 16384 + '\n'))

    def test_shell_nocheck_failure(self):
        rc, out, _ = self.device.shell_nocheck(['false'])
        self.assertNotEqual(rc, 0)
        self.assertEqual(out, '')

    def test_shell_nocheck_output_not_stripped(self):
        rc, out, _ = self.device.shell_nocheck(['echo', 'foo'])
        self.assertEqual(rc, 0)
        self.assertEqual(out, 'foo' + self.device.linesep)

    def test_can_distinguish_tricky_results(self):
        # If result checking on ADB shell is naively implemented as
        # `adb shell <cmd>; echo $?`, we would be unable to distinguish the
        # output from the result for a cmd of `echo -n 1`.
        rc, out, _ = self.device.shell_nocheck(['echo', '-n', '1'])
        self.assertEqual(rc, 0)
        self.assertEqual(out, '1')

    def test_line_endings(self):
        """Ensure that line ending translation is not happening in the pty.

        Bug: http://b/19735063
        """
        output = self.device.shell(['uname'])[0]
        self.assertEqual(output, 'Linux' + self.device.linesep)

    def test_pty_logic(self):
        """Tests that a PTY is allocated when it should be.

        PTY allocation behavior should match ssh.
        """
        def check_pty(args):
            """Checks adb shell PTY allocation.

            Tests |args| for terminal and non-terminal stdin.

            Args:
                args: -Tt args in a list (e.g. ['-t', '-t']).

            Returns:
                A tuple (<terminal>, <non-terminal>). True indicates
                the corresponding shell allocated a remote PTY.
            """
            test_cmd = self.device.adb_cmd + ['shell'] + args + ['[ -t 0 ]']

            terminal = subprocess.Popen(
                    test_cmd, stdin=None,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            terminal.communicate()

            non_terminal = subprocess.Popen(
                    test_cmd, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            non_terminal.communicate()

            return (terminal.returncode == 0, non_terminal.returncode == 0)

        # -T: never allocate PTY.
        self.assertEqual((False, False), check_pty(['-T']))

        # These tests require a new device.
        if self.device.has_shell_protocol() and os.isatty(sys.stdin.fileno()):
            # No args: PTY only if stdin is a terminal and shell is interactive,
            # which is difficult to reliably test from a script.
            self.assertEqual((False, False), check_pty([]))

            # -t: PTY if stdin is a terminal.
            self.assertEqual((True, False), check_pty(['-t']))

        # -t -t: always allocate PTY.
        self.assertEqual((True, True), check_pty(['-t', '-t']))

        # -tt: always allocate PTY, POSIX style (http://b/32216152).
        self.assertEqual((True, True), check_pty(['-tt']))

        # -ttt: ssh has weird even/odd behavior with multiple -t flags, but
        # we follow the man page instead.
        self.assertEqual((True, True), check_pty(['-ttt']))

        # -ttx: -x and -tt aren't incompatible (though -Tx would be an error).
        self.assertEqual((True, True), check_pty(['-ttx']))

        # -Ttt: -tt cancels out -T.
        self.assertEqual((True, True), check_pty(['-Ttt']))

        # -ttT: -T cancels out -tt.
        self.assertEqual((False, False), check_pty(['-ttT']))

    def test_shell_protocol(self):
        """Tests the shell protocol on the device.

        If the device supports shell protocol, this gives us the ability
        to separate stdout/stderr and return the exit code directly.

        Bug: http://b/19734861
        """
        if not self.device.has_shell_protocol():
            raise unittest.SkipTest('shell protocol unsupported on this device')

        # Shell protocol should be used by default.
        result = self.device.shell_nocheck(
                shlex.split('echo foo; echo bar >&2; exit 17'))
        self.assertEqual(17, result[0])
        self.assertEqual('foo' + self.device.linesep, result[1])
        self.assertEqual('bar' + self.device.linesep, result[2])

        self.assertEqual(17, self._interactive_shell([], b'exit 17'))

        # -x flag should disable shell protocol.
        result = self.device.shell_nocheck(
                shlex.split('-x echo foo; echo bar >&2; exit 17'))
        self.assertEqual(0, result[0])
        self.assertEqual('foo{0}bar{0}'.format(self.device.linesep), result[1])
        self.assertEqual('', result[2])

        self.assertEqual(0, self._interactive_shell(['-x'], b'exit 17'))

    def test_non_interactive_sigint(self):
        """Tests that SIGINT in a non-interactive shell kills the process.

        This requires the shell protocol in order to detect the broken
        pipe; raw data transfer mode will only see the break once the
        subprocess tries to read or write.

        Bug: http://b/23825725
        """
        if not self.device.has_shell_protocol():
            raise unittest.SkipTest('shell protocol unsupported on this device')

        # Start a long-running process.
        sleep_proc = subprocess.Popen(
                self.device.adb_cmd + shlex.split('shell echo $$; sleep 60'),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)
        remote_pid = sleep_proc.stdout.readline().strip().decode("utf8")
        self.assertIsNone(sleep_proc.returncode, 'subprocess terminated early')
        proc_query = shlex.split('ps {0} | grep {0}'.format(remote_pid))

        # Verify that the process is running, send signal, verify it stopped.
        self.device.shell(proc_query)
        os.kill(sleep_proc.pid, signal.SIGINT)
        sleep_proc.communicate()

        # It can take some time for the process to receive the signal and die.
        end_time = time.time() + 3
        while self.device.shell_nocheck(proc_query)[0] != 1:
            self.assertFalse(time.time() > end_time,
                             'subprocess failed to terminate in time')

    def test_non_interactive_stdin(self):
        """Tests that non-interactive shells send stdin."""
        if not self.device.has_shell_protocol():
            raise unittest.SkipTest('non-interactive stdin unsupported '
                                    'on this device')

        # Test both small and large inputs.
        small_input = b'foo'
        characters = [c.encode("utf8") for c in string.ascii_letters + string.digits]
        large_input = b'\n'.join(characters)


        for input in (small_input, large_input):
            proc = subprocess.Popen(self.device.adb_cmd + ['shell', 'cat'],
                                    stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate(input)
            self.assertEqual(input.splitlines(), stdout.splitlines())
            self.assertEqual(b'', stderr)

    def test_sighup(self):
        """Ensure that SIGHUP gets sent upon non-interactive ctrl-c"""
        log_path = "/data/local/tmp/adb_signal_test.log"

        # Clear the output file.
        self.device.shell_nocheck(["echo", ">", log_path])

        script = """
            trap "echo SIGINT > {path}; exit 0" SIGINT
            trap "echo SIGHUP > {path}; exit 0" SIGHUP
            echo Waiting
            read
        """.format(path=log_path)

        script = ";".join([x.strip() for x in script.strip().splitlines()])

        with self.device.shell_popen([script], kill_atexit=False,
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE) as process:

            self.assertEqual(b"Waiting\n", process.stdout.readline())
            process.send_signal(signal.SIGINT)
            process.wait()

        # Waiting for the local adb to finish is insufficient, since it hangs
        # up immediately.
        time.sleep(1)

        stdout, _ = self.device.shell(["cat", log_path])
        self.assertEqual(stdout.strip(), "SIGHUP")

    # Temporarily disabled because it seems to cause later instability.
    # http://b/228114748
    def disabled_test_exit_stress(self):
        """Hammer `adb shell exit 42` with multiple threads."""
        thread_count = 48
        result = dict()
        def hammer(thread_idx, thread_count, result):
            success = True
            for i in range(thread_idx, 240, thread_count):
                ret = subprocess.call(['adb', 'shell', 'exit {}'.format(i)])
                if ret != i % 256:
                    success = False
                    break
            result[thread_idx] = success

        threads = []
        for i in range(thread_count):
            thread = threading.Thread(target=hammer, args=(i, thread_count, result))
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
        for i, success in result.items():
            self.assertTrue(success)

    def disabled_test_parallel(self):
        """Spawn a bunch of `adb shell` instances in parallel.

        This was broken historically due to the use of select, which only works
        for fds that are numerically less than 1024.

        Bug: http://b/141955761"""

        n_procs = 2048
        procs = dict()
        for i in range(0, n_procs):
            procs[i] = subprocess.Popen(
                ['adb', 'shell', 'read foo; echo $foo; read rc; exit $rc'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE
            )

        for i in range(0, n_procs):
            procs[i].stdin.write("%d\n" % i)

        for i in range(0, n_procs):
            response = procs[i].stdout.readline()
            assert(response == "%d\n" % i)

        for i in range(0, n_procs):
            procs[i].stdin.write("%d\n" % (i % 256))

        for i in range(0, n_procs):
            assert(procs[i].wait() == i % 256)


class ArgumentEscapingTest(DeviceTest):
    def test_shell_escaping(self):
        """Make sure that argument escaping is somewhat sane."""

        # http://b/19734868
        # Note that this actually matches ssh(1)'s behavior --- it's
        # converted to `sh -c echo hello; echo world` which sh interprets
        # as `sh -c echo` (with an argument to that shell of "hello"),
        # and then `echo world` back in the first shell.
        result = self.device.shell(
            shlex.split("sh -c 'echo hello; echo world'"))[0]
        result = result.splitlines()
        self.assertEqual(['', 'world'], result)
        # If you really wanted "hello" and "world", here's what you'd do:
        result = self.device.shell(
            shlex.split(r'echo hello\;echo world'))[0].splitlines()
        self.assertEqual(['hello', 'world'], result)

        # http://b/15479704
        result = self.device.shell(shlex.split("'true && echo t'"))[0].strip()
        self.assertEqual('t', result)
        result = self.device.shell(
            shlex.split("sh -c 'true && echo t'"))[0].strip()
        self.assertEqual('t', result)

        # http://b/20564385
        result = self.device.shell(shlex.split('FOO=a BAR=b echo t'))[0].strip()
        self.assertEqual('t', result)
        result = self.device.shell(
            shlex.split(r'echo -n 123\;uname'))[0].strip()
        self.assertEqual('123Linux', result)

    def test_install_argument_escaping(self):
        """Make sure that install argument escaping works."""
        # http://b/20323053, http://b/3090932.
        for file_suffix in (b'-text;ls;1.apk', b"-Live Hold'em.apk"):
            tf = tempfile.NamedTemporaryFile('wb', suffix=file_suffix,
                                             delete=False)
            tf.close()

            # Installing bogus .apks fails if the device supports exit codes.
            try:
                output = self.device.install(tf.name.decode("utf8"))
            except subprocess.CalledProcessError as e:
                output = e.output

            self.assertIn(file_suffix, output)
            os.remove(tf.name)


class RootUnrootTest(DeviceTest):
    def _test_root(self):
        message = self.device.root()
        if 'adbd cannot run as root in production builds' in message:
            return
        self.device.wait()
        self.assertEqual('root', self.device.shell(['id', '-un'])[0].strip())

    def _test_unroot(self):
        self.device.unroot()
        self.device.wait()
        self.assertEqual('shell', self.device.shell(['id', '-un'])[0].strip())

    def test_root_unroot(self):
        """Make sure that adb root and adb unroot work, using id(1)."""
        if self.device.get_prop('ro.debuggable') != '1':
            raise unittest.SkipTest('requires rootable build')

        original_user = self.device.shell(['id', '-un'])[0].strip()
        try:
            if original_user == 'root':
                self._test_unroot()
                self._test_root()
            elif original_user == 'shell':
                self._test_root()
                self._test_unroot()
        finally:
            if original_user == 'root':
                self.device.root()
            else:
                self.device.unroot()
            self.device.wait()


class TcpIpTest(DeviceTest):
    def test_tcpip_failure_raises(self):
        """adb tcpip requires a port.

        Bug: http://b/22636927
        """
        self.assertRaises(
            subprocess.CalledProcessError, self.device.tcpip, '')
        self.assertRaises(
            subprocess.CalledProcessError, self.device.tcpip, 'foo')


class SystemPropertiesTest(DeviceTest):
    def test_get_prop(self):
        self.assertEqual(self.device.get_prop('init.svc.adbd'), 'running')

    def test_set_prop(self):
        # debug.* prop does not require root privileges
        prop_name = 'debug.foo'
        self.device.shell(['setprop', prop_name, '""'])

        val = random.random()
        self.device.set_prop(prop_name, str(val))
        self.assertEqual(
            self.device.shell(['getprop', prop_name])[0].strip(), str(val))


def compute_md5(string):
    hsh = hashlib.md5()
    hsh.update(string)
    return hsh.hexdigest()


class HostFile(object):
    def __init__(self, handle, checksum):
        self.handle = handle
        self.checksum = checksum
        self.full_path = handle.name
        self.base_name = os.path.basename(self.full_path)


class DeviceFile(object):
    def __init__(self, checksum, full_path):
        self.checksum = checksum
        self.full_path = full_path
        self.base_name = posixpath.basename(self.full_path)


def make_random_host_files(in_dir, num_files):
    min_size = 1 * (1 << 10)
    max_size = 16 * (1 << 10)

    files = []
    for _ in range(num_files):
        file_handle = tempfile.NamedTemporaryFile(dir=in_dir, delete=False)

        size = random.randrange(min_size, max_size, 1024)
        rand_str = os.urandom(size)
        file_handle.write(rand_str)
        file_handle.flush()
        file_handle.close()

        md5 = compute_md5(rand_str)
        files.append(HostFile(file_handle, md5))
    return files


def make_random_device_files(device, in_dir, num_files, prefix='device_tmpfile'):
    min_size = 1 * (1 << 10)
    max_size = 16 * (1 << 10)

    files = []
    for file_num in range(num_files):
        size = random.randrange(min_size, max_size, 1024)

        base_name = prefix + str(file_num)
        full_path = posixpath.join(in_dir, base_name)

        device.shell(['dd', 'if=/dev/urandom', 'of={}'.format(full_path),
                      'bs={}'.format(size), 'count=1'])
        dev_md5, _ = device.shell(['md5sum', full_path])[0].split()

        files.append(DeviceFile(dev_md5, full_path))
    return files


class FileOperationsTest:
    class Base(DeviceTest):
        SCRATCH_DIR = '/data/local/tmp'
        DEVICE_TEMP_FILE = SCRATCH_DIR + '/adb_test_file'
        DEVICE_TEMP_DIR = SCRATCH_DIR + '/adb_test_dir'

        def setUp(self):
            super().setUp()
            self.previous_env = os.environ.get("ADB_COMPRESSION")
            os.environ["ADB_COMPRESSION"] = self.compression

        def tearDown(self):
            if self.previous_env is None:
                del os.environ["ADB_COMPRESSION"]
            else:
                os.environ["ADB_COMPRESSION"] = self.previous_env

        def _verify_remote(self, checksum, remote_path):
            dev_md5, _ = self.device.shell(['md5sum', remote_path])[0].split()
            self.assertEqual(checksum, dev_md5)

        def _verify_local(self, checksum, local_path):
            with open(local_path, 'rb') as host_file:
                host_md5 = compute_md5(host_file.read())
                self.assertEqual(host_md5, checksum)

        def test_push(self):
            """Push a randomly generated file to specified device."""
            kbytes = 512
            tmp = tempfile.NamedTemporaryFile(mode='wb', delete=False)
            rand_str = os.urandom(1024 * kbytes)
            tmp.write(rand_str)
            tmp.close()

            self.device.shell(['rm', '-rf', self.DEVICE_TEMP_FILE])
            self.device.push(local=tmp.name, remote=self.DEVICE_TEMP_FILE)

            self._verify_remote(compute_md5(rand_str), self.DEVICE_TEMP_FILE)
            self.device.shell(['rm', '-f', self.DEVICE_TEMP_FILE])

            os.remove(tmp.name)

        def test_push_dir(self):
            """Push a randomly generated directory of files to the device."""
            self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            self.device.shell(['mkdir', self.DEVICE_TEMP_DIR])

            try:
                host_dir = tempfile.mkdtemp()

                # Make sure the temp directory isn't setuid, or else adb will complain.
                os.chmod(host_dir, 0o700)

                # Create 32 random files.
                temp_files = make_random_host_files(in_dir=host_dir, num_files=32)
                self.device.push(host_dir, self.DEVICE_TEMP_DIR)

                for temp_file in temp_files:
                    remote_path = posixpath.join(self.DEVICE_TEMP_DIR,
                                                 os.path.basename(host_dir),
                                                 temp_file.base_name)
                    self._verify_remote(temp_file.checksum, remote_path)
                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def disabled_test_push_empty(self):
            """Push an empty directory to the device."""
            self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            self.device.shell(['mkdir', self.DEVICE_TEMP_DIR])

            try:
                host_dir = tempfile.mkdtemp()

                # Make sure the temp directory isn't setuid, or else adb will complain.
                os.chmod(host_dir, 0o700)

                # Create an empty directory.
                empty_dir_path = os.path.join(host_dir, 'empty')
                os.mkdir(empty_dir_path);

                self.device.push(empty_dir_path, self.DEVICE_TEMP_DIR)

                remote_path = os.path.join(self.DEVICE_TEMP_DIR, "empty")
                test_empty_cmd = ["[", "-d", remote_path, "]"]
                rc, _, _ = self.device.shell_nocheck(test_empty_cmd)

                self.assertEqual(rc, 0)
                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        @unittest.skipIf(sys.platform == "win32", "symlinks require elevated privileges on windows")
        def test_push_symlink(self):
            """Push a symlink.

            Bug: http://b/31491920
            """
            try:
                host_dir = tempfile.mkdtemp()

                # Make sure the temp directory isn't setuid, or else adb will
                # complain.
                os.chmod(host_dir, 0o700)

                with open(os.path.join(host_dir, 'foo'), 'w') as f:
                    f.write('foo')

                symlink_path = os.path.join(host_dir, 'symlink')
                os.symlink('foo', symlink_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', self.DEVICE_TEMP_DIR])
                self.device.push(symlink_path, self.DEVICE_TEMP_DIR)
                rc, out, _ = self.device.shell_nocheck(
                    ['cat', posixpath.join(self.DEVICE_TEMP_DIR, 'symlink')])
                self.assertEqual(0, rc)
                self.assertEqual(out.strip(), 'foo')
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_multiple_push(self):
            """Push multiple files to the device in one adb push command.

            Bug: http://b/25324823
            """

            self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            self.device.shell(['mkdir', self.DEVICE_TEMP_DIR])

            try:
                host_dir = tempfile.mkdtemp()

                # Create some random files and a subdirectory containing more files.
                temp_files = make_random_host_files(in_dir=host_dir, num_files=4)

                subdir = os.path.join(host_dir, 'subdir')
                os.mkdir(subdir)
                subdir_temp_files = make_random_host_files(in_dir=subdir,
                                                           num_files=4)

                paths = [x.full_path for x in temp_files]
                paths.append(subdir)
                self.device._simple_call(['push'] + paths + [self.DEVICE_TEMP_DIR])

                for temp_file in temp_files:
                    remote_path = posixpath.join(self.DEVICE_TEMP_DIR,
                                                 temp_file.base_name)
                    self._verify_remote(temp_file.checksum, remote_path)

                for subdir_temp_file in subdir_temp_files:
                    remote_path = posixpath.join(self.DEVICE_TEMP_DIR,
                                                 # BROKEN: http://b/25394682
                                                 # 'subdir';
                                                 temp_file.base_name)
                    self._verify_remote(temp_file.checksum, remote_path)


                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        @requires_non_root
        def test_push_error_reporting(self):
            """Make sure that errors that occur while pushing a file get reported

            Bug: http://b/26816782
            """
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(b'\0' * 1024 * 1024)
                tmp_file.flush()
                try:
                    self.device.push(local=tmp_file.name, remote='/system/')
                    self.fail('push should not have succeeded')
                except subprocess.CalledProcessError as e:
                    output = e.output

                self.assertTrue(b'Permission denied' in output or
                                b'Read-only file system' in output)

        @requires_non_root
        def test_push_directory_creation(self):
            """Regression test for directory creation.

            Bug: http://b/110953234
            """
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(b'\0' * 1024 * 1024)
                tmp_file.flush()
                remote_path = self.DEVICE_TEMP_DIR + '/test_push_directory_creation'
                self.device.shell(['rm', '-rf', remote_path])

                remote_path += '/filename'
                self.device.push(local=tmp_file.name, remote=remote_path)

        def disabled_test_push_multiple_slash_root(self):
            """Regression test for pushing to //data/local/tmp.

            Bug: http://b/141311284

            Disabled because this broken on the adbd side as well: b/141943968
            """
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(b'\0' * 1024 * 1024)
                tmp_file.flush()
                remote_path = '/' + self.DEVICE_TEMP_DIR + '/test_push_multiple_slash_root'
                self.device.shell(['rm', '-rf', remote_path])
                self.device.push(local=tmp_file.name, remote=remote_path)

        def _test_pull(self, remote_file, checksum):
            tmp_write = tempfile.NamedTemporaryFile(mode='wb', delete=False)
            tmp_write.close()
            self.device.pull(remote=remote_file, local=tmp_write.name)
            with open(tmp_write.name, 'rb') as tmp_read:
                host_contents = tmp_read.read()
                host_md5 = compute_md5(host_contents)
            self.assertEqual(checksum, host_md5)
            os.remove(tmp_write.name)

        @requires_non_root
        def test_pull_error_reporting(self):
            self.device.shell(['touch', self.DEVICE_TEMP_FILE])
            self.device.shell(['chmod', 'a-rwx', self.DEVICE_TEMP_FILE])

            try:
                output = self.device.pull(remote=self.DEVICE_TEMP_FILE, local='x')
            except subprocess.CalledProcessError as e:
                output = e.output

            self.assertIn(b'Permission denied', output)

            self.device.shell(['rm', '-f', self.DEVICE_TEMP_FILE])

        def test_pull(self):
            """Pull a randomly generated file from specified device."""
            kbytes = 512
            self.device.shell(['rm', '-rf', self.DEVICE_TEMP_FILE])
            cmd = ['dd', 'if=/dev/urandom',
                   'of={}'.format(self.DEVICE_TEMP_FILE), 'bs=1024',
                   'count={}'.format(kbytes)]
            self.device.shell(cmd)
            dev_md5, _ = self.device.shell(['md5sum', self.DEVICE_TEMP_FILE])[0].split()
            self._test_pull(self.DEVICE_TEMP_FILE, dev_md5)
            self.device.shell_nocheck(['rm', self.DEVICE_TEMP_FILE])

        def test_pull_dir(self):
            """Pull a randomly generated directory of files from the device."""
            try:
                host_dir = tempfile.mkdtemp()

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', self.DEVICE_TEMP_DIR])

                # Populate device directory with random files.
                temp_files = make_random_device_files(
                    self.device, in_dir=self.DEVICE_TEMP_DIR, num_files=32)

                self.device.pull(remote=self.DEVICE_TEMP_DIR, local=host_dir)

                for temp_file in temp_files:
                    host_path = os.path.join(
                        host_dir, posixpath.basename(self.DEVICE_TEMP_DIR),
                        temp_file.base_name)
                    self._verify_local(temp_file.checksum, host_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_pull_dir_symlink(self):
            """Pull a directory into a symlink to a directory.

            Bug: http://b/27362811
            """
            if os.name != 'posix':
                raise unittest.SkipTest('requires POSIX')

            try:
                host_dir = tempfile.mkdtemp()
                real_dir = os.path.join(host_dir, 'dir')
                symlink = os.path.join(host_dir, 'symlink')
                os.mkdir(real_dir)
                os.symlink(real_dir, symlink)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', self.DEVICE_TEMP_DIR])

                # Populate device directory with random files.
                temp_files = make_random_device_files(
                    self.device, in_dir=self.DEVICE_TEMP_DIR, num_files=32)

                self.device.pull(remote=self.DEVICE_TEMP_DIR, local=symlink)

                for temp_file in temp_files:
                    host_path = os.path.join(
                        real_dir, posixpath.basename(self.DEVICE_TEMP_DIR),
                        temp_file.base_name)
                    self._verify_local(temp_file.checksum, host_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_pull_dir_symlink_collision(self):
            """Pull a directory into a colliding symlink to directory."""
            if os.name != 'posix':
                raise unittest.SkipTest('requires POSIX')

            try:
                host_dir = tempfile.mkdtemp()
                real_dir = os.path.join(host_dir, 'real')
                tmp_dirname = os.path.basename(self.DEVICE_TEMP_DIR)
                symlink = os.path.join(host_dir, tmp_dirname)
                os.mkdir(real_dir)
                os.symlink(real_dir, symlink)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', self.DEVICE_TEMP_DIR])

                # Populate device directory with random files.
                temp_files = make_random_device_files(
                    self.device, in_dir=self.DEVICE_TEMP_DIR, num_files=32)

                self.device.pull(remote=self.DEVICE_TEMP_DIR, local=host_dir)

                for temp_file in temp_files:
                    host_path = os.path.join(real_dir, temp_file.base_name)
                    self._verify_local(temp_file.checksum, host_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_pull_dir_nonexistent(self):
            """Pull a directory of files from the device to a nonexistent path."""
            try:
                host_dir = tempfile.mkdtemp()
                dest_dir = os.path.join(host_dir, 'dest')

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', self.DEVICE_TEMP_DIR])

                # Populate device directory with random files.
                temp_files = make_random_device_files(
                    self.device, in_dir=self.DEVICE_TEMP_DIR, num_files=32)

                self.device.pull(remote=self.DEVICE_TEMP_DIR, local=dest_dir)

                for temp_file in temp_files:
                    host_path = os.path.join(dest_dir, temp_file.base_name)
                    self._verify_local(temp_file.checksum, host_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        # selinux prevents adbd from accessing symlinks on /data/local/tmp.
        def disabled_test_pull_symlink_dir(self):
            """Pull a symlink to a directory of symlinks to files."""
            try:
                host_dir = tempfile.mkdtemp()

                remote_dir = posixpath.join(self.DEVICE_TEMP_DIR, 'contents')
                remote_links = posixpath.join(self.DEVICE_TEMP_DIR, 'links')
                remote_symlink = posixpath.join(self.DEVICE_TEMP_DIR, 'symlink')

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', remote_dir, remote_links])
                self.device.shell(['ln', '-s', remote_links, remote_symlink])

                # Populate device directory with random files.
                temp_files = make_random_device_files(
                    self.device, in_dir=remote_dir, num_files=32)

                for temp_file in temp_files:
                    self.device.shell(
                        ['ln', '-s', '../contents/{}'.format(temp_file.base_name),
                         posixpath.join(remote_links, temp_file.base_name)])

                self.device.pull(remote=remote_symlink, local=host_dir)

                for temp_file in temp_files:
                    host_path = os.path.join(
                        host_dir, 'symlink', temp_file.base_name)
                    self._verify_local(temp_file.checksum, host_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_pull_empty(self):
            """Pull a directory containing an empty directory from the device."""
            try:
                host_dir = tempfile.mkdtemp()

                remote_empty_path = posixpath.join(self.DEVICE_TEMP_DIR, 'empty')
                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', remote_empty_path])

                self.device.pull(remote=remote_empty_path, local=host_dir)
                self.assertTrue(os.path.isdir(os.path.join(host_dir, 'empty')))
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def test_multiple_pull(self):
            """Pull a randomly generated directory of files from the device."""

            try:
                host_dir = tempfile.mkdtemp()

                subdir = posixpath.join(self.DEVICE_TEMP_DIR, 'subdir')
                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                self.device.shell(['mkdir', '-p', subdir])

                # Create some random files and a subdirectory containing more files.
                temp_files = make_random_device_files(
                    self.device, in_dir=self.DEVICE_TEMP_DIR, num_files=4)

                subdir_temp_files = make_random_device_files(
                    self.device, in_dir=subdir, num_files=4, prefix='subdir_')

                paths = [x.full_path for x in temp_files]
                paths.append(subdir)
                self.device._simple_call(['pull'] + paths + [host_dir])

                for temp_file in temp_files:
                    local_path = os.path.join(host_dir, temp_file.base_name)
                    self._verify_local(temp_file.checksum, local_path)

                for subdir_temp_file in subdir_temp_files:
                    local_path = os.path.join(host_dir,
                                              'subdir',
                                              subdir_temp_file.base_name)
                    self._verify_local(subdir_temp_file.checksum, local_path)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if host_dir is not None:
                    shutil.rmtree(host_dir)

        def verify_sync(self, device, temp_files, device_dir):
            """Verifies that a list of temp files was synced to the device."""
            # Confirm that every file on the device mirrors that on the host.
            for temp_file in temp_files:
                device_full_path = posixpath.join(
                    device_dir, temp_file.base_name)
                dev_md5, _ = device.shell(['md5sum', device_full_path])[0].split()
                self.assertEqual(temp_file.checksum, dev_md5)

        def test_sync(self):
            """Sync a host directory to the data partition."""

            try:
                base_dir = tempfile.mkdtemp()

                # Create mirror device directory hierarchy within base_dir.
                full_dir_path = base_dir + self.DEVICE_TEMP_DIR
                os.makedirs(full_dir_path)

                # Create 32 random files within the host mirror.
                temp_files = make_random_host_files(
                    in_dir=full_dir_path, num_files=32)

                # Clean up any stale files on the device.
                device = adb.get_device()  # pylint: disable=no-member
                device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])

                old_product_out = os.environ.get('ANDROID_PRODUCT_OUT')
                os.environ['ANDROID_PRODUCT_OUT'] = base_dir
                device.sync('data')
                if old_product_out is None:
                    del os.environ['ANDROID_PRODUCT_OUT']
                else:
                    os.environ['ANDROID_PRODUCT_OUT'] = old_product_out

                self.verify_sync(device, temp_files, self.DEVICE_TEMP_DIR)

                #self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if base_dir is not None:
                    shutil.rmtree(base_dir)

        def test_push_sync(self):
            """Sync a host directory to a specific path."""

            try:
                temp_dir = tempfile.mkdtemp()
                temp_files = make_random_host_files(in_dir=temp_dir, num_files=32)

                device_dir = posixpath.join(self.DEVICE_TEMP_DIR, 'sync_src_dst')

                # Clean up any stale files on the device.
                device = adb.get_device()  # pylint: disable=no-member
                device.shell(['rm', '-rf', device_dir])

                device.push(temp_dir, device_dir, sync=True)

                self.verify_sync(device, temp_files, device_dir)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir)

        def test_push_sync_multiple(self):
            """Sync multiple host directories to a specific path."""

            try:
                temp_dir = tempfile.mkdtemp()
                temp_files = make_random_host_files(in_dir=temp_dir, num_files=32)

                device_dir = posixpath.join(self.DEVICE_TEMP_DIR, 'sync_src_dst')

                # Clean up any stale files on the device.
                device = adb.get_device()  # pylint: disable=no-member
                device.shell(['rm', '-rf', device_dir])
                device.shell(['mkdir', '-p', device_dir])

                host_paths = [os.path.join(temp_dir, x.base_name) for x in temp_files]
                device.push(host_paths, device_dir, sync=True)

                self.verify_sync(device, temp_files, device_dir)

                self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
            finally:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir)


        def test_push_dry_run_nonexistent_file(self):
            """Push with dry run (non-existent file)."""

            for file_size in [8, 1024 * 1024]:
                try:
                    device_dir = posixpath.join(self.DEVICE_TEMP_DIR, 'push_dry_run')
                    device_file = posixpath.join(device_dir, 'file')

                    self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                    self.device.shell(['mkdir', '-p', device_dir])

                    host_dir = tempfile.mkdtemp()
                    host_file = posixpath.join(host_dir, 'file')

                    with open(host_file, "w") as f:
                        f.write('x' * file_size)

                    self.device._simple_call(['push', '-n', host_file, device_file])
                    rc, _, _ = self.device.shell_nocheck(['[', '-e', device_file, ']'])
                    self.assertNotEqual(0, rc)

                    self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                finally:
                    if host_dir is not None:
                        shutil.rmtree(host_dir)

        def test_push_dry_run_existent_file(self):
            """Push with dry run."""

            for file_size in [8, 1024 * 1024]:
                try:
                    host_dir = tempfile.mkdtemp()
                    device_dir = posixpath.join(self.DEVICE_TEMP_DIR, 'push_dry_run')
                    device_file = posixpath.join(device_dir, 'file')

                    self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                    self.device.shell(['mkdir', '-p', device_dir])
                    self.device.shell(['echo', 'foo', '>', device_file])

                    host_file = posixpath.join(host_dir, 'file')

                    with open(host_file, "w") as f:
                        f.write('x' * file_size)

                    self.device._simple_call(['push', '-n', host_file, device_file])
                    stdout, stderr = self.device.shell(['cat', device_file])
                    self.assertEqual(stdout.strip(), "foo")

                    self.device.shell(['rm', '-rf', self.DEVICE_TEMP_DIR])
                finally:
                    if host_dir is not None:
                        shutil.rmtree(host_dir)

        def test_unicode_paths(self):
            """Ensure that we can support non-ASCII paths, even on Windows."""
            name = u'로보카 폴리'

            self.device.shell(['rm', '-f', '/data/local/tmp/adb-test-*'])
            remote_path = u'/data/local/tmp/adb-test-{}'.format(name)

            ## push.
            tf = tempfile.NamedTemporaryFile('wb', suffix=name, delete=False)
            tf.close()
            self.device.push(tf.name, remote_path)
            os.remove(tf.name)
            self.assertFalse(os.path.exists(tf.name))

            # Verify that the device ended up with the expected UTF-8 path
            output = self.device.shell(
                    ['ls', '/data/local/tmp/adb-test-*'])[0].strip()
            self.assertEqual(remote_path, output)

            # pull.
            self.device.pull(remote_path, tf.name)
            self.assertTrue(os.path.exists(tf.name))
            os.remove(tf.name)
            self.device.shell(['rm', '-f', '/data/local/tmp/adb-test-*'])


class FileOperationsTestUncompressed(FileOperationsTest.Base):
    compression = "none"


class FileOperationsTestBrotli(FileOperationsTest.Base):
    compression = "brotli"


class FileOperationsTestLZ4(FileOperationsTest.Base):
    compression = "lz4"


class FileOperationsTestZstd(FileOperationsTest.Base):
    compression = "zstd"


class DeviceOfflineTest(DeviceTest):
    def _get_device_state(self, serialno):
        output = subprocess.check_output(self.device.adb_cmd + ['devices'])
        for line in output.split('\n'):
            m = re.match('(\S+)\s+(\S+)', line)
            if m and m.group(1) == serialno:
                return m.group(2)
        return None

    def disabled_test_killed_when_pushing_a_large_file(self):
        """
           While running adb push with a large file, kill adb server.
           Occasionally the device becomes offline. Because the device is still
           reading data without realizing that the adb server has been restarted.
           Test if we can bring the device online automatically now.
           http://b/32952319
        """
        serialno = subprocess.check_output(self.device.adb_cmd + ['get-serialno']).strip()
        # 1. Push a large file
        file_path = 'tmp_large_file'
        try:
            fh = open(file_path, 'w')
            fh.write('\0' * (100 * 1024 * 1024))
            fh.close()
            subproc = subprocess.Popen(self.device.adb_cmd + ['push', file_path, '/data/local/tmp'])
            time.sleep(0.1)
            # 2. Kill the adb server
            subprocess.check_call(self.device.adb_cmd + ['kill-server'])
            subproc.terminate()
        finally:
            try:
                os.unlink(file_path)
            except:
                pass
        # 3. See if the device still exist.
        # Sleep to wait for the adb server exit.
        time.sleep(0.5)
        # 4. The device should be online
        self.assertEqual(self._get_device_state(serialno), 'device')

    def disabled_test_killed_when_pulling_a_large_file(self):
        """
           While running adb pull with a large file, kill adb server.
           Occasionally the device can't be connected. Because the device is trying to
           send a message larger than what is expected by the adb server.
           Test if we can bring the device online automatically now.
        """
        serialno = subprocess.check_output(self.device.adb_cmd + ['get-serialno']).strip()
        file_path = 'tmp_large_file'
        try:
            # 1. Create a large file on device.
            self.device.shell(['dd', 'if=/dev/zero', 'of=/data/local/tmp/tmp_large_file',
                               'bs=1000000', 'count=100'])
            # 2. Pull the large file on host.
            subproc = subprocess.Popen(self.device.adb_cmd +
                                       ['pull','/data/local/tmp/tmp_large_file', file_path])
            time.sleep(0.1)
            # 3. Kill the adb server
            subprocess.check_call(self.device.adb_cmd + ['kill-server'])
            subproc.terminate()
        finally:
            try:
                os.unlink(file_path)
            except:
                pass
        # 4. See if the device still exist.
        # Sleep to wait for the adb server exit.
        time.sleep(0.5)
        self.assertEqual(self._get_device_state(serialno), 'device')


    def test_packet_size_regression(self):
        """Test for http://b/37783561

        Receiving packets of a length divisible by 512 but not 1024 resulted in
        the adb client waiting indefinitely for more input.
        """
        # The values that trigger things are 507 (512 - 5 bytes from shell protocol) + 1024*n
        # Probe some surrounding values as well, for the hell of it.
        for base in [512] + list(range(1024, 1024 * 16, 1024)):
            for offset in [-6, -5, -4]:
                length = base + offset
                cmd = ['dd', 'if=/dev/zero', 'bs={}'.format(length), 'count=1', '2>/dev/null;'
                       'echo', 'foo']
                rc, stdout, _ = self.device.shell_nocheck(cmd)

                self.assertEqual(0, rc)

                # Output should be '\0' * length, followed by "foo\n"
                self.assertEqual(length, len(stdout) - 4)
                self.assertEqual(stdout, "\0" * length + "foo\n")

    def test_zero_packet(self):
        """Test for http://b/113070258

        Make sure that we don't blow up when sending USB transfers that line up
        exactly with the USB packet size.
        """

        local_port = int(self.device.forward("tcp:0", "tcp:12345"))
        try:
            for size in [512, 1024]:
                def listener():
                    cmd = ["echo foo | nc -l -p 12345; echo done"]
                    rc, stdout, stderr = self.device.shell_nocheck(cmd)

                thread = threading.Thread(target=listener)
                thread.start()

                # Wait a bit to let the shell command start.
                time.sleep(0.25)

                sock = socket.create_connection(("localhost", local_port))
                with contextlib.closing(sock):
                    bytesWritten = sock.send(b"a" * size)
                    self.assertEqual(size, bytesWritten)
                    readBytes = sock.recv(4096)
                    self.assertEqual(b"foo\n", readBytes)

                thread.join()
        finally:
            self.device.forward_remove("tcp:{}".format(local_port))


class SocketTest(DeviceTest):
    def test_socket_flush(self):
        """Test that we handle socket closure properly.

        If we're done writing to a socket, closing before the other end has
        closed will send a TCP_RST if we have incoming data queued up, which
        may result in data that we've written being discarded.

        Bug: http://b/74616284
        """
        def adb_length_prefixed(string):
            encoded = string.encode("utf8")
            result = b"%04x%s" % (len(encoded), encoded)
            return result

        if "ANDROID_SERIAL" in os.environ:
            transport_string = "host:transport:" + os.environ["ANDROID_SERIAL"]
        else:
            transport_string = "host:transport-any"

        with socket.create_connection(("localhost", 5037)) as s:

            s.sendall(adb_length_prefixed(transport_string))
            response = s.recv(4)
            self.assertEqual(b"OKAY", response)

            shell_string = "shell:sleep 0.5; dd if=/dev/zero bs=1m count=1 status=none; echo foo"
            s.sendall(adb_length_prefixed(shell_string))

            response = s.recv(4)
            self.assertEqual(b"OKAY", response)

            # Spawn a thread that dumps garbage into the socket until failure.
            def spam():
                buf = b"\0" * 16384
                try:
                    while True:
                        s.sendall(buf)
                except Exception as ex:
                    print(ex)

            thread = threading.Thread(target=spam)
            thread.start()

            time.sleep(1)

            received = b""
            while True:
                read = s.recv(512)
                if len(read) == 0:
                    break
                received += read

        self.assertEqual(1024 * 1024 + len("foo\n"), len(received))
        thread.join()


class FramebufferTest(DeviceTest):
    def test_framebuffer(self):
        """Test that we get something from the framebuffer service."""
        output = subprocess.check_output(self.device.adb_cmd + ["raw", "framebuffer:"])
        self.assertFalse(len(output) == 0)


if sys.platform == "win32":
    # From https://stackoverflow.com/a/38749458
    import os
    import contextlib
    import msvcrt
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    GENERIC_READ  = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ  = 1
    FILE_SHARE_WRITE = 2
    CONSOLE_TEXTMODE_BUFFER = 1
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    STD_OUTPUT_HANDLE = wintypes.DWORD(-11)
    STD_ERROR_HANDLE = wintypes.DWORD(-12)

    def _check_zero(result, func, args):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return args

    def _check_invalid(result, func, args):
        if result == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return args

    if not hasattr(wintypes, 'LPDWORD'): # Python 2
        wintypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)
        wintypes.PSMALL_RECT = ctypes.POINTER(wintypes.SMALL_RECT)

    class COORD(ctypes.Structure):
        _fields_ = (('X', wintypes.SHORT),
                    ('Y', wintypes.SHORT))

    class CONSOLE_SCREEN_BUFFER_INFOEX(ctypes.Structure):
        _fields_ = (('cbSize',               wintypes.ULONG),
                    ('dwSize',               COORD),
                    ('dwCursorPosition',     COORD),
                    ('wAttributes',          wintypes.WORD),
                    ('srWindow',             wintypes.SMALL_RECT),
                    ('dwMaximumWindowSize',  COORD),
                    ('wPopupAttributes',     wintypes.WORD),
                    ('bFullscreenSupported', wintypes.BOOL),
                    ('ColorTable',           wintypes.DWORD * 16))
        def __init__(self, *args, **kwds):
            super(CONSOLE_SCREEN_BUFFER_INFOEX, self).__init__(
                    *args, **kwds)
            self.cbSize = ctypes.sizeof(self)

    PCONSOLE_SCREEN_BUFFER_INFOEX = ctypes.POINTER(
                                        CONSOLE_SCREEN_BUFFER_INFOEX)
    LPSECURITY_ATTRIBUTES = wintypes.LPVOID

    kernel32.GetStdHandle.errcheck = _check_invalid
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetStdHandle.argtypes = (
        wintypes.DWORD,) # _In_ nStdHandle

    kernel32.CreateConsoleScreenBuffer.errcheck = _check_invalid
    kernel32.CreateConsoleScreenBuffer.restype = wintypes.HANDLE
    kernel32.CreateConsoleScreenBuffer.argtypes = (
        wintypes.DWORD,        # _In_       dwDesiredAccess
        wintypes.DWORD,        # _In_       dwShareMode
        LPSECURITY_ATTRIBUTES, # _In_opt_   lpSecurityAttributes
        wintypes.DWORD,        # _In_       dwFlags
        wintypes.LPVOID)       # _Reserved_ lpScreenBufferData

    kernel32.GetConsoleScreenBufferInfoEx.errcheck = _check_zero
    kernel32.GetConsoleScreenBufferInfoEx.argtypes = (
        wintypes.HANDLE,               # _In_  hConsoleOutput
        PCONSOLE_SCREEN_BUFFER_INFOEX) # _Out_ lpConsoleScreenBufferInfo

    kernel32.SetConsoleScreenBufferInfoEx.errcheck = _check_zero
    kernel32.SetConsoleScreenBufferInfoEx.argtypes = (
        wintypes.HANDLE,               # _In_  hConsoleOutput
        PCONSOLE_SCREEN_BUFFER_INFOEX) # _In_  lpConsoleScreenBufferInfo

    kernel32.SetConsoleWindowInfo.errcheck = _check_zero
    kernel32.SetConsoleWindowInfo.argtypes = (
        wintypes.HANDLE,      # _In_ hConsoleOutput
        wintypes.BOOL,        # _In_ bAbsolute
        wintypes.PSMALL_RECT) # _In_ lpConsoleWindow

    kernel32.FillConsoleOutputCharacterW.errcheck = _check_zero
    kernel32.FillConsoleOutputCharacterW.argtypes = (
        wintypes.HANDLE,  # _In_  hConsoleOutput
        wintypes.WCHAR,   # _In_  cCharacter
        wintypes.DWORD,   # _In_  nLength
        COORD,            # _In_  dwWriteCoord
        wintypes.LPDWORD) # _Out_ lpNumberOfCharsWritten

    kernel32.ReadConsoleOutputCharacterW.errcheck = _check_zero
    kernel32.ReadConsoleOutputCharacterW.argtypes = (
        wintypes.HANDLE,  # _In_  hConsoleOutput
        wintypes.LPWSTR,  # _Out_ lpCharacter
        wintypes.DWORD,   # _In_  nLength
        COORD,            # _In_  dwReadCoord
        wintypes.LPDWORD) # _Out_ lpNumberOfCharsRead

    @contextlib.contextmanager
    def allocate_console():
        allocated = kernel32.AllocConsole()
        try:
            yield allocated
        finally:
            if allocated:
                kernel32.FreeConsole()

    @contextlib.contextmanager
    def console_screen(ncols=None, nrows=None):
        info = CONSOLE_SCREEN_BUFFER_INFOEX()
        new_info = CONSOLE_SCREEN_BUFFER_INFOEX()
        nwritten = (wintypes.DWORD * 1)()
        hStdOut = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        kernel32.GetConsoleScreenBufferInfoEx(
               hStdOut, ctypes.byref(info))
        if ncols is None:
            ncols = info.dwSize.X
        if nrows is None:
            nrows = info.dwSize.Y
        elif nrows > 9999:
            raise ValueError('nrows must be 9999 or less')
        fd_screen = None
        hScreen = kernel32.CreateConsoleScreenBuffer(
                    GENERIC_READ | GENERIC_WRITE,
                    FILE_SHARE_READ | FILE_SHARE_WRITE,
                    None, CONSOLE_TEXTMODE_BUFFER, None)
        try:
            fd_screen = msvcrt.open_osfhandle(
                            hScreen, os.O_RDWR | os.O_BINARY)
            kernel32.GetConsoleScreenBufferInfoEx(
                   hScreen, ctypes.byref(new_info))
            new_info.dwSize = COORD(ncols, nrows)
            new_info.srWindow = wintypes.SMALL_RECT(
                    Left=0, Top=0, Right=(ncols - 1),
                    Bottom=(info.srWindow.Bottom - info.srWindow.Top))
            kernel32.SetConsoleScreenBufferInfoEx(
                    hScreen, ctypes.byref(new_info))
            kernel32.SetConsoleWindowInfo(hScreen, True,
                    ctypes.byref(new_info.srWindow))
            kernel32.FillConsoleOutputCharacterW(
                    hScreen, u'\0', ncols * nrows, COORD(0,0), nwritten)
            kernel32.SetConsoleActiveScreenBuffer(hScreen)
            try:
                yield fd_screen
            finally:
                kernel32.SetConsoleScreenBufferInfoEx(
                    hStdOut, ctypes.byref(info))
                kernel32.SetConsoleWindowInfo(hStdOut, True,
                        ctypes.byref(info.srWindow))
                kernel32.SetConsoleActiveScreenBuffer(hStdOut)
        finally:
            if fd_screen is not None:
                os.close(fd_screen)
            else:
                kernel32.CloseHandle(hScreen)

    def read_screen(fd):
        hScreen = msvcrt.get_osfhandle(fd)
        csbi = CONSOLE_SCREEN_BUFFER_INFOEX()
        kernel32.GetConsoleScreenBufferInfoEx(
            hScreen, ctypes.byref(csbi))
        ncols = csbi.dwSize.X
        pos = csbi.dwCursorPosition
        length = ncols * pos.Y + pos.X + 1
        buf = (ctypes.c_wchar * length)()
        n = (wintypes.DWORD * 1)()
        kernel32.ReadConsoleOutputCharacterW(
            hScreen, buf, length, COORD(0,0), n)
        lines = [buf[i:i+ncols].rstrip(u'\0')
                    for i in range(0, n[0], ncols)]
        return u'\n'.join(lines)

@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class WindowsConsoleTest(DeviceTest):
    def test_unicode_output(self):
        """Test Unicode command line parameters and Unicode console window output.

        Bug: https://issuetracker.google.com/issues/111972753
        """
        # If we don't have a console window, allocate one. This isn't necessary if we're already
        # being run from a console window, which is typical.
        with allocate_console() as allocated_console:
            # Create a temporary console buffer and switch to it. We could also pass a parameter of
            # ncols=len(unicode_string), but it causes the window to flash as it is resized and
            # likely unnecessary given the typical console window size.
            with console_screen(nrows=1000) as screen:
                unicode_string = u'로보카 폴리'
                # Run adb and allow it to detect that stdout is a console, not a pipe, by using
                # device.shell_popen() which does not use a pipe, unlike device.shell().
                process = self.device.shell_popen(['echo', '"' + unicode_string + '"'])
                process.wait()
                # Read what was written by adb to the temporary console buffer.
                console_output = read_screen(screen)
                self.assertEqual(unicode_string, console_output)

class DevicesListing(DeviceTest):

    serial = subprocess.check_output(['adb', 'get-serialno']).strip().decode("utf-8")
    # def get_serial(self):
    #     return subprocess.check_output(self.device.adb_cmd + ['get-serialno']).strip().decode("utf-8")

    def test_devices(self):
        with subprocess.Popen(['adb', 'devices'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            lines = list(map(lambda b: b.decode("utf-8"), proc.stdout.readlines()))
            self.assertEqual(len(lines), 3)
            line = lines[1]
            self.assertTrue(self.serial in line)
            self.assertFalse("{" in line)
            self.assertFalse("}" in line)
            self.assertTrue("device" in line)
            self.assertFalse("product" in line)
            self.assertFalse("transport" in line)

    def test_devices_l(self):
        with subprocess.Popen(['adb', 'devices', '-l'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            lines = list(map(lambda b: b.decode("utf-8"), proc.stdout.readlines()))
            self.assertEqual(len(lines), 3)
            line = lines[1]
            self.assertTrue(self.serial in line)
            self.assertFalse("{" in line)
            self.assertFalse("}" in line)
            self.assertTrue("device" in line)
            self.assertTrue("product" in line)
            self.assertTrue("transport" in line)

    def test_track_devices(self):
        with subprocess.Popen(['adb', 'track-devices'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            with io.TextIOWrapper(proc.stdout, encoding='utf8') as reader:
                output_size = int(reader.read(4), 16)
                output = reader.read(output_size)
                self.assertFalse("{" in output)
                self.assertFalse("}" in output)
                self.assertTrue(self.serial in output)
                self.assertTrue("device" in output)
                self.assertFalse("product" in output)
                self.assertFalse("transport" in output)
            proc.terminate()

    def test_track_devices_l(self):
        with subprocess.Popen(['adb', 'track-devices', '-l'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            with io.TextIOWrapper(proc.stdout, encoding='utf8') as reader:
                output_size = int(reader.read(4), 16)
                output = reader.read(output_size)
                self.assertFalse("{" in output)
                self.assertFalse("}" in output)
                self.assertTrue(self.serial in output)
                self.assertTrue("device" in output)
                self.assertTrue("product" in output)
                self.assertTrue("transport" in output)
            proc.terminate()

    def test_track_devices_proto_text(self):
        with subprocess.Popen(['adb', 'track-devices', '--proto-text'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            with io.TextIOWrapper(proc.stdout, encoding='utf8') as reader:
                output_size = int(reader.read(4), 16)
                output = reader.read(output_size)
                self.assertTrue("{" in output)
                self.assertTrue("}" in output)
                self.assertTrue(self.serial in output)
                self.assertTrue("device" in output)
                self.assertTrue("product" in output)
                self.assertTrue("connection_type" in output)
            proc.terminate()

    def test_track_devices_proto_binary(self):
        with subprocess.Popen(['adb', 'track-devices', '--proto-binary'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:

            output_size = int(proc.stdout.read(4).decode("utf-8"), 16)
            proto = proc.stdout.read(output_size)

            devices = adb_host_proto.Devices()
            devices.ParseFromString(proto)

            device = devices.device[0]
            self.assertTrue(device.serial == self.serial)
            self.assertFalse(device.bus_address == "")
            self.assertFalse(device.product == "")
            self.assertFalse(device.model == "")
            self.assertFalse(device.device == "")
            self.assertTrue(device.negotiated_speed == int(device.negotiated_speed))
            self.assertTrue(device.max_speed == int(device.max_speed))
            self.assertTrue(device.transport_id == int(device.transport_id))

            proc.terminate()

class DevicesListing(DeviceTest):

    serial = subprocess.check_output(['adb', 'get-serialno']).strip().decode("utf-8")

    def test_track_app_appinfo(self):
        return # Disabled until b/301491148 is fixed.
        # (Exported FeatureFlags cannot be read-only)
        subprocess.check_output(['adb', 'install', '-t', 'adb1.apk']).strip().decode("utf-8")
        subprocess.check_output(['adb', 'install', '-t', 'adb2.apk']).strip().decode("utf-8")
        subprocess.check_output(['adb', 'shell', 'am', 'start', '-W', 'adb.test.app1/.MainActivity']).strip().decode("utf-8")
        subprocess.check_output(['adb', 'shell', 'am', 'start', '-W', 'adb.test.app2/.MainActivity']).strip().decode("utf-8")
        subprocess.check_output(['adb', 'shell', 'am', 'start', '-W', 'adb.test.app1/.OwnProcessActivity']).strip().decode("utf-8")
        with subprocess.Popen(['adb', 'track-app', '--proto-binary'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            output_size = int(proc.stdout.read(4).decode("utf-8"), 16)
            proto = proc.stdout.read(output_size)

            apps = proto_track_app.AppProcesses()
            apps.ParseFromString(proto)

            foundAdbAppDefProc = False
            foundAdbAppOwnProc = False
            for app in apps.process:
                if (app.process_name == "adb.test.process.name"):
                    foundAdbAppDefProc = True
                    self.assertTrue(app.debuggable)
                    self.assertTrue("adb.test.app1" in app.package_names)
                    self.assertTrue("adb.test.app2" in app.package_names)

                if (app.process_name == "adb.test.own.process"):
                    foundAdbAppOwnProc = True
                    self.assertTrue(app.debuggable)
                    self.assertTrue("adb.test.app1" in app.package_names)

            self.assertTrue(foundAdbAppDefProc)
            self.assertTrue(foundAdbAppOwnProc)
            proc.terminate()

class ServerStatus(unittest.TestCase):
    def test_server_status(self):
        with subprocess.Popen(['adb', 'server-status'], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as proc:
            lines = list(map(lambda b: b.decode("utf-8"), proc.stdout.readlines()))
            self.assertTrue("usb_backend" in lines[0])
            self.assertTrue("mdns_backend" in lines[1])
            self.assertTrue("version" in lines[2])
            self.assertTrue("build" in lines[3])
            self.assertTrue("executable_absolute_path" in lines[4])
            self.assertTrue("log_absolute_path" in lines[5])

if __name__ == '__main__':
    random.seed(0)
    unittest.main()
