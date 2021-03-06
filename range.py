#!/usr/bin/python
# -*- coding: utf-8 -*-
# Quick an dirty MetaWatch client in Python for pybluez.
# Written by Travis Goodspeed on--not for--the Nokia N900.

# This doesn't work with very old versions of the MetaWatch.
# Be sure to use a minimum of 0.7.15 and 1.1.7.

import sys, time;
import termios, os
try:
    import bluetooth
except ImportError:
    bluetooth = None
    import lightblue
import socket

import struct
import bluetooth._bluetooth as bluez

import threading


MODE_IDLE = 0
MODE_APPLICATION = 1
MODE_NOTIFICATION = 2
MODE_SCROLL = 3

STATUS_CHANGE_MODE = 0
STATUS_CHANGE_DISPLAYIMEOUT = 1

BUTTON_A = 0
BUTTON_B = 1
BUTTON_C = 2
BUTTON_D = 3
BUTTON_E = 5
BUTTON_F = 6

BUTTON_TYPE_IMMEDIATE = 0
BUTTON_TYPE_PRESSANDRELEASE = 1
BUTTON_TYPE_HOLDANDRELEASE = 2
BUTTON_TYPE_LONHOLDANDRELEASE = 3

def printpacket(pkt):
    for c in pkt:
        sys.stdout.write("%02x " % struct.unpack("B",c)[0])
    print 


def read_inquiry_mode(sock):
    """returns the current mode, or -1 on failure"""
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # Setup socket filter to receive only events related to the
    # read_inquiry_mode command
    flt = bluez.hci_filter_new()
    opcode = bluez.cmd_opcode_pack(bluez.OGF_HOST_CTL, 
            bluez.OCF_READ_INQUIRY_MODE)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    bluez.hci_filter_set_event(flt, bluez.EVT_CMD_COMPLETE);
    bluez.hci_filter_set_opcode(flt, opcode)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    # first read the current inquiry mode.
    bluez.hci_send_cmd(sock, bluez.OGF_HOST_CTL, 
            bluez.OCF_READ_INQUIRY_MODE )

    pkt = sock.recv(255)

    status,mode = struct.unpack("xxxxxxBB", pkt)
    if status != 0: mode = -1

    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )
    return mode

def write_inquiry_mode(sock, mode):
    """returns 0 on success, -1 on failure"""
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # Setup socket filter to receive only events related to the
    # write_inquiry_mode command
    flt = bluez.hci_filter_new()
    opcode = bluez.cmd_opcode_pack(bluez.OGF_HOST_CTL, 
            bluez.OCF_WRITE_INQUIRY_MODE)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    bluez.hci_filter_set_event(flt, bluez.EVT_CMD_COMPLETE);
    bluez.hci_filter_set_opcode(flt, opcode)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    # send the command!
    bluez.hci_send_cmd(sock, bluez.OGF_HOST_CTL, 
            bluez.OCF_WRITE_INQUIRY_MODE, struct.pack("B", mode) )

    pkt = sock.recv(255)

    status = struct.unpack("xxxxxxB", pkt)[0]

    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )
    if status != 0: return -1
    return 0

