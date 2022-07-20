import sys
from time import sleep

import boto3
from botocore.exceptions import ClientError

def describe_fleets(region, fleet_id):
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_fleets(
       FleetIds=[
            fleet_id
        ],
    )

    return response['Fleets'][0]['Instances'][0]['InstanceIds']

def delete_fleet(region, fleet_id):
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.delete_fleets(
        FleetIds=[
            fleet_id,
        ],
        TerminateInstances=True
    )

    return response['SuccessfulFleetDeletions'][0]['CurrentFleetState']


if __name__ == '__main__':
    region = sys.argv[1]
    fleet_id = sys.argv[2]
    try:
        # Delete the fleet
        fleet_deleted_states = ["deleted", "deleted_running", "deleted_terminating"]
        fleet_state = None
        while fleet_state not in fleet_deleted_states:
            sleep(5)
            fleet_state = delete_fleet(region=region, fleet_id=fleet_id)
        print(f"Fleet deleted. Fleet state: {fleet_state}")

        # get the instance ids from the fleet
        print(describe_fleets(region=region, fleet_id=fleet_id))
    except (ClientError, Exception) as e:
        print(e)
  
  
