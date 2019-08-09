from base64 import b64decode
from base64 import b64encode
from calendar import timegm
from collections import OrderedDict
from datetime import datetime
from flask import Flask, Response, request
from glob import glob
from json import loads
from json import dumps
from logging import basicConfig
from logging import DEBUG
from logging import WARNING
from logging import ERROR
#from logging import EXCEPTION
from logging import INFO
from logging import debug
from logging import info
from logging import warning
from logging import critical
from logging import exception as logging_exception
from os import environ
from os import getenv
from os import remove
from os.path import expanduser
from os.path import join
#from pyqrcode import create
from queue import Queue
from queue import Empty
from QiyNodeLib.QiyNodeLib import node_connect
from QiyNodeLib.QiyNodeLib import node_connect_token__create
from QiyNodeLib.QiyNodeLib import node_get_messages
from QiyNodeLib.QiyNodeLib import node_request
from QiyNodeLib.QiyNodeLib import pretty_print
from re import findall
from re import fullmatch
from requests.exceptions import ChunkedEncodingError
from string import Template
from threading import Thread
from threading import Event
from time import sleep
from time import strftime
from time import time
from typing import Iterator
from uuid import uuid4
from urllib.parse import quote_plus
from urllib.parse import unquote

import flask_sse
import pymongo
import random
import string
import sys

log_levels={}
log_levels['DEBUG']=DEBUG
log_levels['INFO']=INFO
log_levels['WARNING']=WARNING
log_levels['ERROR']=ERROR
#log_levels['EXCEPTION']=EXCEPTION

log_level=DEBUG


basicConfig(filename="QiyTestTool.log",
            level=log_level,
            format='%(asctime)s %(funcName)s %(levelname)s: %(message)s',
            )

if not 'TARGET' in environ:
    critical("ERROR: No TARGET specified.")
    exit(1)
if not environ['TARGET'] in ['dev2','acc']:
    critical("ERROR: No valid TARGET specified.")
    exit(1)

target=environ['TARGET']


configuration="""
CURRENT CONFIGURATION:
- TARGET:               '{}'

""".format(environ['TARGET'])
info("Configuration: ok")
debug(configuration)


info("Start")


app = Flask(__name__)


class NoDataReceivedException(Exception):
    def __init__(self):
        pass

class ServerSentEvent(object):
    """Class to handle server-sent events."""
    def __init__(self, data, event):
        now=datetime.now().isoformat()
        self.data = "{} {}".format(now,data)
        self.event = event
        self.event_id = generate_id()
        self.desc_map = {
            self.data: "data",
            self.event: "event",
            self.event_id: "id"
        }

    def encode(self) -> str:
        """Encodes events as a string."""
        if not self.data:
            return ""
        lines = ["{}: {}".format(name, key)
                 for key, name in self.desc_map.items() if key]

        return "{}\n\n".format("\n".join(lines))

def event_generator() -> Iterator[str]:
    for event in event_listener():
        sse = ServerSentEvent(str(event), None)
        yield sse.encode()

def __event_listener(regexp=None) -> Iterator[str]:
    str_regexp=""
    if regexp:
        str_regexp=regexp
    info("event_listener(regexp='%s')", str_regexp)
    headers={"Accept": "text/event-stream"}
    node_name=environ['NODE_NAME']
    target=environ['TARGET']
    with node_request(endpoint_name="events",
                      headers=headers,
                      node_name=node_name,
                      #node_type="",
                      operation="get",
                      stream=True,
                      target=target
                      ) as r:
        log=""
        try:
            for chunk in r.iter_content(chunk_size=1, decode_unicode=True):
                if not chunk.isprintable():
                    chunk=" "
                log=log+chunk
                if 'ping' in log:
                    debug(".")
                    log=""
                elif '}' in log:
                    info("event_listener: event: '%s'", log)
                    if regexp:
                        debug("    regexp: '{0}'".format(regexp))
                        extract=findall(regexp,log)
                        debug("    extract: '{0}'".format(extract))
                        if extract:
                            info("event_listener: regexp '%s' extract '%s'", regexp, extract)
                            yield extract
                    else:
                        yield log
                    log=""
        except ChunkedEncodingError:
            info("Catched ChunkedEncodingError")

"""
   Example output:

event: CONNECTED_TO_ROUTER
data: {
   "type":"CONNECTED_TO_ROUTER",
   "connectionUrl":"https://dev2-user.testonly.digital-me.nl/user/connections/user/pt_usernode_RP_mockup_de/1cb98e90-0ad8-45a1-bf1f-2fecfce7d382",
   "extraData":"https://dev2-issuer.testonly.digital-me.nl/issuer/routes/webhook/2480e817-dfc3-4892-b445-afe34ac17676"
}
: ping
event: STATE_HANDLED
data: {
   "type":"STATE_HANDLED",
   "connectionUrl":"https://dev2-user.testonly.digital-me.nl/user/connections/user/pt_usernode_RP_mockup_de/1cb98e90-0ad8-45a1-bf1f-2fecfce7d382",
   "extraData":"https://dev2-user.testonly.digital-me.nl/user/connections/user/pt_usernode_RP_mockup_de/6c31becc-2ffb-4aaa-b9c9-e4074028ae66"
}

: ping : ping : ping : ping : ping
"""

def node_events_listener(event=None,
                         node_name=None,
                         node_type='user',
                         queue=None,
                         target=None
                         ):
    info("{0} {1}".format(node_name,target))
    headers={"Accept": "text/event-stream"}
    try:
        with node_request(endpoint_name="events",
                          headers=headers,
                          node_name=node_name,
                          node_type=node_type,
                          operation="get",
                          stream=True,
                          target=target
                          ) as r:
            log=""
            for chunk in r.iter_content(chunk_size=1, decode_unicode=True):
                if not chunk.isprintable():
                    chunk=" "
                log=log+chunk
                if 'ping' in log or (len(findall('{',log))>0 and (len(findall('{',log))==len(findall('}',log)))):
                    queue.put(log,timeout=1)
                    log=""
                if event.is_set():
                    queue.put(None,timeout=1)
                    print("----------- BREAK ---------------")
                    break
    except ChunkedEncodingError:
        # This exception is only raised when the URLLIB fix has not been applied, see README.
        # Server-sent events can still be received, but only when using a new session.
        info("Silenced ChunkedEncodingError")
        if 'ping' in log or (len(findall('{',log))>0 and (len(findall('{',log))==len(findall('}',log)))):
            queue.put(log,timeout=1)
            log=""


