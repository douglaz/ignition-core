#!/usr/bin/env python
import ast
import logging
from pprint import pprint
import boto.ec2
import sys
import subprocess
import select
import time
import json
from os.path import exists
from os import makedirs
import os

# get a folder_log_path from env variable
folder_log_path = os.getenv('LOG_FOLDER')

logging.basicConfig(level=logging.INFO)

def get_active_instances(conn):
    active = [instance for res in conn.get_all_instances()
              for instance in res.instances
              if instance.state in set(['pending', 'running',
                                        'stopping', 'stopped', 'shutting-down'])]
    return active

def parse_nodes(active_instances, cluster_name):
    master_nodes = []
    slave_nodes = []
    for instance in active_instances:
        group_names = [g.name for g in instance.groups]
        # This can handle both spark-ec2 and flintrock clusters
        if (cluster_name + "-master") in group_names or (("flintrock-" + cluster_name) in group_names and instance.tags.get('flintrock-role') == 'master'):
            master_nodes.append(instance)
        elif (cluster_name + "-slaves") in group_names or (("flintrock-" + cluster_name) in group_names and instance.tags.get('flintrock-role') in ('slave', None)):
            slave_nodes.append(instance)
    return (master_nodes, slave_nodes)

def get_masters(cluster_name, region):
    conn = boto.ec2.connect_to_region(region)

    active = get_active_instances(conn)
    master_nodes, slave_nodes = parse_nodes(active, cluster_name)
    return master_nodes

def get_active_nodes(cluster_name, region):
    conn = boto.ec2.connect_to_region(region)
    active = get_active_instances(conn)
    return parse_nodes(active, cluster_name)


def get_active_nodes_by_tag(region, tag_name, tag_value):
    conn = boto.ec2.connect_to_region(region)
    filter = {"tag:{0}".format(tag_name):["{0}".format(tag_value)], "instance-state-name":["running"]}
    return conn.get_only_instances(filters=filter)

def get_fleet_id_by_cluster_name(cluster_name):
    # create a array with the requests ids
    fleet_id = ''
    file_name = '{0}.json'.format(cluster_name)

    if folder_log_path:
        # check if the folder exists and if not create it
        if not exists(folder_log_path):
            makedirs(folder_log_path)
    
        file_name = '{0}/{1}.json'.format(folder_log_path, cluster_name)

    # verify if the file exists
    if exists(file_name):
        # open a json log file if exists
        with open(file_name) as json_file:# deserialize the json file to object
            json_content = json.load(json_file)
            
            # create a array with the requests ids
            for request in json_content:
                fleet_id = str(request['FleetId'])

    return fleet_id


def destroy_by_fleet_id(region, cluster_name):
    conn = boto.ec2.connect_to_region(region)
    fleet_instances_ids = []
    instances = []
    
    try:
        # get requets ids from json log file
        fleet_id = get_fleet_id_by_cluster_name(cluster_name)
        logging.info('The fleet id found in json log file: {0}'.format(fleet_id))
        
        # call an external script to delete the fleet and retrieve the list of instances
        delete_fleet_script = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'delete_fleet.py')
        process = subprocess.Popen(["python3", delete_fleet_script, region, fleet_id], stdout=subprocess.PIPE)
        stdout_str = process.communicate()[0]

        # the subprocess return a string with the character '\n' separating the delete message and the list of instances 
        stdout_str_split = stdout_str.split('\n')

        # message of fleet deletion
        deleted_fleet = stdout_str_split[0]
        logging.info(deleted_fleet)

        # getting the list of the string containing the list of istances
        # e.g."['i-0e90a67a64693dc39', 'i-00889275ebe58bb7b', 'i-0982e3e6728044bef']"
        fleet_instances = ast.literal_eval(stdout_str_split[1])
        fleet_instances_ids.extend(fleet_instances)

        # test if the instance id is not empty
        if len(fleet_instances_ids) > 0:
            instances_requested = conn.get_only_instances(fleet_instances_ids)

            # terminate instances from request spot
            for instance in instances_requested:
                # checking again if the object is in the list to not terminate wrong machines
                if fleet_instances_ids.index(instance.id) > -1:
                    if instance.state == 'running':
                        logging.info('Terminating instance: {0}'.format(instance.id))
                        # add only instances that are running to return list
                        instances.append(instance)
                        # terminate the instance
                        instance.terminate()
                    elif instance.state == 'shutting-down':
                        # add the instance to the wait list
                        instances.append(instance)

    except Exception as e:
        logging.error(e)
        logging.error('Error to destroy cluster {0} by request ids.'.format(cluster_name))
        pass

    return instances


