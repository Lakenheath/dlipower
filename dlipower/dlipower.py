#!/usr/bin/python
# Copyright (c) 2009-2015, Dwight Hubbard
# Copyrights licensed under the New BSD License
# See the accompanying LICENSE.txt file for terms.
"""
Digital Loggers Web Power Switch Management

The module provides a python class named
powerswitch that allows managing the web power
switch from python programs.

When run as a script this acts as a command line utility to
manage the DLI Power switch.

Notes
-----
This module has been tested against the following
Digital Loggers Power network power switches:
  WebPowerSwitch II
  WebPowerSwitch III
  WebPowerSwitch IV
  WebPowerSwitch V
  Ethernet Power Controller III

Examples
--------

*Connecting to a Digital Loggers Power switch*

>>> from dlipower import PowerSwitch
>>> switch = PowerSwitch(hostname='lpc.digital-loggers.com', userid='admin', password='4321')

*Getting the power state (status) from the switch*
Printing the switch object will print a table with the
Outlet Number, Name and Power State

>>> switch
DLIPowerSwitch at lpc.digital-loggers.com
Outlet	Name           	State
1	Battery Charger	     OFF
2	K3 Power ON    	     ON
3	Cisco Router   	     OFF
4	WISP access poi	     ON
5	Shack Computer 	     OFF
6	Router         	     OFF
7	2TB Drive      	     ON
8	Cable Modem1   	     ON

*Getting the name and powerswitch of the first outlet*
The PowerSwitch has a series of Outlet objects, they
will display their name and state if printed.

>>> switch[0]
<dlipower_outlet 'Traffic light:OFF'>

*Renaming the first outlet*
Changing the "name" attribute of an outlet will
rename the outlet on the powerswitch.

>>> switch[0].name = 'Battery Charger'
>>> switch[0]
<dlipower_outlet 'Battery Charger:OFF'>

*Turning the first outlet on*
Individual outlets can be accessed uses normal
list slicing operators.

>>> switch[0].on()
False
>>> switch[0]
<dlipower_outlet 'Battery Charger:ON'>

*Turning all outlets off*
The PowerSwitch() object supports iterating over
the available outlets.

>>> for outlet in switch:
...     outlet.off()
...
False
False
False
False
False
False
False
False
>>> switch
DLIPowerSwitch at lpc.digital-loggers.com
Outlet	Name           	State
1	Battery Charger	OFF
2	K3 Power ON    	OFF
3	Cisco Router   	OFF
4	WISP access poi	OFF
5	Shack Computer 	OFF
6	Router         	OFF
7	2TB Drive      	OFF
8	Cable Modem1   	OFF
"""

import logging
import multiprocessing
import json
import time
from hammock import Hammock
from requests.auth import HTTPDigestAuth


# Global settings
TIMEOUT = 20
RETRIES = 3
CYCLETIME = 3
CONFIG_DEFAULTS = {
    'timeout': TIMEOUT,
    'cycletime': CYCLETIME,
    'userid': 'admin',
    'password': '4321',
    'hostname': '192.168.10.12'
}


def _call_it(params):   # pragma: no cover
    """indirect caller for instance methods and multiprocessing"""
    instance, name, args = params
    kwargs = {}
    return getattr(instance, name)(*args, **kwargs)


class DLIPowerException(Exception):
    """
    An error occurred talking the the DLI Power switch
    """
    pass


class Outlet(object):
    """
    A power outlet class
    """
    use_description = True

    def __init__(self, switch, outlet_number, description=None, state=None):
        self.switch = switch
        self.outlet_number = outlet_number
        self.description = description
        if not description:
            self.description = str(outlet_number)
        self._state = state

    def __unicode__(self):
        name = None
        if self.use_description and self.description:  # pragma: no cover
            name = '%s' % self.description
        if not name:
            name = '%d' % self.outlet_number
        return '%s:%s' % (name, self._state)

    def __str__(self):
        return self.__unicode__()

    def __repr__(self):
        return "<dlipower_outlet '%s'>" % self.__unicode__()

    def _repr_html_(self):  # pragma: no cover
        """ Display representation as an html table when running in ipython """
        return u"""<table>
    <tr><th>Description</th><th>Outlet Number</th><th>State</th></tr>
    <tr><td>{0:s}</td><td>{1:s}</td><td>{2:s}</td></tr>
</table>""".format(self.description, self.outlet_number, self.state)

    @property
    def state(self):
        """ Return the outlet state """
        return self._state

    @state.setter
    def state(self, value):
        """ Set the outlet state """
        self._state = value
        if value in ['off', 'OFF', '0']:
            self.off()
        if value in ['on', 'ON', '1']:
            self.on()

    def off(self):
        """ Turn the outlet off """
        return self.switch.off(self.outlet_number)

    def on(self):
        """ Turn the outlet on """
        return self.switch.on(self.outlet_number)

    def rename(self, new_name):
        """
        Rename the outlet
        :param new_name: New name for the outlet
        :return:
        """
        return self.switch.set_outlet_name(self.outlet_number, new_name)

    @property
    def name(self):
        """ Return the name or description of the outlet """
        return self.switch.get_outlet_name(self.outlet_number)

    @name.setter
    def name(self, new_name):
        """ Set the name of the outlet """
        self.rename(new_name)


