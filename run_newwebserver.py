#Adam Cotter
#!/usr/bin/env python3

import sys
import subprocess
import boto3
import time
from datetime import datetime,timezone,timedelta
import paramiko

#generates bucket name based on current time and date
currentDate = datetime.now().strftime("%d-%m-%Y%H-%M-%S")
print(currentDate)
bucket_name= currentDate+"acbucket"

#commands executed to install apache and start the service
USER_DATA = """#!/bin/bash
yum install httpd -y
systemctl enable httpd
service httpd start
"""

htmlcommands="""
echo '<html>' > index.html
echo 'Private IP address: ' >> index.html
curl http://169.254.169.254/latest/meta-data/local-ipv4 >> index.html
echo '<br>Here is the image:<br> ' >> index.html
echo '<img src="https://s3-eu-west-1.amazonaws.com/"""+bucket_name+"""/image.jpg">' >> index.html
sudo mv index.html /var/www/html
"""

def main():
    #takes the name of the user's key as an input and gives the key the correct permissions
    key_name = input("What is the name of your key? >> ")
    subprocess.run(f'chmod 600 {key_name}.pem',shell=True)

    print("Creating instance...")
    ec2 = boto3.resource('ec2')

    #creates a security group that allows SSH and HTTP
    security_group = ec2.create_security_group(GroupName='instance_security_group'+currentDate,Description='HTTP and SSH')
    security_group.authorize_ingress(GroupId=security_group.id,IpProtocol='tcp',FromPort=22,ToPort=22,CidrIp='0.0.0.0/0')
    security_group.authorize_ingress(GroupId=security_group.id,IpProtocol='tcp',FromPort=80,ToPort=80,CidrIp='0.0.0.0/0')
    print("Security group created")
    
    #creates the instance
    instance = ec2.create_instances(
        ImageId='ami-0ce71448843cb18a1',
        KeyName=key_name,
        UserData=USER_DATA,
        SecurityGroupIds=[security_group.id],
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        #enables detailed monitoring for cloudwatch
        Monitoring={
            'Enabled':True
        }
    )
    print("Instance created.")
    print("Instance ID: "+instance[0].id)
    instance[0].wait_until_running()
    instance[0].reload()
    
    print("Instance IP: "+instance[0].public_ip_address)
    
    s3 = boto3.resource("s3")

    #creates the bucket for storing the image
    try:
        response = s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': 'eu-west-1'})
        print (response)
    except Exception as error:
        print (error)

    #downloads the image locally
    subprocess.run(
        "curl http://devops.witdemo.net/image.jpg > image.jpg", shell=True
    )

    time.sleep(50)

    #uses paramiko to connect to the instance using SSH and executes the htmlcommands
    key = paramiko.RSAKey.from_private_key_file(key_name+'.pem')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(hostname=instance[0].public_ip_address, username="ec2-user", pkey=key)

        stdin, stdout, stderr = client.exec_command(htmlcommands)
        print(stdout.read())

        client.close()

    except Exception as e:
        print(e)

    #puts the image file in the bucket
    try:
        response = s3.Object(bucket_name, 'image.jpg').put(Body=open('image.jpg', 'rb'), ACL='public-read')
        print (response)
    except Exception as error:
        print(error)

    print("Instance IP: "+instance[0].public_ip_address)

    id = instance[0].id

    #runs the getMetrics function and prints the average of each metric
    while getMetrics('CPUUtilization', id)==None:
        time.sleep(10)
    print("CPU Utilisation: "+str(getMetrics('CPUUtilization',id)))

    while getMetrics('NetworkIn',id)==None:
        time.sleep(10)
    print("Network In: "+str(getMetrics('NetworkIn',id)))

    while getMetrics('NetworkOut',id)==None:
        time.sleep(10)
    print("Network Out: "+str(getMetrics('NetworkOut',id)))

#this function gets a cloudwatch metric returns the average when there is at least 1 datapoint
def getMetrics(name,id):
    cloudwatch=boto3.client('cloudwatch')
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName=name,
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': id
            },
        ],
        StartTime=datetime.now(timezone.utc)-timedelta(minutes=5),
        EndTime=datetime.now(timezone.utc),
        Period=300,
        Statistics=[
            'Average'
        ],
    )

    if len(response['Datapoints'])>0:
        return(response['Datapoints'][0]['Average'])
    else:
        return None

main()