def node_events_listener__start(
                                event=None, # Stop listening event
                                node_name=None,
                                node_type='user',
                                queue=None,
                                target=None
                                ):
    thread=Thread(daemon=True,
                  target=node_events_listener,
                  kwargs={"node_name":node_name,
                          "node_type":node_type,
                          "event": event,
                          "queue":queue,
                          "target":target,
                          },
                  name="{0}.events_listener".format(node_name)
                  )
    thread.start()
    return thread


def listen_to_node(queue,stop_listening,node_name="example_node_credential",target="dev2"):
    node_events_listener__start(event=stop_listening,
                                node_name=node_name,
                                queue=queue,
                                target=target)



def generate_id(size=6, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def get_first_connection_url(new_connection_url,queue=''):
    info("get_first_connection_url('%s',queue='%s')", new_connection_url,queue)
    regexp='STATE_HANDLED[^c]*connectionUrl":"{0}"[^e]*extraData":{{"newUri":"([^"]*)"'.format(new_connection_url)
    debug(regexp)
    first_connection_url=""
    if not queue:
        for first_connection_url_list in event_listener(regexp=regexp):
            break
        first_connection_url=first_connection_url_list[0]
        info("get_first_connection_url('%s') returns '%s'", new_connection_url, first_connection_url)
    else:
        while not first_connection_url:
            event=queue.get(timeout=100)
            debug("    event: '{0}'".format(event))
            debug("    regexp: '{0}'".format(regexp))
            extract=findall(regexp,event)
            debug("    extract: '{0}'".format(extract))
            if extract:
                first_connection_url=extract[0]
                debug("    first_connection_url: '{0}'".format(first_connection_url))
        info("get_first_connection_url('%s',queue='%s') returns '%s'", new_connection_url,queue,first_connection_url)
    return first_connection_url

def get_new_connection_url(webhook_url,queue=''):
    info("get_new_connection_url('%s',queue='%s')", webhook_url,queue)
    regexp='CONNECTED_TO_ROUTER[^c]*connectionUrl":"([^"]*)"[^e]*extraData":"{0}"'.format(webhook_url)
    debug(regexp)
    new_connection_url=""
    if not queue:
        iterator=event_listener(regexp=regexp)
        for new_connection_url_list in iterator:
            break
        new_connection_url=new_connection_url_list[0]
        info("get_new_connection_url('%s') returns '%s'", webhook_url, new_connection_url)
    else:
        while not new_connection_url:
            event=queue.get(timeout=100)
            debug("    event: '{0}'".format(event))
            debug("    regexp: '{0}'".format(regexp))
            extract=findall(regexp,event)
            debug("    extract: '{0}'".format(extract))
            if extract:
                new_connection_url=extract[0]
                debug("    new_connection_url: '{0}'".format(new_connection_url))
        info("get_new_connection_url('%s',queue='%s') returns '%s'", webhook_url,queue,new_connection_url)


    return new_connection_url

def message_poller(connection_url=None,node_name=None,target=None) -> Iterator[str]:
    str_connection_url=""
    if connection_url:
        str_connection_url=connection_url
    str_node_name=""
    if node_name:
        str_node_name=node_name
    str_target=""
    if target:
        str_target=target
    info("message_poller(connection_url='%s',node_name='%s',target='%s')", str_connection_url,str_node_name,str_target)
    warning("message_poller() has been disabled.")
    while False:
        message=node_get_messages(connection_url=connection_url,
                                  node_name=node_name,
                                  since=0, # For now: return all messages ever received.
                                  target=target
                                  )
        sse = ServerSentEvent(str(message), None)
        yield sse.encode()
        sleep(15)

@app.route('/')
def root():
    info("root()")

    service_types=node_service_types()
    service_type_lis=""
    for i in service_types:
        service_type_lis=service_type_lis+'<li><a href="service_types/{0}">{1}</a>\n'.format(ub_encode(i),i)
        
    ids=node_ids(target=target)
    lis=""
    for i in ids:
        lis=lis+'<li><a href="qiy_nodes/{0}">{0}</a>'.format(i)
    
    return """
<h1>Qiy Test Tool</h1>
freek.driesenaar@digital-me.nl
8-2019

<h2>Service types</h2>

<ul>
{0}
</ul>

<h2>Test nodes</h2>
<ul>
{1}
</ul>

""".format(service_type_lis,
           lis)

#
# <Candidate function(s) for QiyNodeLib>
#

def node_connected_node_names(node_name,target=None):
    connected_node_names=[]
    
    all_node_names=node_ids(target=target)

    connections_by_node={}
    node_names_by_pid={}
    
    for name in all_node_names:
        connections=qiy_nodes_connections_json(name)

        connected_connections_by_pid={}
        for i in connections:
            connection=connections[i]
            if connection['state']=='connected':
                pid=connection['pid']
                connected_connections_by_pid[pid]=connection
                if pid not in node_names_by_pid:
                    node_names_by_pid[pid]=[name]
                elif name not in node_names_by_pid[pid]:
                    node_names_by_pid[pid].append(name)
        connections_by_node[name]=connected_connections_by_pid

    for pid in node_names_by_pid:
        names=node_names_by_pid[pid]
        if len(names)==2:
            if node_name in names:
                if names[0]==node_name:
                    connected_node_names.append(names[1])
                else:
                    connected_node_names.append(names[0])

    return connected_node_names

def node_connection_delete(
    node_name=None,
    connection_url=None,
    target=None):
    
    r=node_request(url=connection_url,
                   node_name=node_name,
                   operation="delete",
                   target=target,
                   )

    return r

def node_connection_feed_ids(node_name,
                             connection_url):
    headers={'Accept': 'application/json'}
    r=node_request(url=connection_url,
                   headers=headers,
                   node_name=node_name,
                   target=target)

    connection_feeds_url=r.json()['links']['feeds']
    
    r=node_request(url=connection_feeds_url,
                   headers=headers,
                   node_name=node_name,
                   target=target)

    return r.json()

def node_data_providers(
    service_type_url=None,
    target=None,
    ):
    node_names=node_ids(target=target)
    data_providers=[]
    
    for i in node_names:
        service_catalogue=node_service_catalogue(i,target=target)
        for url in service_catalogue:
            if url == service_type_url:
                data_providers.append(i)

    return data_providers

def node_feed_ids(node_name):
    headers={'Accept': 'application/json'}
    r=node_request(endpoint_name="feeds",
                   headers=headers,
                   node_name=node_name,
                   target=target)
    return r.json()

def node_feed(node_name,feed_id,
              headers={'Accept': 'application/json', 'Content-Type': 'application/json'}
              ):
    body={feed_id: {'input': ''}}
    data=dumps(body)
    print(data)
    r=node_request(
        data=data,
        endpoint_name="feeds",
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target)
    return r.text

def node_service_catalogue(
    node_name,
    target=None,
    ):
    headers={'Accept': 'application/json'}
    r=node_request(endpoint_name="serviceCatalog",
                   headers=headers,
                   node_name=node_name,
                   target=target)
    return r.json()

def node_ids(target=None):
    creds_path=expanduser(getenv("QIY_CREDENTIALS"))
    xpr="*_{}_node_repository.json".format(target[:2])
    l=glob(join(creds_path,xpr))

    rex="{}/(.*?)_{}_node_repository.json".format(creds_path,target[:2])
    rex=rex.replace("\\","/")
    
    node_ids=[]
    for i in l:
        i=i.replace("\\","/")
        node_id=findall(rex,i)[0]
        node_ids.append(node_id)
    return node_ids

def node_service_types(target=None):
    node_names=node_ids(target=target)
    service_types=[]
    
    for i in node_names:
        service_catalogue=node_service_catalogue(i,target=target)
        for service_type_url in service_catalogue:
            if not service_type_url in service_types:
                service_types.append(service_type_url)

    return service_types

def request_to_str(r):
    s="\n"
    s=s+"-------------------------------------------------------------------------------------------\n"
    s=s+"Request:\n"
    s=s+"{0} {1} HTTP/1.1\n".format(r.request.method,r.request.url)
    s=s+"\n"
    headers=r.request.headers
    for header in headers:
        s=s+"{0}: {1}\n".format(header,headers[header])
    s=s+"\n"
    s=s+str(r.request.body)
    s=s+"\n\n"
    s=s+"Response:\n"
    s=s+str(r.status_code)+"\n"
    headers=r.headers
    for header in headers:
        s=s+"{0}: {1}\n".format(header,headers[header])
    s=s+"\n"
    s=s+r.text
    s=s+"\n-------------------------------------------------------------------------------------------\n"
    
    return s

def ub_decode(ub):
    bu=unquote(ub)
    bu=b64decode(bu).decode()
    return bu
    
def ub_encode(s):
    ub=quote_plus(b64encode(s.encode()).decode())
    return ub
    

# </Candidate function(s) for QiyNodeLib>


@app.route('/qiy_nodes/<node_name>')
def qiy_nodes(node_name):
    info("qiy_node({})".format(node_name))

    u_redirect_url=quote_plus("https://test-einwoner.lostlemon.nl/test/qtn/Boxtel")

    return """
<h1>Test Node {0}</h1>

<ul>
<li><a href="/qiy_nodes/{0}/action_messages">Action messages</a>
<li><a href="/qiy_nodes/{0}/connect">Connect</a>
<li><a href="/qiy_nodes/{0}/connected_nodes">Connected nodes</a>
<li><a href="/qiy_nodes/{0}/connect_tokens">Connect tokens</a>
<li><a href="/qiy_nodes/{0}/consume_connect_token">Consume Connect token</a>
<li><a href="/qiy_nodes/{0}/connections">Connections</a>
<li><a href="/qiy_nodes/{0}/event_callback_addresses">Event callback addresses</a>
<li><a href="/qiy_nodes/{0}/events">Events</a>
<li><a href="/qiy_nodes/{0}/feeds">Feeds</a>
<li><a href="/qiy_nodes/{0}/messages/since/60">Messages since 1h</a> (<a href="/qiy_nodes/{0}/messages/since/1440">1 day</a>)
<li><a href="/qiy_nodes/{0}/service_catalogue">Service Catalogue</a>
<li><a href="/qiy_nodes/{0}/pids">Pids</a>
<li><a href="/qiy_nodes/{0}/redirect_to_eformulieren/{1}">Redirect to Lost Lemon eFormulieren</a>
</ul>

<a href="/">Home</a>

""".format(node_name,u_redirect_url)

def qiy_nodes_action_messages_json(node_name):
    info("qiy_nodes_action_messages_json({})".format(node_name))

    action_messages={}

    r=node_request(endpoint_name="amList", node_name=node_name, target=target)
    action_messages_by_created={}
    if r.status_code==200:
        action_messages=r.json()['result']
        for action_message in action_messages:
            action_message['created']=datetime.utcfromtimestamp(int(action_message['created'])/1000).isoformat()
            action_messages_by_created[action_message['created']+' '+action_message['links']['self']]=action_message
        sorted_action_messages = OrderedDict(sorted(action_messages_by_created.items(), key=lambda t: t[0],reverse=True))

    else:
        sorted_action_messages={"error": r.text }
    return sorted_action_messages


@app.route('/qiy_nodes/<node_name>/action_messages')
def qiy_nodes_action_messages(node_name):
    info("qiy_nodes_action_messages({})".format(node_name))

    action_messages=qiy_nodes_action_messages_json(node_name)
    lis=""
    for amid in action_messages:
        action_message=action_messages[amid]
        li='<li>{0}: {1}'.format(amid, dumps(action_message,indent=2))
        rolis=""
        relay_options=action_message['relayOptions']
        for relay_option in relay_options:
            b64_relay_option_url=quote_plus(
                b64encode(relay_options[relay_option].encode()).decode()
            )
            url="/qiy_nodes/{}/action_messages/relay_options/get/{}".format(node_name,b64_relay_option_url)
            roli="<li>{0}: <a href=\"{1}\">select as source using relay option url {2}</a>\n".format(relay_option,url,dumps(relay_options[relay_option]))
            rolis=rolis+roli
        rolis="    <ul>\n    {}    </ul>\n".format(rolis)
        li=li+rolis
        lis=lis+li

    return """
<h1>Test Node {0} - Action messages</h1>

<ul>
{1}
</ul>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,lis)


@app.route('/qiy_nodes/<node_name>/action_messages/relay_options/get/<path:b64_relay_option>')
def qiy_nodes_action_messages_relay_options_get(node_name,b64_relay_option):
    info("qiy_nodes_action_messages_relay_options_get({},{})".format(node_name,b64_relay_option))

    relay_option=b64decode(b64_relay_option.encode()).decode()

    r=node_request(node_name=node_name,
#            operation="post",
            operation="put",
            target=target,
            url=relay_option
            )
    pretty_print(r)

    return """
<h1>Test Node {0} - Action messages - Relay options - get</h1>

Relay option: {1}
<p>
Response status_code: {2}<br>
Response headers: {3}

<a href="/qiy_nodes/{0}/action_messages">Up</a>

""".format(node_name,relay_option,r.status_code,r.headers)


@app.route('/qiy_nodes/<node_name>/connect')
def qiy_nodes_connect(node_name):
    info("{}".format(node_name))

    return """
<h1>Test Node {0}</h1>

<h2>Connect</h2>

<ul>
<li><a href="/qiy_nodes/{0}/connect_with_node">Connect with node</a>
</ul>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name)

