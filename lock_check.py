import shlex
import sys
import boto3
import time
sys.path.append("/Users/tec/Desktop/svmcheck") #location of NetApp SDK python files
from NaServer import *


# Function to poll the number of open NFS locks per node
def lockcheck(node ,cluster_ip, username, password):
    s = NaServer(cluster_ip, 1, 110)
    s.set_server_type("FILER")
    s.set_transport_type("HTTPS")
    s.set_port(443)
    s.set_style("LOGIN")
    s.set_admin_user(username, password)
    cmd = shlex.split('statistics show -object nfsv4_diag -instance nfs4_diag -counter storePool_OpenAlloc -raw -node '+node)
    args = NaElement('args')
    for arg in cmd:
        args.child_add(NaElement('arg', arg))
    cli = NaElement('system-cli')
    cli.child_add(args)
    cli.child_add(NaElement('priv', 'diagnostic'))
    out = s.invoke_elem(cli)
    format_output = out.sprintf()
    result = format_output.split('storePool_OpenAlloc')[1].splitlines()[0].strip(" ")
    result = int(result)
    return result

# Function to pull the LIFs from listed node and vserver
def list_lifs_from_locked_node(cluster, problem_node, problem_vserver, username, password):
    s = NaServer(cluster, 1 , 110)
    s.set_server_type("FILER")
    s.set_transport_type("HTTPS")
    s.set_port(443)
    s.set_style("LOGIN")
    s.set_admin_user(username, password)

    # Set tag to null in order to use the iter-api properly
    tag = "";
    interfaces = []
    while tag != None:
        if not tag:
            result = s.invoke('net-interface-get-iter', 'max-records', 1)
        else:
            result = s.invoke('net-interface-get-iter', 'tag', tag, 'max-records', 1)

        if result.results_status() == "failed":
            reason = result.results_reason()
            print(reason + "\n")
            return
            #sys.exit(2)

        if result.child_get_int('num-records') == 0:
            # print("Migrating interfaces")
            # for i in interfaces:
            #     print(i['name'])
            #sys.exit(0)
            return interfaces

        tag = result.child_get_string('next-tag')

        for interface in result.child_get('attributes-list').children_get():
            name = interface.child_get_string('interface-name')
            vserver = interface.child_get_string('vserver')
            home_port = interface.child_get_string('home-port')
            home_node = interface.child_get_string('home-node')
            if vserver == problem_vserver and home_node == problem_node:
                interfaces.append({'name':name, 'vserver': vserver, 'home_port':home_port, 'home_node':home_node})

# Function to migrate LIFs off impacted node in order to reset lock count
def migrate_lifs(cluster, username, password, dest_node, dest_port, vserver, lif):
    s = NaServer(cluster, 1, 110)
    s.set_server_type("FILER")
    s.set_transport_type("HTTPS")
    s.set_port(443)
    s.set_style("LOGIN")
    s.set_admin_user(username, password)

    api = NaElement("net-interface-migrate")

    api.child_add_string("destination-node", dest_node)
    api.child_add_string("destination-port", dest_port)
    api.child_add_string("lif", lif)
    api.child_add_string("vserver", vserver)
    s.invoke_elem(api)

def send_sns(message):
    sns = boto3.client('sns', aws_access_key_id='changeme', aws_secret_access_key='changeme', region_name='us-east-1')
    topic = 'arn:aws:sns:CHANGEME'
    sns.publish(TopicArn=topic, Message=message)

def trigger_autosupport():
    s = NaServer(cluster, 1, 110)
    s.set_server_type("FILER")
    s.set_transport_type("HTTPS")
    s.set_port(443)
    s.set_style("LOGIN")
    s.set_admin_user(username, password)

    api = NaElement("autosupport-invoke")
    api.child_add_string("message", "Possible NFSv4 lock bug discovered")
    api.child_add_string("node-name", "*")
    api.child_add_string("type", "all")

    s.invoke_elem(api)

def push_logs_cloudwatch(message):
    logs = boto3.client('logs', aws_access_key_id='CHANGEME', aws_secret_access_key='CHANGEME', region_name='us-east-2')
    LOG_GROUP = 'LOGGROUP'
    LOG_STREAM = 'LOGSTREAM'
    # Either uncomment during first run, or pre-setup the log group and stream
    #logs.create_log_group(logGroupName=LOG_GROUP)
    #logs.create_log_stream(logGroupName=LOG_GROUP, logStreamName=LOG_STREAM)
    group_info = logs.describe_log_streams(logGroupName='LOG_GROUP')
    output_list = str(group_info['logStreams']).split(',')
    token_preformat = [s for s in output_list if "uploadSequenceToken" in s]
    token = int(''.join(list(filter(str.isdigit, str(token_preformat)))))


    timestamp = int(round(time.time() * 1000))
    logs.put_log_events(logGroupName=LOG_GROUP, logStreamName=LOG_STREAM, sequenceToken=str(token), logEvents=[{'timestamp': timestamp, 'message': time.strftime('%Y-%m-%d %H:%M:%S')+message}])


cluster = ''
username = ''
password = ''

# check for locks against both no
n1_locks = lockcheck('cluster-n1', cluster, username, password)
n2_locks = lockcheck('cluster-n2', cluster, username, password)

# if locks are above 300k, migrate the LIFs, trigger autosupport and trigger a SNS alert
if n1_locks > 300000:
    lifs_to_migrate_from_node1 = list_lifs_from_locked_node(cluster, 'node1', 'problem_vserver, username, password)
    for interface in lifs_to_migrate_from_node1:
        migrate_lifs(cluster, username, password, 'node2', interface['home_port'], 'problem_vserver', interface['name'])
    trigger_autosupport()
    send_sns("node1 hit lock threshold. LIFs were migrated Locks: "+str(n1_locks))

if n2_locks > 300000:
    lifs_to_migrate_from_node2 = list_lifs_from_locked_node(cluster, 'node2', 'problem_vserver', username, password)
    for interface in lifs_to_migrate_from_node2:
        migrate_lifs(cluster, username, password, 'node1', interface['home_port'], 'problem_vserver', interface['name'])
    trigger_autosupport()
    send_sns("node2 hit lock threshold. LIFs were migrated. Locks: " +str(n2_locks))


log_message = ' node1 locks: '+str(n1_locks)+' and node2 locks: '+str(n2_locks)
push_logs_cloudwatch(log_message)


