#!/usr/bin/python 
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2015 UnionPay China .INC
# All Rights Reserved.
# Copyright 2015 

'''This is only version 0.1 now. DC will
keep overwriting it to make it better. Any 
usefull suggestion is welcomed
'''
import os
import MySQLdb
import time
import signal
import logging
import re
import socket

def logger():
	logger = logging.getLogger('servers.remote')
	logger.setLevel(logging.DEBUG)
	fh = logging.FileHandler('remote.log')
	fh.setLevel(logging.DEBUG)
	ch = logging.StreamHandler()
	ch.setLevel(logging.DEBUG)
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s [-] %(message)s')
	fh.setFormatter(formatter)
	ch.setFormatter(formatter)
	logger.addHandler(fh)
	logger.addHandler(ch)
	return logger

cmdLog = logger()

class Remote:
	'''
	Run some command in a remote node. 
It depends on ssh with no passwd. Remenber
that! If connection has been timedout, it
would prefer it a bad node.
	'''

	def __init__(self,ip="",cmd="",timeOut=3,user='stack'):
		self.ip = ip
		self.cmd = cmd
		self.timeOut = timeOut
		self.user = user 

	def execute(self,cmd=""):
		if not cmd:
			pass
		else:
			self.cmd = cmd
		def handler(signum,frame):
			raise AssertionError
		try:
			signal.signal(signal.SIGALRM,handler)
			signal.alarm(self.timeOut)
			command = 'ssh '+self.user+'@'+self.ip+' '+'\''+self.cmd+'\''+' 2>&1'
			output = os.popen(command).readlines()	
			signal.alarm(0)
			cmdLog.info(command+' successfully!')
		except AssertionError:
			output = 'timeout'
			cmdLog.error(command+' timeout!')
		return output

class ControlNodes:
	'''
	Control nodes represent nova nodes. It gets 
neccessary infomation to report the whole clusters' 
status and provides some methods for us to get 
different clusters and check HA status. Finally we 
get compute nodes from every cluster.
	'''
	
	def __init__(self,novaIp="",dbIp="",dbUser="",dbPasswd="",dbName=""):
		self.novaIp = novaIp
		self.dbIp = dbIp
		self.dbUser = dbUser
		self.dbPasswd = dbPasswd
		self.dbName = dbName

	def serviceCheck(self):
		'''
		This method is temporary. As we could caculate the state from 
		database, we could provide a better performance. However, we 
		did not know how to do it. This method return an array which
		is just strings in it to avoid confusion with other instances.
		'''
		remote = Remote(ip=self.novaIp,cmd='source /opt/upInstall/env;nova-manage service list')
		tmp = remote.execute()
		service = []
		if type(tmp) == type(''):
			return tmp	
		else:
			for line in tmp:
				line = line.strip('\n')
				m = re.search('nova-compute\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',line,re.I)
				if m is not None:
					host = m.group(1)
					cluster = m.group(2)
					status = m.group(3)
					state = m.group(4)
					haState = m.group(5)
					if (state == 'XXX' or status == 'disabled'):
						str = host+' '+cluster+' '+status+' '+state+' '+haState 
						service.append(str)
		return service
	
	def getAvailabilityZone(self):
		availabilityZones = []
		try:
			conn = MySQLdb.connect(host=self.dbIp,user=self.dbUser,passwd=self.dbPasswd,db=self.dbName)
			cur = conn.cursor()
			num = cur.execute('select distinct(availability_zone) from services where topic=\'compute\' and deleted=0 order by availability_zone')
			info = cur.fetchmany(num)
			cur.close()
			conn.close()
		except MySQLdb.Error,e:
			cmdLog.error('Mysql DB is not reachable!'+' '+self.dbIp+' '+self.dbName)
			return 'dbTimeOut'
		else:
			for line in info:
				availabilityZone = AvailabilityZone(name=line[0],dbIp=self.dbIp,dbUser=self.dbUser,dbPasswd=self.dbPasswd,dbName=self.dbName)
				availabilityZones.append(availabilityZone)
			return availabilityZones
			