class PowerSwitch(object):
    """ Powerswitch class to manage the Digital Loggers Web power switch """
    __len = 0
    login_timeout = 2.0

    def __init__(self, userid=None, password=None, hostname=None, timeout=None,
                 cycletime=None, retries=None):
        """
        Class initializaton
        """
        if not retries:
            retries = RETRIES
        if retries:
            self.retries = retries
        if userid:
            self.userid = userid
        else:
            self.userid = CONFIG_DEFAULTS['userid']
        if password:
            self.password = password
        else:
            self.password = CONFIG_DEFAULTS['password']
        if hostname:
            self.hostname = hostname
        else:
            self.hostname = CONFIG_DEFAULTS['hostname']
        if timeout:
            self.timeout = float(timeout)
        else:
            self.timeout = CONFIG_DEFAULTS['timeout']
        if cycletime:
            self.cycletime = float(cycletime)
        else:
            self.cycletime = CONFIG_DEFAULTS['cycletime']
        auth = HTTPDigestAuth(self.userid, self.password)
        self.session = Hammock(f"http://{self.hostname}/restapi", append_slash=True, auth=auth, headers={'X-CSRF': 'x'})
        self.outlets = self.session.relay.outlets

    def __len__(self):
        """
        :return: Number of outlets on the switch
        """
        if self.__len == 0:
            self.__len = len(self.statuslist())
        return self.__len

    def __repr__(self):
        """
        display the representation
        """
        if not self.statuslist():
            return "Digital Loggers Web Powerswitch " \
                   "%s (UNCONNECTED)" % self.hostname
        output = 'DLIPowerSwitch at %s\n' \
                 'Outlet\t%-15.15s\tState\n' % (self.hostname, 'Name')
        for item in self.statuslist():
            output += '%d\t%-15.15s\t%s\n' % (item[0], item[1], item[2])
        return output

    def _repr_html_(self):
        """
        __repr__ in an html table format
        """
        if not self.statuslist():
            return "Digital Loggers Web Powerswitch " \
                   "%s (UNCONNECTED)" % self.hostname
        output = '<table>' \
                 '<tr><th colspan="3">DLI Web Powerswitch at %s</th></tr>' \
                 '<tr>' \
                 '<th>Outlet Number</th>' \
                 '<th>Outlet Name</th>' \
                 '<th>Outlet State</th></tr>\n' % self.hostname
        for item in self.statuslist():
            output += '<tr><td>%d</td><td>%s</td><td>%s</td></tr>\n' % (
                item[0], item[1], item[2])
        output += '</table>\n'
        return output

    def __getitem__(self, index):
        outlets = []
        if isinstance(index, slice):
            status = self.statuslist()[index.start:index.stop]
        else:
            status = [self.statuslist()[index]]
        for outlet_status in status:
            power_outlet = Outlet(
                switch=self,
                outlet_number=outlet_status[0],
                description=outlet_status[1],
                state=outlet_status[2]
            )
            outlets.append(power_outlet)
        if len(outlets) == 1:
            return outlets[0]
        return outlets


    def determine_outlet(self, outlet=None):
        """ Get the correct outlet number from the outlet passed in, this
            allows specifying the outlet by the name and making sure the
            returned outlet is an int
        """
        outlets = self.statuslist()
        if outlet and outlets and isinstance(outlet, str):
            for plug in outlets:
                plug_name = plug[1]
                if plug_name and plug_name.strip() == outlet.strip():
                    return int(plug[0])
        try:
            outlet_int = int(outlet)
            if outlet_int <= 0 or outlet_int > self.__len__():
                raise DLIPowerException('Outlet number %d out of range' % outlet_int)
            return outlet_int
        except ValueError:
            raise DLIPowerException('Outlet name \'%s\' unknown' % outlet)

    def get_outlet_name(self, outlet=0):
        """ Return the name of the outlet """
        outlet = self.determine_outlet(outlet)
        outlets = self.statuslist()
        if outlets and outlet:
            for plug in outlets:
                if int(plug[0]) == outlet:
                    return plug[1]
        return 'Unknown'

    def set_outlet_name(self, outlet=0, name="Unknown"):
        """ Set the name of an outlet """
        self.determine_outlet(outlet)
        self.outlets(outlet).name.PUT(json=name)
        return self.get_outlet_name(outlet) == name

    def off(self, outlet=0):
        """ Turn off a power to an outlet
            False = Success
            True = Fail
        """
        self.outlets(self.determine_outlet(outlet)).state.PUT(json=False)
        return self.status(outlet) != 'OFF'

    def on(self, outlet=0):
        """ Turn on power to an outlet
            False = Success
            True = Fail
        """
        self.outlets(self.determine_outlet(outlet)).state.PUT(json=True)
        return self.status(outlet) != 'ON'

    def cycle(self, outlet=0):
        """ Cycle power to an outlet
            False = Power off Success
            True = Power off Fail
            Note, does not return any status info about the power on part of
            the operation by design
        """
        self.off(outlet)
        time.sleep(self.cycletime)
        self.on(outlet)
        return False

    def statuslist(self):
        """ Return the status of all outlets in a list,
        each item will contain 3 items plugnumber, hostname and state  """
        outlets = []
        temp = json.loads(self.outlets.GET().text)
        for i, o in enumerate(temp):
            outlets.append([i + 1, o['name'], o['physical_state']])
        if self.__len == 0:
            self.__len = len(outlets)
        return outlets

    def printstatus(self):
        """ Print the status off all the outlets as a table to stdout """
        if not self.statuslist():
            print("Unable to communicate to the Web power switch at %s" % self.hostname)
            return None
        print('Outlet\t%-15.15s\tState' % 'Name')
        for item in self.statuslist():
            print('%d\t%-15.15s\t%s' % (item[0], item[1], item[2]))
        return

    def status(self, outlet=1):
        """
        Return the status of an outlet, returned value will be one of:
        ON, OFF, Unknown
        """
        outlet = self.determine_outlet(outlet)
        outlets = self.statuslist()
        if outlets and outlet:
            for plug in outlets:
                if plug[0] == outlet:
                    return plug[2] == 'ON'
        return 'Unknown'

    def command_on_outlets(self, command, outlets):
        """
        If a single outlet is passed, handle it as a single outlet and
        pass back the return code.  Otherwise run the operation on multiple
        outlets in parallel the return code will be failure if any operation
        fails.  Operations that return a string will return a list of strings.
        """
        if len(outlets) == 1:
            result = getattr(self, command)(outlets[0])
            if isinstance(result, bool):
                return result
            else:
                return [result]
        pool = multiprocessing.Pool(processes=len(outlets))
        result = [
            value for value in pool.imap(
                _call_it,
                [(self, command, (outlet, )) for outlet in outlets],
                chunksize=1
            )
        ]
        pool.close()
        pool.join()
        if isinstance(result[0], bool):
            for value in result:
                if value:
                    return True
            return result[0]
        return result


if __name__ == "__main__":  # pragma: no cover
    epcr = PowerSwitch(userid='admin', password='4321', hostname='192.168.10.12')
    epcr.printstatus()
    print(epcr.statuslist())

    # auth = HTTPDigestAuth('admin', '4321')
    # session = Hammock("http://192.168.10.12/restapi", append_slash=True, auth=auth, headers={'X-CSRF': 'x'})
    # outlets = session.relay.outlets
    # listOutlets = json.loads(outlets.GET().text)
    # print(listOutlets)
    # for o in listOutlets:
    #     print(o['name'])

    # Relay 1 starts switching on
    # for i in range(1, 8):
    #     outlets(i).state.PUT(json=True)  # outlets 1-7 switch on

    # time.sleep(7)
    #
    # for i in range(8):
    #     outlets(i).state.PUT(json=False)  # all outlets switch off

    # admin