def device_inquiry_with_with_rssi(sock):
    # save current filter
    old_filter = sock.getsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, 14)

    # perform a device inquiry on bluetooth device #0
    # The inquiry should last 8 * 1.28 = 10.24 seconds
    # before the inquiry is performed, bluez should flush its cache of
    # previously discovered devices
    flt = bluez.hci_filter_new()
    bluez.hci_filter_all_events(flt)
    bluez.hci_filter_set_ptype(flt, bluez.HCI_EVENT_PKT)
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, flt )

    duration = 4
    max_responses = 255
    cmd_pkt = struct.pack("BBBBB", 0x33, 0x8b, 0x9e, duration, max_responses)
    bluez.hci_send_cmd(sock, bluez.OGF_LINK_CTL, bluez.OCF_INQUIRY, cmd_pkt)

    results = []

    done = False
    while not done:
        pkt = sock.recv(255)
        ptype, event, plen = struct.unpack("BBB", pkt[:3])
        if event == bluez.EVT_INQUIRY_RESULT_WITH_RSSI:
            pkt = pkt[3:]
            nrsp = struct.unpack("B", pkt[0])[0]
            for i in range(nrsp):
                addr = bluez.ba2str( pkt[1+6*i:1+6*i+6] )
                rssi = struct.unpack("b", pkt[1+13*nrsp+i])[0]
                results.append( ( addr, rssi ) )
                print "[%s] RSSI: [%d]" % (addr, rssi)
        elif event == bluez.EVT_INQUIRY_COMPLETE:
            done = True
        elif event == bluez.EVT_CMD_STATUS:
            status, ncmd, opcode = struct.unpack("BBH", pkt[3:7])
            if status != 0:
                print "uh oh..."
                printpacket(pkt[3:7])
                done = True
        elif event == bluez.EVT_INQUIRY_RESULT:
            pkt = pkt[3:]
            nrsp = struct.unpack("B", pkt[0])[0]
            for i in range(nrsp):
                addr = bluez.ba2str( pkt[1+6*i:1+6*i+6] )
                results.append( ( addr, -1 ) )
                print "[%s] (no RRSI)" % addr
        else:
            print "unrecognized packet type 0x%02x" % ptype
	    print "event ", event


    # restore old filter
    sock.setsockopt( bluez.SOL_HCI, bluez.HCI_FILTER, old_filter )

    return results
    
TERMIOS = termios

def getkey():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        new = termios.tcgetattr(fd)
        new[3] = new[3] & ~TERMIOS.ICANON & ~TERMIOS.ECHO
        new[6][TERMIOS.VMIN] = 1
        new[6][TERMIOS.VTIME] = 0
        termios.tcsetattr(fd, TERMIOS.TCSANOW, new)
        c = None
        try:
                c = os.read(fd, 1)
        finally:
                termios.tcsetattr(fd, TERMIOS.TCSAFLUSH, old)
        return c
        