class AvailabilityZone():
	'''
	This concept exactly corresponds with OpenStack.
	'''
	
	def __init__(self,name='',dbIp='',dbUser='',dbPasswd='',dbName=''):
		self.name = name
		self.dbIp = dbIp
		self.dbUser = dbUser
		self.dbPasswd = dbPasswd
		self.dbName = dbName

	def isHa(self):
		try:
			conn = MySQLdb.connect(host=self.dbIp,user=self.dbUser,passwd=self.dbPasswd,db=self.dbName)
			cur = conn.cursor()
			sql = 'select is_ha,except_hosts from up_ha_zones where name=\''+self.name+'\' and deleted=0'
			num = cur.execute(sql)
			info = cur.fetchmany(num)
			cur.close()
			conn.close()
		except MySQLdb.Error,e:
			cmdLog.error('Mysql DB is not reachable!'+' '+self.dbIp+' '+self.dbName)
			return 'dbTimeOut'
		else:
			if len(info):
				ha = info[0][0] 
			else:
				ha = 0
			return ha		

	def getComputeNodes(self):
		try:
			conn = MySQLdb.connect(host=self.dbIp,user=self.dbUser,passwd=self.dbPasswd,db=self.dbName)
			cur = conn.cursor()
			sql = 'SELECT host,ip_mng,availability_zone FROM services where availability_zone=\''+self.name+'\' and topic=\'compute\' and deleted=0 order by host;' 
			num = cur.execute(sql)
			info = cur.fetchmany(num)
			cur.close()
			conn.close()
		except MySQLdb.Error,e:
			cmdLog.error('Mysql DB is not reachable!'+' '+self.dbIp+' '+self.dbName)
			return 'dbTimeOut'
		else:
			computeNodes = []
			if len(info):
				for line in info:
					hostname = line[0]
					if line[1] is not None:
						ipmng = line[1]
					else:
						ipmng = ''
					computeNode = ComputeNodes(hostname,ipmng)
					computeNodes.append(computeNode)
			return computeNodes

	def getResources(self):
		try:
			conn = MySQLdb.connect(host=self.dbIp,user=self.dbUser,passwd=self.dbPasswd,db=self.dbName)
			cur = conn.cursor()
			sql = 'SELECT services.host,services.ip_mng,compute_nodes.memory_mb,compute_nodes.free_ram_mb from compute_nodes,services where compute_nodes.service_id = services.id and services.availability_zone=\''+self.name+'\' and services.deleted=0 and compute_nodes.deleted=\'0\'  and services.topic=\'compute\' order by services.host;' 
			num = cur.execute(sql)
			info = cur.fetchmany(num)
			cur.close()
			conn.close()
		except MySQLdb.Error,e:
			cmdLog.error('Mysql DB is not reachable!'+' '+self.dbIp+' '+self.dbName)
			return 'dbTimeOut'
		else:
			if len(info):
				resource = {}
				for line in info:
					hostname = line[0]
					freeMem = line[3]
					resource[hostname] = freeMem
			return resource

	def getVmIps(self):
		try:
			conn = MySQLdb.connect(host=self.dbIp,user=self.dbUser,passwd=self.dbPasswd,db=self.dbName)
			cur = conn.cursor()
			sql = 'SELECT address FROM fixed_ips,instances where fixed_ips.instance_id=instances.id and instances.availability_zone=\''+self.name+'\';' 
			num = cur.execute(sql)
			info = cur.fetchmany(num)
			cur.close()
			conn.close()
		except MySQLdb.Error,e:
			cmdLog.error('Mysql DB is not reachable!'+' '+self.dbIp+' '+self.dbName)
			return 'dbTimeOut'
		else:
			vmIps = []
			if len(info):
				for line in info:
					ip = line[0]
					vmIps.append(ip)
			return vmIps
		

