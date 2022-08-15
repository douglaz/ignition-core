import urllib.request
import sys

from botocore.exceptions import ClientError
import boto3


def _get_security_group(region, vpc_id, sg_name):
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_security_groups(
        Filters=[
            {
                'Name': 'vpc-id',
                'Values': [
                    vpc_id,
                ]
            },
        ],
    )
    desired_sg = None
    security_groups = response['SecurityGroups']
    for security_group in security_groups:
        if security_group['GroupName'] == sg_name:
            desired_sg = security_group

    return desired_sg


def _client_cidr():
    flintrock_client_ip = (
            urllib.request.urlopen('http://checkip.amazonaws.com/')
            .read().decode('utf-8').strip())
    flintrock__client_cidr = '{ip}/32'.format(ip=flintrock_client_ip)
    return flintrock__client_cidr


def _exists_cidr_in_sg(region, cidr, sg_id):
    """Boolean function to return `true` if a given cidr
    exists in a given security group id. Otherwise returns
    `false`.
    """
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_security_group_rules(
        Filters=[
            {
                'Name': 'group-id',
                'Values': [
                    sg_id,
                ]
            },
        ]
    )
    rules = response['SecurityGroupRules']
    for rule in rules:
        if rule['CidrIpv4'] == cidr:
            return True
    return False


def _delete_rule(cidr_ip, ip_protocol, from_port, to_port, group_id, region):
      ec2 = boto3.client('ec2', region_name=region)
      ec2.revoke_security_group_ingress(
            CidrIp=cidr_ip,
            GroupId=group_id,
            IpProtocol=ip_protocol,
            FromPort=from_port,
            ToPort=to_port
        )


def revoke_flintrock_sg_ingress(region, vpc_id):
    """Revoke Flintrock Security Group's Rules matched with the IP from
    the current machine given the Region and VPC ID
    :param `region`: The AWS region where the VPC is located
    :type `region`: str
    :param `vpc_id`: The VPC ID where flintrock Security Group was created
    :type `vpc_id`: str
    """
    
    flintrock_security_group = _get_security_group(region=region, vpc_id=vpc_id, sg_name='flintrock')
    cidr_to_revoke_rules = _client_cidr()
    flintrock_group_id = flintrock_security_group['GroupId']

    if flintrock_security_group['GroupName'] != 'flintrock':
        print('Flintrock security groups doesn\'t exist in this vpc {} at region {}'.format(vpc_id, region))
        return # we don't want the script to ``raise`` an error, to not mess with the job_runner.py logs
    
    # check if the local IP is in some rule or not
    if not _exists_cidr_in_sg(region=region, cidr=cidr_to_revoke_rules, sg_id=flintrock_group_id):
        print('There is no rules with the IP of this client in Flintrock security group.')
        return

    for ip_permission in flintrock_security_group['IpPermissions']:
        for ip_range in ip_permission['IpRanges']:
            group_id = flintrock_group_id
            from_port = ip_permission['FromPort']
            ip_protocol = ip_permission['IpProtocol']
            to_port = ip_permission['ToPort']
            
            if 'FromPort' in ip_permission and ip_range['CidrIp'] == cidr_to_revoke_rules:
                try:
                    _delete_rule(
                        cidr_ip=ip_range['CidrIp'],
                        ip_protocol=ip_protocol,
                        from_port=from_port,
                        to_port=to_port,
                        group_id=group_id,
                        region=region
                    )
                except ClientError as error:
                    print(error)
    
    # check again to confirm if the rules were revoked
    if not _exists_cidr_in_sg(region=region, cidr=cidr_to_revoke_rules, sg_id=flintrock_group_id):
        print('Successfully deleted rules of this client from flintrock security group at vpc {}'.format(vpc_id))


if __name__ == '__main__':
    region = sys.argv[1]
    vpc_id = sys.argv[2]
    revoke_flintrock_sg_ingress(region=region, vpc_id=vpc_id)
    