@app.route('/qiy_nodes/<node_name>/connect_with_node')
def qiy_nodes_connect_with_node(node_name):
    info("{}".format(node_name))

    l=node_ids(target=target)
    l.remove(node_name)
    connected=node_connected_node_names(node_name,target=target)

    not_connected=[]
    for i in l:
        if i not in connected:
            not_connected.append(i)

    lis=""
    for i in not_connected:
        li='<li><a href="/qiy_nodes/{0}/connect_with_other_node/{1}">{1}</a>'.format(node_name,i)
        lis="{}\n{}".format(lis,li)

    return """
<h1>Test Node {0}</h1>

<h2>Connect with node</h2>

<ul>
{1}
</ul>

<a href="/qiy_nodes/{0}/connect">Up</a>

""".format(node_name,lis)


@app.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>')
def qiy_nodes_connect_with_other_node(node_name,other_node_name):
    info("{} {}".format(node_name,other_node_name))

    return """
<h1>Test Node {0}</h1>

<h2>Connect with node {1}</h2>

<h3>With new connect token</h3>
<ul>
<li><a href="/qiy_nodes/{0}/connect_with_other_node/{1}/with_new_connect_token/as_producer">as connect token producer</a>
<li><a href="/qiy_nodes/{0}/connect_with_other_node/{1}/with_new_connect_token/as_consumer">as connect token consumer</a>
</ul>

<a href="/qiy_nodes/{0}/connect_with_node">Up</a>

""".format(node_name,other_node_name)