class MetaWatch:
    _TX_PACKET_WAIT_SEC = 0.1
    _TX_PACKET_WAIT_SEC = 0.01

    def __init__(self, watchaddr = None, verbose = False,debug=True):
        self.CRC=CRC_CCITT();
        self._last_tx_time = time.clock()
        self.verbose = verbose
        self.debug=debug
	self.invertDisplay=False
        while watchaddr == None or watchaddr == "none":
            print "performing inquiry..."
            if bluetooth:
                nearby_devices = bluetooth.discover_devices(lookup_names = True)
            else:
                # Need to strip the third "device class" tuple element from results
                nearby_devices = map(lambda x:x[:2], lightblue.finddevices())

            print "found %d devices" % len(nearby_devices)
            for addr, name in nearby_devices:
                print "  %s - '%s'" % (addr, name)
                if name and ('MetaWatch Digital' in name or 'Fossil Digital' in name) :
                    watchaddr=addr;
                    print "Identified Watch at %s" % watchaddr;

        # MetaWatch doesn't run the Service Discovery Protocol.
        # Instead we manually use the portnumber.
        port=1;

        print "Connecting to %s on port %i." % (watchaddr, port);
        if bluetooth:
            sock=bluetooth.BluetoothSocket(bluetooth.RFCOMM);
            # print rssi
            print "Computing rssi"
	    dev_id = 0
	    try:
		self.sock_monitor = bluez.hci_open_dev(dev_id)
	    except:
		print "error accessing bluetooth device..."
		sys.exit(1)
	    try:
		mode = read_inquiry_mode(self.sock_monitor)
	    except Exception, e:
		print "error reading inquiry mode.  "
		print "Are you sure this a bluetooth 1.2 device?"
		print e
		sys.exit(1)
	    print "current inquiry mode is %d" % mode

	    if mode != 1:
		print "writing inquiry mode..."
		try:
		    result = write_inquiry_mode(sock_monitor, 1)
		except Exception, e:
		    print "error writing inquiry mode.  Are you sure you're root?"
		    print e
		    sys.exit(1)
		if result != 0:
		    print "error while setting inquiry mode"
		print "result: %d" % result            
	    device_inquiry_with_with_rssi(self.sock_monitor)
        else:
            sock=lightblue.socket();
        sock.setblocking(True)

        self.sock = sock;

        sock.connect((watchaddr, port));
        sock.settimeout(10);            # IMPORTANT Must be patient, must come after connect().
        self.setclock()
        #Buzz to indicate connection.
        self.buzz();

    def getRSSI(self):
        device_inquiry_with_with_rssi(self.sock_monitor)
        
    def close(self):
        """Close the connection."""
        self.sock.close();

    def tx(self,msg,rx=True):
        """Transmit a MetaWatch packet.  SFD, Length, and Checksum will be added."""
        time_since_last_tx = time.clock() - self._last_tx_time

        #Prepend SFD, length.
        msg="\x01"+chr(len(msg)+4)+msg;
        #Append CRC.
        crc=self.CRC.checksum(msg);
        msg=msg+chr(crc&0xFF)+chr(crc>>8); #Little Endian

        tmp = msg
        while len(tmp):
            tmp = tmp[self.sock.send(tmp, socket.MSG_WAITALL):]
            if self.debug:
	      print len(tmp), "left to send"
        #result = self.sock.sendall(msg, socket.MSG_WAITALL);
        self._last_txt_time = time.clock()

        if self.verbose:
            print "Sent message: %s" % hex(msg);

        if not rx:
            return None;
        return self.rx();

    def rx(self):
        data=None;
        #Is there a reply?
        try:
            data=self.sock.recv(32);
            data=data[2:];
        except IOError:pass;
        if self.verbose: print "Received [%s]" % hex(data);
        return data;

    def writebuffer(self, mode, row1, data1, row2=None, data2=None):
        """Writes image data to the Draw Buffer.
        You'll need to send activatedisplay() to swap things over when done."""
        option=mode; #idle screen, single row.
        if row2 != None:
            option = option | 0x10;

        packet="\x40%s%s%s\x00" % (
                chr(option),
                chr(row1),
                data1[0:12]
                )
        if row2!=None:
            packet="%s%s%s" % (
                    packet,
                    chr(row2),
                    data2[0:11]);
        self.tx(packet,rx=False);

    def clearbuffer(self,mode=1,filled=True):
        self.loadtemplate(mode,filled);

    def testwritebuffer(self,mode=1):
        m=mode;
        image=["\x00\xFF\x00\xFF\x00\xFF\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
                "\xFF\x00\xFF\x00\xFF\x00\xFF\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
                ];
        self.loadtemplate(mode=m,filled=1);
        # Blank some rows.
        for foo in range(0,96):
            self.writebuffer(m,
                            foo, image[(foo/8)%2]
                            #);
                            ,foo+40, image[((foo+40)/8)%2]);
            #self.updatedisplay(mode=m);
        self.updatedisplay(mode=m);

    def writeimage(self, mode=0, image="template.bmp", live=False):
        """Write a 1bpp BMP file to the watch in the given mode."""
        import Image;
        im=Image.open(image);
        pix=im.load();
        for y in range(0,96):
            rowstr="";
            rowdat="";
            for x in range(0,96,8):
                byte=0;
                for pindex in range(0,8):
                    pixel=pix[x+pindex,y];
                    if (pixel > 0):
                        pixel = 1
                    rowstr="%s%i" % (rowstr,pixel);
                    #byte=((byte<<1)+pixel);
                    byte=((byte>>1)|(pixel<<7));
                rowdat="%s%s" % (rowdat,chr(byte));
            if self.debug:
	      print rowstr;
            self.writebuffer(mode,
                            y, rowdat)#,
                            #0,rowdat);
            if live:
                self.updatedisplay(mode=mode);
        self.updatedisplay(mode=mode);


    def writeText(self,mode=0,text=''):
        import Image,ImageDraw,ImageFont

        image=None
	if(self.invertDisplay):
	  image = Image.new("1",(96,96),"white")
	else:
	  image = Image.new("1",(96,96),"black")
	#the top header is reserverd for the clock
        self.draw_word_wrap(image,text,2,8)
        image.save('tmp.bmp','BMP')
        self.writeimage(mode,"tmp.bmp",live=True)

    def draw_word_wrap(self,img, text, xpos=0, ypos=0, max_width=95):
        import Image,ImageDraw,ImageFont
        font=ImageFont.load_default()

        # textwrapping adapted from http://jesselegg.com/archives/2009/09/5/simple-word-wrap-algorithm-pythons-pil/

        draw = ImageDraw.Draw(img)
        text_size_x, text_size_y = draw.textsize(text, font=font)
        remaining = max_width
        space_width, space_height = draw.textsize(' ', font=font)
        # use this list as a stack, push/popping each line
        output_text = []
        # split on whitespace...
        for word in text.split(None):
            word_width, word_height = draw.textsize(word, font=font)
            if word_width + space_width > remaining:
                output_text.append(word)
                remaining = max_width - word_width
            else:
                if not output_text:
                    output_text.append(word)
                else:
                    output = output_text.pop()
                    output += ' %s' % word
                    output_text.append(output)
            remaining = remaining - (word_width + space_width)
        for text in output_text:
	    if(self.invertDisplay):
	      draw.text((xpos, ypos), text, font=font, fill='black')
	    else:
	      draw.text((xpos, ypos), text, font=font, fill='white')
            ypos += text_size_y



    def updatedisplay(self,mode=0,activate=0):
        """Update the display to a particular mode."""
        time.sleep(0.1)
        if activate:
            mode=mode|0x10
        #time.sleep(0.1); #rate limiting is necessary here.
        self.tx("\x43%s" % chr(mode),rx=False)

    def loadtemplate(self,mode=0,filled=0):
        """Update the display to a particular mode."""
        self.tx("\x44%s%s" % (chr(mode), chr(filled)), rx=False)


    def idle(self):
        """Wait a second."""
        data = self.rx();
        if not data:
            return

        cmd = data[0]
        if cmd == "\x34":
            # we received a button press
            buttonIndex = data[1]
            print "button [%i] pressed" % ord(buttonIndex);

    def buzz(self, ms_on=500, ms_off=500, cycles=1):
        """Buzz the buzzer."""

        ms_on = min(ms_on, 65535)
        ms_off = min(ms_off, 65535)
        cycles = min(cycles, 256)

        message = []
        message.append("\x23\x00\x01")
        message.append(chr(ms_on % 256))
        message.append(chr(ms_on / 256))
        message.append(chr(ms_off % 256))
        message.append(chr(ms_off / 256))
        message.append(chr(cycles))
        self.tx(''.join(message), False)

    def showtime(self, watch_controls_top):
        """Set whether the watch shows the time at top."""

        message = []
        message.append("\x42\x00")
        if watch_controls_top:
            message.append("\x00")
        else:
            message.append("\x01")

        self.tx(''.join(message), False)

    def gettype(self):
        """Get the version information."""
        devtyperesp=self.tx("\x01\x00");
        devtype=ord(devtyperesp[2]);
        types=["Reserved",
                "Ana-Digi", "Digital",
                "DigitalDev", "AnaDigitalDev"];
        self.devtype=types[devtype];
        print "Identified %s MetaWatch" % self.devtype;

    def getinfostr(self,item=0x00):
        """Get the information string."""
        string=self.tx("\x03\x00%s" % chr(item));
        return string[:len(string)-2];  #Don't include the checksum.

        def getinfo(self):
            """Get all the information strings.""";
        model=self.getinfostr(0);
        version=self.getinfostr(1);
        return "%s %s" % (model,version);

    def setclock(self):
        """Set the date and time of the watch to the system time."""
        ltime=time.localtime();
        #Year in BIG ENDIAN, not LITTLE.
        str="\x07\xdb%s%s%s%s%s%s\x01\x01" % (
            chr(ltime.tm_mon),  #month
            chr(ltime.tm_mday), #day of month
            chr((ltime.tm_wday+1) % 7), #day of week
            chr(ltime.tm_hour), #hour
            chr(ltime.tm_min),  #min
            chr(ltime.tm_sec),  #sec
            );
        self.tx("\x26\x00"+str, rx=False);

    def getclock(self):
        """Get the local time from the watch, in order to set it or measure drift."""
        #Year in LITTLE ENDIAN, not BIG.
        data=self.tx("\x27\x00");
        date=data[2:]
        #print "Interpreting %s" % hex(date);
        year=ord(date[1])*256+ord(date[0])
        month=ord(date[2]);
        day=ord(date[3]);
        dayofweek=ord(date[4]);
        hour=ord(date[5]);
        minute=ord(date[6]);
        second=ord(date[6]);
        print "%02i:%02i on %02i.%02i.%04i" % (
                hour, minute,
                day, month, year);


    def configureWatchMode(self,mode=0, save=0, displayTimeout=0, invertDisplay=True):
        msg=[]
        msg.append("\x41")
        msg.append(chr(mode))
        msg.append(chr(displayTimeout))
        msg.append(chr(invertDisplay))

        self.tx(''.join(msg),rx=False)

    def enableButton(self, mode=0,buttonIndex=0, type=BUTTON_TYPE_IMMEDIATE):
        msg=[]
        msg.append("\x46\x00")
        msg.append(chr(mode))
        msg.append(chr(buttonIndex))
        msg.append(chr(type))
        msg.append("\x34")
        msg.append(chr(buttonIndex))

        self.tx(''.join(msg),rx=False)

    def disableButton(self, mode=0,buttonIndex=0, type=BUTTON_TYPE_IMMEDIATE):
        msg=[]
        msg.append("\x47\x00")
        msg.append(chr(mode))
        msg.append(chr(buttonIndex))
        msg.append(chr(type))

        self.tx(''.join(msg),rx=False)

    def getButtonConfiguration(self,mode=0,buttonIndex=0):
        msg=[]
        msg.append("\x48\x00")
        msg.append(chr(mode))
        msg.append(chr(buttonIndex))
        msg.append("\x00\x00\x00")

        data = self.tx(''.join(msg))

        print "button:%i %s" %(buttonIndex, data)

    def getBatteryVoltage(self):
        str="\x56\x00"
        data=self.tx(str)
        volt=ord(data[1])*256+ord(data[0])
        chargerAttached=ord(data[2])
        isCharging=ord(data[3])
        print "battery:%s charger:%s isCharging:%s" %(volt,chargerAttached,isCharging)

    def setDisplayInverted(self, inverted=True):
        str=""
        if inverted:
            str="\x41\x00\x00\x01"
        else:
            str="\x41\x00\x00\x00"

        self.tx(str,rx=False)

