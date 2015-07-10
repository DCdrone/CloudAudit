#!/usr/bin/python
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2015 UnionPay China .INC
# All Rights Reserved.
# Copyright 2015 
# version = 1.0

'''
	This python ha check project overwrites 
the old perl script. It will be easier for
us to manage it.
	'''

import os
import logging
import re
import socket
import time
import sys
from lib import servers

times = [6,0]
entryPoints = []
entryPoints.append(['1456.240.4.205','145.240.6.119','novaprod02','novaprod02','nova_prod_02'])
entryPoints.append(['1456.240.4.204','145.240.6.119','nova','nova','nova'])

def logger2():
	logger = logging.getLogger('HA-Check')
	logger.setLevel(logging.INFO)
	fh = logging.FileHandler('haCheck.log')
	fh.setLevel(logging.INFO)
	fh2 = logging.FileHandler('haCheck_error.log')
	fh2.setLevel(logging.ERROR)
	ch = logging.StreamHandler()
	ch.setLevel(logging.INFO)
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s [-] %(message)s')
	fh.setFormatter(formatter)
	ch.setFormatter(formatter)
	fh2.setFormatter(formatter)
	logger.addHandler(fh)
	logger.addHandler(fh2)
	logger.addHandler(ch)
	return logger

#
#Make sure haCheck_error.log includes latest error information!
#
errorFile = 'haCheck_error.log'        
if os.path.exists(errorFile):
	os.remove(errorFile)
haLog = logger2()

def zoneCheckPoints(zone,services,*args):
	'''
	This function is going to check HA configuration in zone aspect.
	Most of the information come from mysql or nova controller. It is 
	recommended to make this function a class to be organized better.
	
	zone is the same with avaliablity_zone in openstack. In our UnionPay,
	there're different nova controllers. Each has a mysql database and has
	a lot of avaliability zones. Each zone has a lot of compute nodes
	to support virtual servers' running. Many functions of our cloud
	is devided into zones, like HA, migrating.
	'''

	zone = zone
	services = services
	zoneCheck = 1
	novaIp = args[0]
#-------------------------------------
#[01] check service in XXX status 
#-------------------------------------
	for service in services:
		m = re.search(zone.name,service)
		if m is not None:
			info = zone.name+' has a bad service:'+service+'. \
You could login stack@'+novaIp+' \
and execute \'source /opt/upInstall/env;nova-manage service list\'. \
Ignore all compute nodes check points.'
			haLog.error(info)
			zoneCheck = 0
	#if zone.name == 'Test-CLUSTER05' or zone.name == 'Test-CLUSTER00':
	#	zoneCheck = 1
	if zoneCheck:
		pass
	else:
		return 0
#-------------------------------------
#[02] check zone's HA status is on 
#-------------------------------------
	if zone.isHa():
		pass
	else:
		info = zone.name+' is not in HA zone. \
You could login stack@'+novaIp+' \
and execute \'source /opt/upInstall/env;nova-manage hazone-list\'\
Ignore all compute nodes check Points.'
		haLog.error(info)
		zoneCheck = 0

	#if zone.name == 'Test-CLUSTER05' or zone.name == 'Test-CLUSTER00':
	#	zoneCheck = 1
	if zoneCheck:
		pass
	else:
		return 0
#-------------------------------------
#[03] nodes in a zone should >=3
#-------------------------------------
	if len(zone.getComputeNodes())<3:
		info = zone.name+' has less than 3 compute nodes. \
Ignore all compute nodes check Points.'
		haLog.error(info)
		zoneCheck = 0

	#if zone.name == 'Test-CLUSTER05' or zone.name == 'Test-CLUSTER00':
	#	zoneCheck = 1
	if zoneCheck:
		pass
	else:
		return 0
#-------------------------------------
#[04] check every compute's ip 
#-------------------------------------
	for computeNode in zone.getComputeNodes():
		if not computeNode.ipMngCheck():
			haLog.error(zone.name+' '+computeNode.name+' missed its manage IP address! Ignore all checks on it!') 

	#if zone.name == 'Test-CLUSTER05':
	#	zoneCheck = 1
	if zoneCheck:
		pass
	else:
		return 0