@app.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>/with_new_connect_token/as_consumer')
def qiy_nodes_connect_with_other_node_with_new_connect_token_as_consumer(node_name,other_node_name):
    info("{} {}".format(node_name,other_node_name))

    connect_token=node_connect_token__create(
        node_name=other_node_name,
        target=target)

    r=node_connect(connect_token=connect_token,
                   node_name=node_name,
                   target=target)

    log=request_to_str(r)
    

    return """
<h1>Test Node {0}</h1>

<h2>Connect with node {1}</h2>

<h3>With new connect token as consumer</h3>

Node {0} has sent {1} a connect request with token:
<p>
<pre>
{2}
</pre>

<h3>Request data</h3>

<pre>
{3}
</pre>

<a href="/qiy_nodes/{0}/connect_with_other_node/{1}">Up</a>
""".format(node_name,
           other_node_name,
           dumps(connect_token,indent=2),
           log
           )


@app.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>/with_new_connect_token/as_producer')
def qiy_nodes_connect_with_other_node_with_new_connect_token_as_producer(node_name,other_node_name):
    info("{} {}".format(node_name,other_node_name))

    connect_token=node_connect_token__create(
        node_name=node_name,
        target=target)

    r=node_connect(connect_token=connect_token,
                   node_name=other_node_name,
                   target=target)

    log=request_to_str(r)
    

    return """
<h1>Test Node {0}</h1>

<h2>Connect with node {1}</h2>

<h3>With new connect token as producer</h3>

Node {1} has sent {0} a connect request with token:
<p>
<pre>
{2}
</pre>

<h3>Request data</h3>

<pre>
{3}
</pre>

<a href="/qiy_nodes/{0}/connect_with_other_node/{1}">Up</a>
""".format(node_name,
           other_node_name,
           dumps(connect_token,indent=2),
           log
           )


@app.route('/qiy_nodes/<node_name>/connected_nodes')
def qiy_nodes_connected_nodes(node_name):
    info("{}".format(node_name))

    ids=node_connected_node_names(node_name,target=target)

    return """
<h1>Test Node {0}</h1>

<h2>Connected nodes</h2>

<pre>
{1}
</pre>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(ids,indent=2))


def qiy_nodes_connections_json(node_name):
    info("qiy_nodes_connections_json({})".format(node_name))

    connections={}

    r=node_request(endpoint_name="connections", node_name=node_name, target=target)
    if r.status_code==200:
        connections=r.json()['result']
        connections_by_activeFrom={}
        for connection in connections:
            connection['activeFrom']=datetime.utcfromtimestamp(int(connection['activeFrom'])/1000).isoformat()
            if 'activeUntil' in connection:
                connection['activeUntil']=datetime.utcfromtimestamp(int(connection['activeUntil'])/1000).isoformat()
            else:
                connection['activeUntil']=''
            if not 'parent' in connection:
                connection['parent']=''
            connections_by_activeFrom[connection['activeFrom']+' '+connection['links']['self']]=connection
        sorted_connections = OrderedDict(sorted(connections_by_activeFrom.items(), key=lambda t: t[0],reverse=True))
    else:
        sorted_connections={"error": r.text }
    return sorted_connections


@app.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>')
def qiy_nodes_connection(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    connection=dumps(node_request(
        node_name=node_name,
        headers={'Accept':'application/json'},
        target=target,
        url=connection_url,
        ).json(),indent=2)

    lis=""
    li='<li><a href="/qiy_nodes/{0}/connection/{1}/delete">Delete</a>'.format(
        node_name,
        quote_plus(ub_connection_url)
        )
    lis="{}{}\n".format(lis,li)
    li='<li><a href="/qiy_nodes/{0}/connection/{1}/feeds">Feeds</a>'.format(
        node_name,
        quote_plus(ub_connection_url)
        )
    lis="{}{}\n".format(lis,li)
    
    
    return """
<h1>Test Node {0}</h1>

<h2>Connection</h2>
connection_url: {1}

<ul>
{2}
</ul>

<pre>
{3}
</pre>


<a href="/qiy_nodes/{0}/connections">Up</a>