class CRC_CCITT:
    """Performs CRC_CCITT"""

    def __init__(self, inverted=True):
        self.inverted=inverted;
        self.tab=256*[[]]
        for i in xrange(256):
            crc=0
            c = i << 8
            for j in xrange(8):
                if (crc ^ c) & 0x8000:
                    crc = ( crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
                c = c << 1
                crc = crc & 0xffff
            self.tab[i]=crc;

    def update_crc(self, crc, c):
        c=0x00ff & (c % 256)
        if self.inverted: c=self.flip(c);
        tmp = ((crc >> 8) ^ c) & 0xffff
        crc = (((crc << 8) ^ self.tab[tmp])) & 0xffff
        return crc;

    def checksum(self,str):
        """Returns the checksum of a string.""";
        #crcval=0;
        crcval=0xFFFF;
        for c in str:
            crcval=self.update_crc(crcval, ord(c));
        return crcval;

    def flip(self,c):
        """Flips the bit order, because that's what Fossil wants."""
        l=[0, 8, 4, 12, 2, 10, 6, 14, 1, 9, 5, 13, 3, 11, 7, 15];
        return ((l[c&0x0F]) << 4) + l[(c & 0xF0) >> 4];

    def test(self):
        return True;

def hex(str):
    """Returns the hex decoded version of a byte string."""
    toret="";
    if str==None: return "none";
    for c in str:
        toret="%s %02x" % (toret,ord(c));
    return toret;

class PingThreadMessage(threading.Thread):

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, verbose=None):
        threading.Thread.__init__(self, group=group, target=target, name=name,
                                  verbose=verbose)
        self.args = args
        self.kwargs = kwargs
        self.mw=kwargs.get('mw')
        return

    def run(self):
        print "pinging message "
        time.sleep(1)
        return