#-------------------------------------
#[05] check available resources
#-------------------------------------
	resources = zone.getResources()
	block = 0
	targetBlock = 4
	blockSize = 8192
	if zone.name =='APP-CLUSTER09' or zone.name == 'APP-CLUSTER10':
		blockSize = 16384
		targetBlock = 3
	for computeName in resources.keys():
		if(resources[computeName] > 0):
			block += int(resources[computeName]/blockSize)
	if block >= targetBlock:
		info = zone.name+' has enough resources for HA! Remain: '+str(blockSize)+'Mb * '+str(block)
		haLog.info(info)
	else:
		info = zone.name+' has not enough resources for HA! Remain: '+blockSize+'Mb * '+block 
		haLog.info(info)
		zoneCheck = 0
		
	#if zone.name == 'Test-CLUSTER05':
	#	zoneCheck = 1
	if zoneCheck:
		pass
	else:
		return 0

#-------------------------------------
#[06] check firewall
#-------------------------------------
	pmIps = []
	for computeNode in zone.getComputeNodes():
		pmIps.append(computeNode.ipMng)
	for pmIp in pmIps:
		try:
			sc = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
			ip = pmIp
			port = 22
			sc.settimeout(2)
			sc.connect((ip,port))
			info = zone.name+' server ip '+pmIp+'\'s port 22 is OK!'
			haLog.info(info)
		except Exception, e:
			exception = str(e)
			if re.search('connection refused',exception,re.I) is not None: 
				info = zone.name+' server ip '+pmIp+'\'s port 22 refused our connection! Please check firewall!'
				haLog.error(info)
				zoneCheck = 0
		finally:
			sc.close()
		
	vmIps = zone.getVmIps()
	for vmIp in vmIps:
		try:
			sc = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
			ip = vmIp
			port = 22
			sc.settimeout(2)
			sc.connect((ip,port))
			info = zone.name+' vm ip '+vmIp+'\'s port 22 is OK!'
			haLog.info(info)
		except Exception, e:
			exception = str(e)
			if re.search('connection refused',exception,re.I) is not None: 
				info = zone.name+' vm ip '+vmIp+'\'s port 22 refused our connection! Please check firewall!'
				haLog.error(info)
				zoneCheck = 0
			elif re.search('timed out',exception,re.I) is not None: 
				info = zone.name+' vm ip '+vmIp+'\'s port 22 timed out! Don\'t care it!'
				haLog.info(info)
			else:
				info = zone.name+' vm ip '+vmIp+'\'s port 22 something wrong! Don\'t care it!'
				haLog.info(info)
		finally:
			sc.close()

	#if zone.name == 'Test-CLUSTER05':
	#	zoneCheck = 1
	if zoneCheck:
	 	return 1	
	else:
		return 0

preMountPoint = {}

def computeNodeCheckPoints(computenode,etcHosts,resource):

	'''
	After we scanned HA configuration in zone aspect, we
	are going to scan every compute node for their configuration.
	Lots of configuration in a compute node are neccessary.
	Any wrong configuration leads to some fatal problem in
	our cloud platform.

	A compute node is a physical server where virtual servers run on.
	Until now, no checking point is associated with virtual servers.

	In order to make less influence on physical servers especially 
	to avoid problem caused by ssh, we combine all the commands together
	and run in remote server in a single SSH connection.

	This function is recommended to be a class in later version.
	'''

	computeNode = computenode
	computeNode.xmListLoad()
	computeNode.dfLoad()
	computeNode.hostsLoad()
	#computeNode.ntpdLoad()
	computeNode.xmInfoLoad()

	###################################
    #    Load command before fetch    #
    ###################################

	computeNode.fetch()
	errorFound = 0

	###################################
    #    Get information after fetch  #
    ###################################

	#mem = computeNode.getDomain0Mem()
	#print '---------------------------------'+computeNode.hostName,mem
	#mount = computeNode.getDsx01()
	#for key in mount:
		#print key,mount[key]
	#hosts = computeNode.getHosts()
				#for key in hosts:
				#	print key,hosts[key]

