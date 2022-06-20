#!/usr/bin/env python
import logging
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

def get_requests_ids_by_cluster_name(cluster_name):
    # create a array with the requests ids
    requests_ids = []
    folder_full_path = os.path.abspath(os.getcwd())

    if folder_log_path:
        # check if the folder exists and if not create it
        folderExist = exists(folder_log_path)

        if folderExist != True:
            makedirs(folder_log_path)
    
        file_name = '{0}/{1}.json'.format(folder_log_path, cluster_name)
    else:
        file_name = '{0}.json'.format(cluster_name)

    # verify if the file exists
    file_exists = exists(file_name)
    
    if file_exists:
        # open a json log file if exists
        json_file = open(file_name)

        # deserialize the json file to object
        json_content = json.load(json_file)

        # create a array with the requests ids
        for request_id in json_content:
            requests_ids.append(str(request_id['SpotInstanceRequestId']))

    return requests_ids


def destroy_by_request_spot_ids(region, cluster_name):
    conn = boto.ec2.connect_to_region(region)
    instances = []
    
    try:
        # get requets ids from json log file
        request_ids = get_requests_ids_by_cluster_name(cluster_name)
        logging.info('The amount of requests ids found in json log file: {0}'.format(len(request_ids)))
        instances_cancelled = []
        
        # test if the request has any id
        if len(request_ids) > 0:
            spot_requests = conn.get_all_spot_instance_requests()
            for request in request_ids:
                for spot_request in spot_requests:                    
                    if request == spot_request.id:
                        # cancel the requests returned before
                        conn.cancel_spot_instance_requests(request)
                        instances_cancelled.append(spot_request)

            # verify if the cancelled list is not empty
            if len(instances_cancelled) > 0:
                instances_ids = []
        
                # create the instance list of machines based on requests ids
                for request_cancelled in instances_cancelled:
                    if request_cancelled.instance_id:
                        instances_ids.append(request_cancelled.instance_id)
                
                # test if the instance id is not empty
                if len(instances_ids) > 0:
                    instances_requested = conn.get_only_instances(instances_ids)

                    # terminate instances from request spot
                    for instance in instances_requested:
                        # checking again if the object is in the list to not terminate wrong machines
                        if instances_ids.index(instance.id) > -1:
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