""".format(node_name,
           connection_url,
           lis,
           connection
           )


@app.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/delete')
def qiy_nodes_connection_delete(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    r=node_connection_delete(node_name=node_name,
                             connection_url=connection_url,
                             target=target)

    log=request_to_str(r)
    
    return """
<h1>Test Node {0}</h1>

<h2>Connection delete</h2>
connection_url: {1}

<h3>Request</h3>
<pre>
{2}
</pre>

<a href="/qiy_nodes/{0}/connection/{3}">Up</a>

""".format(node_name,
           connection_url,
           log,
           ub_connection_url,
           )


@app.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds')
def qiy_nodes_connection_feeds(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    
    
    return """
<h1>Test Node {0}</h1>

<h2>Connection feeds</h2>
connection_url: {1}

<ul>
<li><a href="/qiy_nodes/{0}/connection/{2}/feeds/list">List connection feed id's.</a>
<li><a href="/qiy_nodes/{0}/connection/{2}/feeds/request">Request connection for feed.</a>
</ul>

<a href="/qiy_nodes/{0}/connection/{2}">Up</a>

""".format(node_name,
           connection_url,
           quote_plus(ub_connection_url),
           )


@app.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds/list')
def qiy_nodes_connection_feeds_list(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    feed_ids=node_connection_feed_ids(node_name,connection_url)

    lis=""
    for feed_id in feed_ids:
        li='<li><a href="/qiy_nodes/{0}/feed/{1}">{1}</a>\n'.format(
            node_name,
            feed_id
            )
        lis=lis+li

    return """
<h1>Test Node {0}</h1>

<h2>Connection feeds list</h2>
connection_url: {1}

<ul>
{2}
</ul>

<pre>
{3}
</pre>

<a href="/qiy_nodes/{0}/connection/{4}/feeds">Up</a>

""".format(node_name,
           connection_url,
           lis,
           dumps(feed_ids,indent=2),
           quote_plus(ub_connection_url),
           )


@app.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds/request')
def qiy_nodes_connection_feeds_request(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    return """
<h1>Test Node {0}</h1>

<h2>Connection feeds request</h2>
connection_url: {1}

<p>
tbd
</p>


<a href="/qiy_nodes/{0}/connection/{2}/feeds">Up</a>

""".format(node_name,
           connection_url,
           quote_plus(ub_connection_url),
           )


@app.route('/qiy_nodes/<node_name>/connections')
def qiy_nodes_connections(node_name):
    info("qiy_nodes_connections({})".format(node_name))

    connections=qiy_nodes_connections_json(node_name)

    rows=""

    for i in connections:
        connection=connections[i]
        ub_connection=quote_plus(b64encode(dumps(connection).encode()).decode())
        
        active_from=connection['activeFrom']
        parent=""
        if 'parent' in connection['links']:
            parent=connection['links']['parent']
        ub_parent=quote_plus(b64encode(parent.encode()).decode())
        pid=""
        if 'pid' in connection:
            pid=connection['pid']
        ub_pid=quote_plus(b64encode(pid.encode()).decode())
        state=connection['state']
        connection_url=connection['links']['self']
        ub_connection_url=quote_plus(b64encode(connection_url.encode()).decode())
        row='<tr><td>{0}</td><td><a href="/qiy_nodes/{1}/connection/{2}">{3}</a></td><td><a href="/qiy_nodes/{1}/pid/{4}/{5}">{6}</a></td><td>{7}</td><td><a href="/qiy_nodes/{1}/connection/{8}">{9}</a></td></tr>'.format(
            active_from,
            node_name,
            ub_connection_url,
            connection_url,
            ub_pid,
            ub_connection,
            pid,
            state,
            ub_parent,
            parent
            )
        rows="{}\n{}".format(rows,row)

    return """
<h1>Test Node {0}  Connections</h1>

<table>
{1}
</table>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,rows)

def qiy_nodes_connections_references_json(node_name):
    info("qiy_nodes_connections_references_json({})".format(node_name))

    connections=qiy_nodes_connections_json(node_name)
    connections_references={}

    for connection in connections:
        references=qiy_nodes_connection_references_json(connection)
        connections_references[connection['links']['self']]=references

    return connections_references

@app.route('/qiy_nodes/<node_name>/connections/references')
def qiy_nodes_connections_references(node_name):
    info("qiy_nodes_connections({})".format(node_name))

    connections_references_json=qiy_nodes_connections_references_json(node_name)

    return """
<h1>Test Node {0}  Connections</h1>

<pre>
{1}
</pre>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(connections_references_json,indent=2))

def qiy_nodes_connect_tokens_json(node_name):
    info("qiy_nodes_connect_tokens_json({})".format(node_name))


    connect_tokens_by_created={}

    r=node_request(endpoint_name="ctList", node_name=node_name, target=target)
    if r.status_code==200:
        connect_tokens=r.json()
        info("connect_tokens: '{}'".format(dumps(connect_tokens,indent=2)))
        print("connect_tokens: '{}'".format(dumps(connect_tokens,indent=2)))
        for ct in connect_tokens:
            ct['created']=datetime.utcfromtimestamp(int(ct['created'])/1000).isoformat()
            if 'lastUsed' in ct:
                ct['lastUsed']=datetime.utcfromtimestamp(int(ct['lastUsed'])/1000).isoformat()
            connect_tokens_by_created[ct['created']+' '+ct['links']['self']]=ct
        sorted_connection_tokens = OrderedDict(sorted(connect_tokens_by_created.items(), key=lambda t: t[0],reverse=True))
    else:
        sorted_connection_tokens={"error": r.text }

    return sorted_connection_tokens

@app.route('/qiy_nodes/<node_name>/connect_tokens')
def qiy_nodes_connect_tokens(node_name):
    info("qiy_nodes_connect_tokens({})".format(node_name))

    connection_tokens=qiy_nodes_connect_tokens_json(node_name)

    return """
<h1>Test Node {0}  Connect Tokens</h1>

<pre>
{1}
</pre>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(connection_tokens,indent=2))