#-------------------------------------
#[01] check whether ntpd service is on
#-------------------------------------
#	ntpd =  computeNode.getNtpd()
#	if not ntpd:
#		info = computeNode.name+'['+computeNode.ipMng+'] ntpd service is off.'
#		haLog.error(info)
#This ntp service is depreciated.
			
#-------------------------------------
#[01] check domain0's memory 
#-------------------------------------
	dom0Mem = computeNode.getDomain0Mem()
	if dom0Mem == '' :
		info = computeNode.name+'['+computeNode.ipMng+'] stack seems has no sudo priviledge.'
		haLog.error(info)
		errorFound += 1
	elif int(dom0Mem) < 2500 or int(dom0Mem) > 5000:
		info = computeNode.name+'['+computeNode.ipMng+'] domain0\'s memory is out of range(2500-5000).'
		haLog.error(info)
		errorFound += 1 
	else:
		info = computeNode.name+'['+computeNode.ipMng+'] domain0\'s memory '+dom0Mem+'Mb is OK!'
		haLog.info(info)

#-------------------------------------
#[02] check domain resources 
#-------------------------------------
	[totalMem,usedMem] = computeNode.getMem()
	if totalMem == 0:
		info = computeNode.name+'['+computeNode.ipMng+'] stack seems has no sudo priviledge.'
		haLog.error(info)
		errorFound += 1 
	else:
		freeMem = int(totalMem) - int(usedMem)
		if computeNode.name in resource.keys():
			if (resource[computeNode.name] - freeMem) > 512:
				info = computeNode.name+'['+computeNode.ipMng+'] free memory is less than expected in database. Check whether there\'s unauthorized vm in it.'
				haLog.error(info)
				errorFound += 1 
			elif (freeMem - resource[computeNode.name] > 512):
				info = computeNode.name+'['+computeNode.ipMng+'] free memory is more than expected in database.'
				haLog.warning(info)
			else:
				info = computeNode.name+'['+computeNode.ipMng+'] free memory is the same with database.'
				haLog.info(info)
		else:
			info = computeNode.name+'['+computeNode.ipMng+'] resources is missed in database.'
			haLog.warning(info)

#-------------------------------------
#[03] check /dsx01 
#-------------------------------------
	mountPoint = computeNode.getDsx01()
	mountPointCheck = 1
	global preMountPoint
	if mountPoint:
		if not preMountPoint:
			for key in mountPoint.keys():
				preMountPoint[key] = mountPoint[key]
		if len(preMountPoint.keys()) == len(mountPoint.keys()):
			for key in mountPoint.keys():
				if preMountPoint[key] != mountPoint[key]:
					mountPointCheck = 0
		else:
			mountPointCheck = 0
		if mountPointCheck == 1:
			info = computeNode.name+'['+computeNode.ipMng+'] nas /dsx01 is OK.'
			haLog.info(info)
		else:
			info = computeNode.name+'['+computeNode.ipMng+'] nas mounting point is different from the first one.'
			haLog.error(info)
			errorFound += 1
	else:
		info = computeNode.name+'['+computeNode.ipMng+'] stack seems has no sudo priviledge or /dsx01 is missed!.'
		haLog.error(info)
		errorFound += 1 
		

