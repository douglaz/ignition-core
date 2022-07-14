import urllib.request
import sys

from botocore.exceptions import ClientError
import boto3


def _get_security_group(region, vpc_id):
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
    return response


def _client_cidr():
    flintrock_client_ip = (
            urllib.request.urlopen('http://checkip.amazonaws.com/')
            .read().decode('utf-8').strip())
    flintrock__client_cidr = '{ip}/32'.format(ip=flintrock_client_ip)
    return flintrock__client_cidr


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

    :param region: The AWS region where the VPC is located
    :type region: str
    :param vpc_id: The VPC ID where flintrock Security Group was created
    :type vpc_id: str
    :returns: a string with a message explaining the success or fail
    :rtype: str
    """
    
    response = _get_security_group(region=region, vpc_id=vpc_id)
    security_groups = response["SecurityGroups"]
    cidr_to_revoke_rules = _client_cidr()
    
    if not len(security_groups):
        raise 'There is no security groups in the vpc {} at region {}'.format(vpc_id, region)

     for security_group in security_groups:
        for ip_permission in security_group['IpPermissions']:
            for ip_range in ip_permission['IpRanges']:
                group_id = security_group['GroupId']
                group_name = security_group['GroupName']
                from_port = ip_permission['FromPort']
                ip_protocol = ip_permission['IpProtocol']
                to_port = ip_permission['ToPort']
                
                if group_name == 'flintrock' and  'FromPort' in ip_permission and ip_range['CidrIp'] == cidr_to_revoke_rules:
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
                        print('There is no rule from this client to delete in the vpc id: {}.'.format(vpc_id))
                        raise error
                        
    print('Successfully deleted the rules from this client in the vpc id: {}.'.format(vpc_id))


if __name__ == '__main__':
    region = sys.argv[1]
    vpc_id = sys.argv[2]
    result = revoke_flintrock_sg_ingress(region=region, vpc_id=vpc_id)
    print(result)
    