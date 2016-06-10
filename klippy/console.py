#!/usr/bin/env python
# Script to implement a test console with firmware over serial port
#
# Copyright (C) 2016  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import sys, optparse, os, re, logging

import reactor, serialhdl, pins, util, msgproto

re_eval = re.compile(r'\{(?P<eval>[^}]*)\}')

class KeyboardReader:
    def __init__(self, ser, reactor):
        self.ser = ser
        self.reactor = reactor
        self.fd = sys.stdin.fileno()
        util.set_nonblock(self.fd)
        self.pins = None
        self.data = ""
        self.reactor.register_fd(self.fd, self.process_kbd)
        self.local_commands = { "PINS": self.set_pin_map }
        self.eval_globals = {}
    def update_evals(self, eventtime):
        f = self.ser.msgparser.config.get('CLOCK_FREQ', 1)
        c = (eventtime - self.ser.last_ack_time) * f + self.ser.last_ack_clock
        self.eval_globals['freq'] = f
        self.eval_globals['clock'] = int(c)
    def set_pin_map(self, parts):
        mcu = self.ser.msgparser.config['MCU']
        self.pins = pins.map_pins(parts[1], mcu)
    def lookup_pin(self, value):
        if self.pins is None:
            self.pins = pins.mcu_to_pins(self.ser.msgparser.config['MCU'])
        return self.pins[value]
    def translate(self, line, eventtime):
        evalparts = re_eval.split(line)
        if len(evalparts) > 1:
            self.update_evals(eventtime)
            try:
                for i in range(1, len(evalparts), 2):
                    evalparts[i] = str(eval(evalparts[i], self.eval_globals))
            except:
                print "Unable to evaluate: ", line
                return None
            line = ''.join(evalparts)
            print "Eval:", line
        if self.pins is None and self.ser.msgparser.config:
            self.pins = pins.mcu_to_pins(self.ser.msgparser.config['MCU'])
        if self.pins is not None:
            try:
                line = pins.update_command(line, self.pins).strip()
            except:
                print "Unable to map pin: ", line
                return None
        if line:
            parts = line.split()
            if parts[0] in self.local_commands:
                self.local_commands[parts[0]](parts)
                return None
        try:
            msg = self.ser.msgparser.create_command(line)
        except msgproto.error, e:
            print "Error:", e
            return None
        return msg
    def process_kbd(self, eventtime):
        self.data += os.read(self.fd, 4096)

        kbdlines = self.data.split('\n')
        for line in kbdlines[:-1]:
            line = line.strip()
            cpos = line.find('#')
            if cpos >= 0:
                line = line[:cpos]
                if not line:
                    continue
            msg = self.translate(line.strip(), eventtime)
            if msg is None:
                continue
            self.ser.send(msg)
        self.data = kbdlines[-1]

def main():
    usage = "%prog [options] <serialdevice> <baud>"
    opts = optparse.OptionParser(usage)
    options, args = opts.parse_args()
    serialport, baud = args
    baud = int(baud)

    logging.basicConfig(level=logging.DEBUG)
    r = reactor.Reactor()
    ser = serialhdl.SerialReader(r, serialport, baud)
    ser.connect()
    kbd = KeyboardReader(ser, r)
    try:
        r.run()
    except KeyboardInterrupt:
        sys.stdout.write("\n")

if __name__ == '__main__':
    main()