@app.route('/qiy_nodes/<node_name>/consume_connect_token')
def qiy_nodes_consume_connect_token(node_name):
    info("qiy_nodes_consume_connect_token({})".format(node_name))

    return """
<h1>Test Node {0}  consume_connect_token</h1>

<ul>
<li><a href="/qiy_nodes/{0}/consume_connect_token/of/{1}">of {1}</a>
</ul>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,"mgd_dev2")

@app.route('/qiy_nodes/<node_name>/consume_connect_token/of/<path:producer>')
def qiy_nodes_consume_connect_token_of(node_name,producer):
    info("qiy_nodes_consume_connect_token_of({},{})".format(node_name,producer))

    connect_tokens=qiy_nodes_connect_tokens_json(producer)

    lis=""
    i=0
    for cti in connect_tokens:
        i=i+1
        if i > 9:
            break
        ct=connect_tokens[cti]
        ctjsonb64=quote_plus(b64encode(dumps(ct['json']).encode()).decode())
        url="/qiy_nodes/{}/consume_connect_token/value/{}".format(node_name,ctjsonb64)
        li="<li>{0}, {1}: <a href=\"{3}\">{2}</a>\n".format(ct['created'],ct['useSpend'],dumps(ct['json']),url)
        lis=lis+li

    page="""
<h1>Test Node {0}  consume_connect_token</h1>

<ul>
{2}
</ul>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,"mgd_dev2",lis)
    return page


@app.route('/qiy_nodes/<node_name>/consume_connect_token/value/<path:b64_connect_token>')
def qiy_nodes_consume_connect_token_connect_token_value(node_name,b64_connect_token):
    info("qiy_nodes_consume_connect_token_connect_token_value({},{})".format(node_name,b64_connect_token))

    connect_token_s=b64decode(b64_connect_token).decode()
    connect_token=loads(connect_token_s)

    r=node_connect(connect_token=connect_token,
        node_name=node_name,
        target=target)


    page="""
<h1>Test Node {0} consume_connect_token</h1>

Connect token: {1}
<p>
Response: status code: {2},<br>
headers: {3}

<p>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,connect_token_s,r.status_code,r.headers)
    return page

@app.route('/qiy_nodes/<node_name>/event_callback_addresses')
def qiy_nodes_event_callback_addresses(node_name):
    info("{}".format(node_name))

    headers={'Accept':'application/json'}
    urls=dumps(node_request(
        endpoint_name="eventCallbacks",
        headers=headers,
        node_name=node_name,
        target=target
        ).json(),indent=2)
    
    return """
<h1>Test Node {0}</h1>
<h2>Event Callback Endpoint addresses</h2>
<pre>
{1}
</pre>
<a href="/">Home</a>

""".format(node_name,urls)

@app.route('/qiy_nodes/<node_name>/events')
def qiy_nodes_events(node_name):
    info("qiy_nodes_events({})".format(node_name))
    return """
<h1>Test Node {0}</h1>
<h2>Listen to events</h2>

<p id="events"></p>
<p>
<a href="/qiy_nodes/{0}">Up</a>

<script>
var eventEventSource = new EventSource('/qiy_nodes/{0}/events/source');
eventEventSource.onmessage = function(m) {{
	console.log(m);
	var el = document.getElementById('events');
	el.innerHTML = m.data + "<br>" + el.innerHTML;
}}
</script>

""".format(node_name)


@app.route('/qiy_nodes/<node_name>/events/source')
def qiy_nodes_events_source(node_name):
    info("{0}".format(node_name))

    def gen(node_name) -> Iterator[str]:
            listener_id=generate_id()
            info("{}: Starting events listener...".format(listener_id))
            stop_listening=Event()
            queue=Queue()
            listen_to_node(queue,stop_listening,node_name=node_name)
            info("{}: Events listener started.".format(listener_id))

            while True:
                try:
                    event=queue.get(timeout=100)
                except Empty:
                    if 'QTT_URLLIB_FIXED' in environ:
                        if getenv('QTT_URLLIB_FIXED')=='TRUE':
                            info("{}: QTT_URLLIB_FIXED=='TRUE': Reusing connection on Empty exception".format(listener_id))
                        else:
                            info("{}: QTT_URLLIB_FIXED!='TRUE': Using new connection on Empty exception".format(listener_id))
                            info("{}: event: '{}'".format(listener_id,event))
                            sse=ServerSentEvent(event,None)
                            yield sse.encode()
                            break
                    else:
                        info("{}: QTT_URLLIB_FIXED not in environ: Using new connection on Empty exception".format(listener_id))
                        info("{}: event: '{}'".format(listener_id,event))
                        sse=ServerSentEvent(event,None)
                        yield sse.encode()
                        break

                info("{}: event: '{}'".format(listener_id,event))
                sse=ServerSentEvent(event,None)
                yield sse.encode()

            info("{}: Stopping events listener...".format(listener_id))
            stop_listening.set()
            info("{}: Events listener stopped".format(listener_id))

    return Response(
        gen(node_name),
        mimetype="text/event-stream")


@app.route('/qiy_nodes/<node_name>/feed/<feed_id>')
def qiy_nodes_feed(node_name,feed_id):
    info("{}, {}".format(node_name,feed_id))

    text=node_feed(node_name,feed_id)

    return text


@app.route('/qiy_nodes/<node_name>/feeds')
def qiy_nodes_feeds(node_name):
    info("qiy_nodes_feeds({})".format(node_name))
    return """
<h1>Test Node {0}</h1>
<h2>Feeds</h2>
<ul>
<li><a href="/qiy_nodes/{0}/feeds/list">List feed id's.</a> (<a href="/qiy_nodes/{0}/feeds/list/raw">raw</a>)
<li><a href="/qiy_nodes/{0}/feeds/request">Request for feed.</a>
</ul>

<a href="/">Home</a>

""".format(node_name)


@app.route('/qiy_nodes/<node_name>/feeds/list')
def qiy_nodes_feeds_list(node_name):
    info("{}".format(node_name))

    feed_ids=node_feed_ids(node_name)

    lis=""
    for feed_id in feed_ids:
        li='<li><a href="/qiy_nodes/{0}/feed/{1}">{1}</a>\n'.format(
            node_name,
            feed_id
            )
        lis=lis+li

    page="""
<h1>Test Node {0}</h1>
<h2>Feeds - list</h2>

<ul>
{1}
</ul>

<a href="/qiy_nodes/{0}/feeds">Up</a>