#-------------------------------------
#[04] check /etc/hosts
#-------------------------------------
	etcHostsCheck = 1
	hosts = computeNode.getHosts()
	keyError = ''
	if hosts:
		for key in etcHosts.keys():
			if key in hosts.keys():
				if hosts[key] != etcHosts[key]:
					etcHostsCheck = 0
					keyError = key+'-ipwrong'
			else:
				etcHostsCheck = 0
				keyError = key+'-missed'
		if etcHostsCheck == 1:
			info = computeNode.name+'['+computeNode.ipMng+'] /etc/hosts is OK.'
			haLog.info(info)
		else:
			info = computeNode.name+'['+computeNode.ipMng+'] /etc/hosts lacks some hosts. Hint:'+keyError
			haLog.error(info)
			errorFound += 1 
	else:
		info = computeNode.name+'['+computeNode.ipMng+'] stack seems has no sudo priviledge or it does not have any content in /etc/hosts.'
		haLog.error(info)
		errorFound += 1 

	if errorFound != 0:
		return 0
	else:
		return 1


def startChecking(entryPoints):		

	'''
	This function begins HA checking by entryPoints. EntryPoints
	are information related to nova controllers. Each nova controller
	is an entryPoint for us to start our scanning. We get some 
	information in a remote nova node and get others from the nova's
	mysql database.

	So, let's see our scanning routes:
	[nova && mysql] -> [every zone] -> [ever server]	
	'''
	
	errorFound = 0
		
	for entryPoint in entryPoints:

		novaIp = entryPoint[0]
		dbIp = entryPoint[1]
		dbUser = entryPoint[2]
		dbPasswd = entryPoint[3]
		dbName = entryPoint[4]

		controlNodes = servers.ControlNodes(novaIp,dbIp,dbUser,dbPasswd,dbName)
		services = controlNodes.serviceCheck()
		zones = controlNodes.getAvailabilityZone()

		for zone in zones:
			resource = zone.getResources()
			zoneCheck = zoneCheckPoints(zone,services,novaIp)                              #avaliablity zone check points

			#if zone.name == 'Test-CLUSTER05':                                              #This is just for pit 
			#	zoneCheck = 1
			if zoneCheck:                                                                  #check compute nodes' configuration only if zone check passed
				global preMountPoint
				preMountPoint = {}
				zoneEtcHosts = {}
				for computeNode in zone.getComputeNodes():
					zoneEtcHosts[computeNode.name] = computeNode.ipMng
			
				for computeNode in zone.getComputeNodes():
					#if computeNode.name == 'B0310011' or computeNode.name == 'B0310015':   #ignore some bad nodes
					#	continue
					if computeNodeCheckPoints(computeNode,zoneEtcHosts,resource) == 0:     #compute nodes check points
						errorFound += 1
			else:
				errorFound += 1

	if errorFound != 0:
		return 0
	else:
		return 1

if __name__ == '__main__':
	if len(sys.argv) > 1:
		MODE = sys.argv[1]                                       # The script will only run once in test mode and would not trigger patrol
	else:
		MODE = 'stantdard'

	if MODE == 'test':
		errorFound = startChecking(entryPoints)
	elif MODE == 'help':
		print 'Run command like [./haCheck.py test]. It will scan our cloud once and will not trigger Patrol. Run command like [nohup ./haCheck &] will scan our cloud every day in a desired time and may trigger Patrol.'
	elif MODE =='version' or MODE == 'V':
		print 'Version V1.0\nUnionPay Reserved'
	else:
		while True:
			if time.localtime().tm_hour == times[0] and time.localtime().tm_min == times[1]:
				print 'Time is '+str(time.localtime().tm_hour)+':'+str(time.localtime().tm_min)+'. We should start our scanning!'
				if startChecking(entryPoints) == 1:
					pass
				else:
					print 'We are writing log in a file which is under Patrol\'s awareness!'
					triggerPatrol = open('../uncheck.log','a')
					info = '['+time.asctime()+'][ERROR] When we were scanning some configuration of UPCLOUD, we found some errors! Please open file ./cloud_check/haCheck_error.log for details!'
					triggerPatrol.write(info+"\n")
					triggerPatrol.close()
					pass
			else:
				print 'Time is '+str(time.localtime().tm_hour)+':'+str(time.localtime().tm_min)+':'+str(time.localtime().tm_sec)+'. We only start scanning at '+str(times[0])+':'+str(times[1])+'.'
				time.sleep(1)
				
		
