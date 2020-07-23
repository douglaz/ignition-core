#!/usr/bin/env python
import logging
import boto.ec2
import sys
import subprocess
import select
import time

logging.basicConfig(level=logging.INFO)

def get_active_instances(conn):
    active = [instance for res in conn.get_all_instances()
              for instance in res.instances
              if instance.state in set(['pending', 'running',
                                        'stopping', 'stopped'])]
    return active

def parse_nodes(active_instances, cluster_name):
    main_nodes = []
    subordinate_nodes = []
    for instance in active_instances:
        group_names = [g.name for g in instance.groups]
        if (cluster_name + "-main") in group_names:
            main_nodes.append(instance)
        elif (cluster_name + "-subordinates") in group_names:
            subordinate_nodes.append(instance)
    return (main_nodes, subordinate_nodes)

def get_mains(cluster_name, region):
    conn = boto.ec2.connect_to_region(region)

    active = get_active_instances(conn)
    main_nodes, subordinate_nodes = parse_nodes(active, cluster_name)
    return main_nodes

def get_active_nodes(cluster_name, region):
    conn = boto.ec2.connect_to_region(region)
    active = get_active_instances(conn)
    return parse_nodes(active, cluster_name)


def tag_instances(cluster_name, tags, region):
    conn = boto.ec2.connect_to_region(region)

    active = get_active_instances(conn)
    logging.info('%d active instances', len(active))

    main_nodes, subordinate_nodes = parse_nodes(active, cluster_name)
    logging.info('%d main, %d subordinate', len(main_nodes), len(subordinate_nodes))

    if main_nodes:
        conn.create_tags([i.id for i in main_nodes],
                         {'spark_node_type': 'main'})
    if subordinate_nodes:
        conn.create_tags([i.id for i in subordinate_nodes],
                         {'spark_node_type': 'subordinate'})

    if subordinate_nodes or main_nodes:
        ids = [i.id for l in (main_nodes, subordinate_nodes) for i in l]
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
            result.append(c)
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
        raise subprocess.CalledProcessError(p.returncode, args)
    return p.returncode