""".format(node_name,lis)
    
    return page


@app.route('/qiy_nodes/<node_name>/feeds/list/raw')
def qiy_nodes_feeds_list_raw(node_name):
    info("{}".format(node_name))

    ids=node_feed_ids(node_name)
    
    return dumps(ids,indent=2)

@app.route('/qiy_nodes/<node_name>/feeds/request')
def qiy_nodes_feeds_request(node_name):
    info("qiy_nodes_feeds_request({})".format(node_name))

    connections=qiy_nodes_connections_json(node_name)

    lis=""
    for connection in connections:
        mbox_url=connections[connection]['links']['mbox']
        b64mbox_url=quote_plus(b64encode(mbox_url.encode()).decode())
        url="/qiy_nodes/{}/feeds/request/mbox/{}".format(node_name,b64mbox_url)
        li='<li>pid {0}: <a href="{1}">{2}</a>\n'.format(connections[connection]['pid'],
                                           url,
                                           dumps(connections[connection],indent=2))
        lis=lis+li

    page="""
<h1>Test Node {0}</h1>
<h2>Feeds - request for</h2>

<ul>
{1}
</ul>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,lis)
    return page


@app.route('/qiy_nodes/<node_name>/feeds/request/mbox/<path:b64_mbox_url>')
def qiy_nodes_feeds_request_mbox(node_name,b64_mbox_url,
                                 operationTypeUrl="https://github.com/qiyfoundation/fiKks/tree/master/schema/v1"
                                 ):
    info("qiy_nodes_feeds_request_mbox({},{})".format(node_name,b64_mbox_url))

    mbox_url=b64decode(b64_mbox_url).decode()

    body={
        "protocol": operationTypeUrl,
        "text": "Requesting feed."
    }
    headers={
        "Content-Type": "application/json"
    }

    r=node_request(data=dumps(body),
            headers=headers,
            node_name=node_name,
            operation="post",
            target=target,
            url=mbox_url
            )


    page="""
<h1>Test Node {0} qiy_nodes_feeds_request_mbox</h1>

mbox_url: {1}

Response: {2}
Headers: {3}

<p>
<a href="/qiy_nodes/{0}/feeds/request">Up</a>

""".format(node_name,mbox_url,r.status_code,r.headers)
    return page


@app.route('/qiy_nodes/<node_name>/messages/since/<path:minutes>')
def qiy_nodes_messages(node_name,minutes):
    info("qiy_nodes_messages({})".format(node_name))


    since=timegm(datetime.utcnow().timetuple())-(int(minutes)*60)
    print(since, datetime.utcfromtimestamp(since))
    since=since*1000
    messages={}

    response_messages_array=node_get_messages(node_name=node_name, since=since, target=target, version="1")
    for r, mbox_url, msgs in response_messages_array:
        messages[mbox_url]=msgs

    return """
<h1>Test Node {0} Messages</h1>

<pre>
{1}
</pre>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(messages,indent=2))

@app.route('/qiy_nodes/<node_name>/pid/<ub_pid>/<ub_connection>')
def qiy_nodes_pid(node_name,ub_pid,ub_connection):
    info("{} {} {}".format(node_name,ub_pid,ub_connection))

    connection_s=b64decode(unquote(ub_connection)).decode()
    connection=loads(connection_s)
    pid=b64decode(unquote(ub_pid)).decode()

    h={'pid':pid,'connection':connection}

    return """
<h1>Test Node {0}</h1>

<h2>pid</h2>

{1}
<p>

<pre>
{2}
</pre>
<a href="/qiy_nodes/{0}/pids">Up</a>

""".format(
    node_name,
    pid,
    dumps(h,indent=2)
    )


def qiy_nodes_pids_json(node_name):
    info("qiy_nodes_pids({})".format(node_name))

    connections=qiy_nodes_connections_json(node_name)
    pids={}
    for connection_id in connections:
        connection=connections[connection_id]
        if not 'parent' in connection['links']:
            pids[connection['activeFrom']+" "+connection['pid']]=connection
    sorted_pids = OrderedDict(sorted(pids.items(), key=lambda t: t[0],reverse=True))
    return sorted_pids

@app.route('/qiy_nodes/<node_name>/pids')
def qiy_nodes_pids(node_name):
    info("{}".format(node_name))

    connections=qiy_nodes_pids_json(node_name)

    rows=""

    for i in connections:
        connection=connections[i]
        ub_connection=quote_plus(b64encode(dumps(connection).encode()).decode())
        
        active_from=connection['activeFrom']
        parent=""
        if 'parent' in connection['links']:
            parent=connection['links']['parent']
        ub_parent=quote_plus(b64encode(parent.encode()).decode())
        pid=connection['pid']
        ub_pid=quote_plus(b64encode(pid.encode()).decode())
        state=connection['state']
        connection_url=connection['links']['self']
        ub_connection_url=quote_plus(b64encode(connection_url.encode()).decode())
        row='<tr><td>{0}</td><td><a href="/qiy_nodes/{1}/connection/{2}">{3}</a></td><td><a href="/qiy_nodes/{1}/pid/{4}/{5}">{6}</a></td><td>{7}</td><td><a href="/qiy_nodes/{1}/connection/{8}">{9}</a></td></tr>'.format(
            active_from,
            node_name,
            ub_connection_url,
            connection_url,
            ub_pid,
            ub_connection,
            pid,
            state,
            ub_parent,
            parent
            )
        rows="{}\n{}".format(rows,row)

    return """
<h1>Test Node {0}</h1>

<h2>pids</h2>

<table>
{1}
</table>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,rows)


#@app.route('/qiy_nodes/<path:node_name>/pids/<ub_pid>/references/<ub_references_url>')
@app.route('/qiy_nodes/<node_name>/pids/references/<ub_references_url>')
def qiy_nodes_pids_references(node_name,ub_references_url):
    info("qiy_nodes_pids_references({},{})".format(node_name,ub_references_url))
    print(ub_references_url)

    references={}
    b_references_url=unquote(ub_references_url)
    references_url=b64decode(b_references_url).decode()

    r=node_request(node_name=node_name,
                   target=target,
                   url=references_url
                   )
    if r.status_code==200:
        # Hyperlink ref to data page
        references_by_operation_type=r.json()
        for operation_type in references_by_operation_type:
            ref_connection_list=references_by_operation_type[operation_type]
            for ref_connection in ref_connection_list:
                feed_id=ref_connection['ref']
                link="/qiy_nodes/{}/pids/refs_feeds/{}/{}".format(node_name,quote_plus(ub_references_url),feed_id)
                href="<a href='{}'>{}</a>".format(link,feed_id)
                print(href)
                ref_connection['ref']=href

        # Ready.
        result=dumps(references_by_operation_type,indent=2)
    else:
        result=r.text

    return """
<h1>Test Node {0} Pids {1}</h1>
References

<pre>
{2}
</pre>

<a href="/qiy_nodes/{0}/pids">Up</a>

""".format(node_name,references_url,result)