class ComputeNodes():
	'''
	Each one represents a compute node. We get everythin 
	we want from a compute node. If more check points are
	needed, just put more methods in this class.
	'''

	def __init__(self,hostname='',ipmng=''):
		self.hostName = hostname
		self.name = hostname
		self.ipMng = ipmng
		self.cmd = ''
		self.blockInfo = [] 

	def ipMngCheck(self):
		if re.search('\d+\.\d+\.\d+\.\d+',self.ipMng) is not None:
			return 1
		else:
			return 0
	
	def fetch(self):
		if not self.ipMngCheck():
			return 0
		remote = Remote(self.ipMng,self.cmd)
		content = remote.execute()
		blockStart = 0
		block = []
		for line in content:
			line = line.strip('\n')
			if blockStart:
				block.append(line)
			if re.search('--------',line) is not None:
				blockStart = 1
			if re.search('@@@@@@@@',line) is not None:
				blockStart = 0
				self.blockInfo.append(block)
				block = []
		return 1
			
	
	def addSplit(self,command):
		self.cmd = self.cmd + 'echo \'--------\';' + command + ';echo \'@@@@@@@@\';'
	
	def findSplit(self,format):
		targetBlock = []
		formatter = ''
		length = len(format)
		i = 0
		for line in format:
			i = i + 1
			if i == len(format):
				formatter = formatter + line
			else:
				formatter = formatter + line + '\\s+'
		for block in self.blockInfo:
			isThis = 0
			for line in block:
				if re.search(formatter,line,re.I) is not None:
					isThis = 1
					break
			if isThis == 1:
				targetBlock = block
				break
		return targetBlock
		

	def xmListLoad(self):
		self.addSplit('sudo /usr/sbin/xm list')

	def getDomain0Mem(self):
		memory = '' 
		block = self.findSplit(['name','id','mem','vcpus','state','time'])
		if block:
			for line in block:
				m = re.search('domain-0\s+\d+\s+(\d+)\s+\d+',line,re.I)
				if m is not None:
					memory = m.group(1)
					break
		return memory

	def xmInfoLoad(self):
		self.addSplit('echo \'xm_info\';sudo /usr/sbin/xm info')

	def getMem(self):
		totalMem = 0
		usedMem = 0
		block = self.findSplit(['xm_info'])
		if block:
			for line in block:
				m = re.search('total_memory\s+:\s+(\d+)',line)
				if m is not None:
					totalMem = m.group(1)
		block = self.findSplit(['name','id','mem','vcpus','state','time'])
		if block:
			for line in block:
				m = re.search('\S+\s+\d+\s+(\d+)\s+\d+\s+\S+---',line)
				if m is not None:
					usedMem += int(m.group(1))
		return [int(totalMem),usedMem]
		pass
		
	def dfLoad(self):
		self.addSplit('sudo df -h')

	def getDsx01(self):
		mountPoint = {} 
		block = self.findSplit(['filesystem','size','used','avail'])	
		if block:
			for line in block:
				if re.search('\s+/dsx01',line):
					m = re.search('(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',line)
					point = m.group(6)
					device = m.group(1)
					mountPoint[point] = device
		return mountPoint

	def hostsLoad(self):
		self.addSplit('echo \'etc_hosts\';sudo cat /etc/hosts')

	def getHosts(self):
		hosts = {}
		block = self.findSplit(['etc_hosts'])
		if block:
			for line in block:
				m = re.search('(\d+\.\d+\.\d+\.\d+)\s+(\S+)',line)
				if m is not None:
					ip = m.group(1)
					host = m.group(2)
					hosts[host] = ip
		return hosts

	def ntpdLoad(self):
		self.addSplit('echo ntpd_check;ps -ef|grep ntpd|grep -v grep')

	def getNtpd(self):
		ntpdOn = 0
		block = self.findSplit(['ntpd_check'])
		if block:
			for line in block:
				m = re.search('/usr/sbin/ntpd',line)
				if m is not None:
					return 1
		return 0

 
		 
if __name__ == '__main__':	
	controlNodes = ControlNodes('146.240.105.242','146.240.104.7','nova','nova','nova')
	services = controlNodes.serviceCheck()
	zones = controlNodes.getAvailabilityZone()
	for zone in zones:
		zoneCheck = '1'
		#print 'Checking -----------'+zone.name
		for service in services:
			m = re.search(zone.name,service)
			if m is not None:
				#print service+" bad service"
				zoneCheck = 0
		if zone.isHa():
			pass
			#for computeNode in zone.getComputeNodes():
			#	print computeNode.hostName,computeNode.ipMng
		
		else:
			#print zone.name+' is not in HA zone!'
			zoneCheck = 0
		if zone.name == 'Test-CLUSTER08':
			zoneCheck = 1
		if zoneCheck:
			#print 'We can check '+zone.name+' right now!'
			for computeNode in zone.getComputeNodes():
				if computeNode.name == 'B0310001' or computeNode.name == 'B0310003':
					continue
				#print computeNode.hostName,computeNode.ipMng
				if not computeNode.ipMngCheck():
					print computeNode.hostName+' missed ip'
				else:
					computeNode.xmListLoad()
					computeNode.dfLoad()
					computeNode.hostsLoad()
					computeNode.ntpdLoad()
					computeNode.xmInfoLoad()
					computeNode.fetch()
					mem = computeNode.getDomain0Mem()
					print '---------------------------------'+computeNode.hostName,mem
					mount = computeNode.getDsx01()
					for key in mount:
						print key,mount[key]
					hosts = computeNode.getHosts()
					for key in hosts:
						print key,hosts[key]
					ntpd =  computeNode.getNtpd()
					if ntpd:
						print computeNode.name+' ntp is on!'
					else:
						print computeNode.name+' ntp is off'
					memory = computeNode.getMem()
					print memory
		else:
			pass
			#print 'Skipping '+zone.name+' ..........'