def main():
    #address is D0:37:61:C3:1A:EE
    watchaddr="D0:37:61:C3:1A:EE";
    if len(sys.argv)>1: watchaddr=sys.argv[1];
    mw=MetaWatch(watchaddr,debug=False);

    #mode=MODE_IDLE;
    mode=MODE_NOTIFICATION;
    
    mw.getBatteryVoltage()

    #mw.getButtonConfiguration(mode,0)

    mw.configureWatchMode(mode=mode, invertDisplay=False)

    # First, clear the draw buffer to a filled template.
    mw.clearbuffer(mode=mode,filled=False);

    imgfile="test.bmp";
    if len(sys.argv)>2:
        imgfile=sys.argv[2];

    mw.writeText(mode,"Medic Mode")

    #mw.enableButton(mode,BUTTON_A, BUTTON_TYPE_IMMEDIATE)
    #mw.enableButton(mode,BUTTON_B, BUTTON_TYPE_IMMEDIATE)
    #mw.enableButton(mode,BUTTON_C, BUTTON_TYPE_IMMEDIATE)
    #mw.enableButton(mode,BUTTON_D, BUTTON_TYPE_IMMEDIATE)
    #mw.enableButton(mode,BUTTON_E, BUTTON_TYPE_IMMEDIATE)
    #mw.enableButton(mode,BUTTON_F, BUTTON_TYPE_IMMEDIATE)

    #mw.disableButton(mode,BUTTON_A, BUTTON_TYPE_PRESSANDRELEASE)
    #mw.disableButton(mode,BUTTON_B, BUTTON_TYPE_PRESSANDRELEASE)
    #mw.disableButton(mode,BUTTON_C, BUTTON_TYPE_PRESSANDRELEASE)
  
    t=PingThreadMessage(kwargs={'mw':mw})
    t.start()

#mode=0
# mw.configureWatchMode(mode=mode, displayTimeout=100, invertDisplay=False)
    try:
        while True:
            mw.idle()
            #check command line input
            c = getkey()
            if c == 'q':     ## break on a Return/Enter keypress
               print 'Command Quit'
               break
            if c == 'v':     ## break on a Return/Enter keypress
               print 'Command Vibra'
               mw.buzz()
            if c == 'm':     ## break on a Return/Enter keypress
               print 'Medication reminder'
               mw.writeText(mode,"Diazepan \nDose: 10mg\n Due: 14.00")
               #mw.updatedisplay(mode)
            if c == 'r':     ## break on a Return/Enter keypress
               print 'Get RSSI'
               mw.getRSSI()
               
    except KeyboardInterrupt:
	print "Closed quickly"
	t.stop()
        mode=0
        mw.updatedisplay(mode)
        pass

    print "Connection was closed"
    mw.close();

if __name__ == '__main__':
    main()