#@app.route('/qiy_nodes/<path:node_name>/pids/<ub_pid>/references/<ub_references_url>')
@app.route('/qiy_nodes/<node_name>/pids/refs_feeds/<ub_references_url>/<feed_id>')
def qiy_nodes_pids_references_feeds(node_name,ub_references_url,feed_id):
    info("qiy_nodes_pids_references_feeds({},{},{})".format(node_name,ub_references_url,feed_id))

    b_references_url=unquote(ub_references_url)
    references_url=b64decode(b_references_url).decode()

    query_parameters={'id': feed_id}
    r=node_request(node_name=node_name,
                   query_parameters=query_parameters,
                   target=target,
                   url=references_url
                   )

    if r.status_code==200:
        result=dumps(r.json(),indent=2)
        b64value_refs_by_operation_type_url=r.json()
        for operation_type_url in b64value_refs_by_operation_type_url:
            b64value_refs=b64value_refs_by_operation_type_url[operation_type_url]
            if len(b64value_refs) > 0:
                b64value_ref=b64value_refs[0]
                #print(b64value_ref)
                if 'value' in b64value_ref:
                    data=b64decode(b64value_ref['value'].encode()).decode()
                    data=data.replace("<","&lt;")
                    result=data.replace(">","&gt;")
    else:
        result=r.text

    return """
<h1>Test Node {0} Pids references Feeds</h1>
References_url {1}<br>
Feed {2}

<pre>
{3}
</pre>

<a href="/qiy_nodes/{0}/pids">Up</a>

""".format(node_name,references_url,feed_id,result)


@app.route('/qiy_nodes/<node_name>/redirect_to_eformulieren/<path:u_url>')
def qiy_nodes_redirect_to_eformulieren(node_name,u_url):
    info("qiy_nodes_redirect_to_eformulieren({})".format(node_name,u_url))

#    url="http://scooterlabs.com/echo"
    url=unquote(u_url)
    return_url="http://scooterlabs.com/echo"
    u_return_url=quote_plus(return_url)

    if target=="dev2":
        ct_target="https://dev2-issuer.testonly.digital-me.nl/issuer/routes/webhook/{}".format(uuid4())
    elif target=="acc":
        ct_target="https://issuer.dolden.net/issuer/routes/webhook/{}".format(uuid4())
    else:
        ct_target="https://issuer.digital-me.nl/issuer/routes/webhook/{}".format(uuid4())

    connect_token_json={
      "tmpSecret": "VZx57LD1mOZggDrhOBYIEA==",
      "target": ct_target,
      "identifier": "test helper {}".format(datetime.utcnow().isoformat())
    }
    ub_connect_token=quote_plus(b64encode(dumps(connect_token_json).encode()).decode())
    redirect_url="{}?returnUrl={}&connectToken={}".format(url,u_return_url,ub_connect_token)

    return """
<h1>Test Node {0} Redirect to eFormulieren</h1>

click here to redirect: <a href="{1}">{1}</a>


<p>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,redirect_url)


@app.route('/qiy_nodes/<node_name>/service_catalogue')
def qiy_nodes_service_catalogue(node_name):
    info("{}".format(node_name))

    service_catalogue=node_service_catalogue(node_name,target=target)

    page="""
<h1>Test Node {0}</h1>
<h2>Service catalogue</h2>

<pre>
{1}
</pre>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(service_catalogue,indent=2))
    
    return page

@app.route('/service_types/<ub_service_type>')
def qtt_service_types(ub_service_type):
    info("{}".format(ub_service_type))

    service_type=ub_decode(ub_service_type)

    data_providers=node_data_providers(service_type_url=service_type,
                                       target=target)

    lis=""
    for i in data_providers:
        li='<li><a href="/service_types/{0}/data_providers/{1}">{1}</a>'.format(ub_service_type,i)
        lis="{}{}\n".format(lis,li)

    data_provider_lis=lis
    return """
<h1>Service type {0}</h1>

<h2>Data providers</h2>
<ul>
{1}
</ul>
<a href="/">Up</a>

""".format(service_type,
           data_provider_lis,
           )


@app.route('/service_types/<ub_service_type>/data_providers/<data_provider>')
def qtt_service_types_data_providers(ub_service_type,data_provider):
    info("{}".format(ub_service_type,data_provider))

    service_type=ub_decode(ub_service_type)

    return """
<h1>Service type {0}</h1>

<h2>Data provider {1}</h2>

tbd

<p>
<a href="/service_types/{2}">Up</a>

""".format(service_type,
           data_provider,
           ub_service_type,
           )


@app.route('/connection_url_event_source/<path:webhook_url>')
def connection_url_event_source(webhook_url):
    warning("connection_url_event_source() started - deprecated")
    def gen() -> Iterator[str]:
        while True: # Dev
#            sse = ServerSentEvent(str("0. webhook: '{0}'".format(webhook_url)), None)
#            yield sse.encode()
#            sleep(1)
            # 1. Get connection url of new connection from CONNECTED_TO_ROUTER.connectionUrl.
            new_connection_url=get_new_connection_url(webhook_url)
            sse = ServerSentEvent(str("1. new connection_url: '{0}'".format(new_connection_url)), None)
            yield sse.encode()
            sleep(1)
            # 2. Get connection url of first connection from STATE_HANDLED.extraData
            first_connection_url=get_first_connection_url(webhook_url)
            sse = ServerSentEvent(str("2. first connection_url: '{0}'".format(first_connection_url)), None)
            yield sse.encode()
            sleep(1)
            # 3. Get messages from first connection
            event="3. here come the messages from first_connection_url {0}!! :-)".format(first_conenction_url)
            sse = ServerSentEvent(event, None)
            yield sse.encode()
            sleep(1)
            node_name=environ['NODE_NAME']
            target=environ['TARGET']
            for message in message_listener(connection_url=first_connetion_url,node_name=node_name,target=target):
                page_with_messages="4. Messages:\n{0}".format(message)
                sse=ServerSentEvent(page_with_messages, None)
                yield sse.encode()
                sleep(1)

    return Response(
        gen(),
        mimetype="text/event-stream")