def tag_instances(cluster_name, tags, region):
    conn = boto.ec2.connect_to_region(region)

    active = get_active_instances(conn)
    logging.info('%d active instances', len(active))

    master_nodes, slave_nodes = parse_nodes(active, cluster_name)
    logging.info('%d master, %d slave', len(master_nodes), len(slave_nodes))

    if master_nodes:
        conn.create_tags([i.id for i in master_nodes],
                         {'spark_node_type': 'master'})
    if slave_nodes:
        conn.create_tags([i.id for i in slave_nodes],
                         {'spark_node_type': 'slave'})

    if slave_nodes or master_nodes:
        ids = [i.id for l in (master_nodes, slave_nodes) for i in l]
        conn.create_tags(ids, tags)

    logging.info("Tagged nodes.")

class ProcessTimeoutException(Exception): pass

def read_from_to(_from, to):
    data = read_non_blocking(_from)
    read_data = False
    while data is not None:
        read_data = True
        to.write(data)
        data = read_non_blocking(_from)
    to.flush()
    return read_data

def read_non_blocking(f):
    result = []
    while select.select([f], [], [], 0)[0]:
        c = f.read(1)
        if c:
            result.append(c.decode('utf-8'))
        else:
            break
    return ''.join(result) if result else None

def check_call_with_timeout(args, stdin=None, stdout=None,
                            stderr=None, shell=False,
                            timeout_total_minutes=0,
                            timeout_inactivity_minutes=0):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    begin_time_total = time.time()
    begin_time_inactivity = time.time()
    p = subprocess.Popen(args,
                         stdin=stdin,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=shell,
                         universal_newlines=False)
    while True:
        if read_from_to(p.stdout, stdout):
            begin_time_inactivity = time.time()
        if read_from_to(p.stderr, stderr):
            begin_time_inactivity = time.time()
        if p.poll() is not None:
            break
        terminate_by_total_timeout = timeout_total_minutes > 0 and time.time() - begin_time_total > (timeout_total_minutes * 60)
        terminate_by_inactivity_timeout = timeout_inactivity_minutes > 0 and time.time() - begin_time_inactivity > (timeout_inactivity_minutes * 60)
        if terminate_by_inactivity_timeout or terminate_by_total_timeout:
            p.terminate()
            for i in range(100):
                if p.poll is not None:
                    break
                time.sleep(0.1)
            p.kill()
            message = 'Terminated by inactivity' if terminate_by_inactivity_timeout else 'Terminated by total timeout'
            raise ProcessTimeoutException(message)
        time.sleep(0.5)
    read_from_to(p.stdout, stdout)
    read_from_to(p.stderr, stderr)
    if p.returncode != 0:
        stdall = 'STDOUT:\n{}\nSTDERR:\n{}'.format(stdout, stderr)
        raise subprocess.CalledProcessError(p.returncode, args, output=stdall)
    return p.returncode

def check_call_with_timeout_describe(args, stdin=None, stdout=None,
                        stderr=None, shell=False,
                        timeout_total_minutes=0,
                        timeout_inactivity_minutes=0):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    begin_time_total = time.time()
    begin_time_inactivity = time.time()
    p = subprocess.Popen(args,
                         stdin=stdin,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=shell,
                         universal_newlines=False)
    while True:
        if read_from_to(p.stdout, stdout):
            begin_time_inactivity = time.time()
        if read_from_to(p.stderr, stderr):
            begin_time_inactivity = time.time()
        if p.poll() is not None:
            break
        terminate_by_total_timeout = timeout_total_minutes > 0 and time.time() - begin_time_total > (timeout_total_minutes * 60)
        terminate_by_inactivity_timeout = timeout_inactivity_minutes > 0 and time.time() - begin_time_inactivity > (timeout_inactivity_minutes * 60)
        if terminate_by_inactivity_timeout or terminate_by_total_timeout:
            p.terminate()
            for i in range(100):
                if p.poll is not None:
                    break
                time.sleep(0.1)
            p.kill()
            message = 'Terminated by inactivity' if terminate_by_inactivity_timeout else 'Terminated by total timeout'
            raise ProcessTimeoutException(message)
        time.sleep(0.5)
    read_from_to(p.stdout, stdout)
    read_from_to(p.stderr, stderr)
    if p.returncode != 0:
        stdall = 'STDOUT:\n{}\nSTDERR:\n{}'.format(stdout, stderr)
        raise subprocess.CalledProcessError(p.returncode, args, output=stdall)
    if len(args) > 5:
        return args[5] 
