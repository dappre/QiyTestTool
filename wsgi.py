from base64 import b64decode
from base64 import b64encode
from calendar import timegm
from collections import OrderedDict
from datetime import datetime
from flask import Flask, Response, request
from flask import Response
from flask import send_from_directory
from flask import url_for
from glob import glob
from gzip import compress
from gzip import decompress
from html import escape
from json import load
from json import loads
from json import dumps
from json.decoder import JSONDecodeError
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
from pathlib import Path
from queue import Queue
from queue import Empty
from QiyNodeLib.QiyNodeLib import node_auth_header
from QiyNodeLib.QiyNodeLib import node_create
from QiyNodeLib.QiyNodeLib import node_connect
from QiyNodeLib.QiyNodeLib import node_connect_token__create
from QiyNodeLib.QiyNodeLib import node_endpoint
from QiyNodeLib.QiyNodeLib import node_get_messages
from QiyNodeLib.QiyNodeLib import node_request
from QiyNodeLib.QiyNodeLib import node_transport_password
from QiyNodeLib.QiyNodeLib import pretty_print
from re import findall
from re import fullmatch
from requests.exceptions import ChunkedEncodingError
from shutil import move
from socket import getfqdn
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
from urllib.parse import urlparse

import flask_sse
import pymongo
import random
import requests
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
if not environ['TARGET'] in ['local','dev2','acc']:
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


application = Flask(__name__)

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

@application.route('/favicon.ico')
def favicon():
    return send_from_directory(join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@application.route('/')
def root():
    info("root()")

    service_types=node_service_types(target=target)
    service_type_lis=""
    for i in service_types:
        service_type_lis=service_type_lis+'<li><a href="service_types/{0}">{1}</a>\n'.format(ub_encode(i),i)
       
    ids=node_ids(target=target)
    lis=""
    report=""
    for i in ids:
        lis=lis+'<li><a href="qiy_nodes/{0}">{0}</a>'.format(i)
        if not node_is_accessible(i,target=target):
            msg="NB: node '{}' is not accessible; please fix before continuing!".format(i)
            report="{}\n<p>\n{}".format(report,msg)
    
    return """<!DOCTYPE html>
<html>
<body>

<h1>Qiy Test Tool</h1>

A tool to assist Qiy integration.<p>

Some links:
<ul>
<li><a href="https://github.com/digital-me/QiyTestTool">Server source code on Github</a>
<li><a href="https://qiy.api.digital-me.nl/">Api used to access the Qiy Trust Network</a>
<li><a href="https://digital-me.nl">The access provider for the Qiy Trust Network</a>
<li><a href="https://github.com/qiyfoundation/Qiy-Scheme/blob/topic/Qiy-Scheme-v1.1/High-Level%20Architectural%20Overview.md#21-data-reuse">How the Qiy Trust Network can be used to control your data</a>
<li><a href="https://qiyfoundation.org/">The Qiy Scheme (standards behind the Qiy Trust Network) are maintained by members of the Qiy Foundation</a>.
</ul>

<p>
freek.driesenaar@digital-me.nl
8-2019

{2}

<h2>Service types</h2>

<ul>
{0}
</ul>

<h3>Add service type</h3>

<form action="/service_types_create" method="get">
<table><tr><td>
  Service type:</td><td><input type="text" name="service_type_url" value="https://service_type_url">
  </td></tr><tr><td>
  Data provider name:</td><td><input type="text" name="data_provider_name" value="dp">
  </td></tr><tr><td>
  Service Endpoint type:</td><td><input type="text" name="service_endpoint_type" value="external">
  </td></tr><tr><td>
  Service Endpoint url:</td><td><input type="text" name="service_endpoint_url" value="">
  </td></tr><tr><td>
  Service Endpoint method:</td><td><input type="text" name="service_endpoint_method" value="POST">
  </td></tr>
</table>
  <br>
  <input type="submit" value="Submit">
</form>

<h2>Test nodes</h2>
<ul>
{1}
</ul>

<h3>Add node</h3>

<form action="/qiy_nodes_create" method="get">
<table><tr><td>
  Node name:</td><td><input type="text" name="node_name" value="dp">
  </td></tr>
</table>
  <br>
  <input type="submit" value="Submit">
</form>


</body>
</html>
""".format(service_type_lis,
           lis,
           report,
           )

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

def node_connection(
    node_name=None,
    pid=None,
    target=None,
    ):

    connection=None
    connections=node_connections(node_name=node_name, target=target)
    for i in connections:
        if i['pid']==pid:
            connection=i

    return connection

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

def node_connection_feed_access_encrypted(
    connection_url=None,
    exponent=None,
    feed_id=None,
    modulus=None,
    node_name=None,
    target=None,
              ):
    
    headers={'Accept': 'application/json'}
    r=node_request(url=connection_url,
                   headers=headers,
                   node_name=node_name,
                   target=target)

    connection_feeds_url=r.json()['links']['feeds']

    url="{}/{}".format(connection_feeds_url,
                       feed_id)
    body="""<?xml version="1.0" encoding="UTF-8"?>
<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:KeyValue>
        <ds:RSAKeyValue>
            <ds:Modulus>{}</ds:Modulus>
            <ds:Exponent>{}</ds:Exponent>
        </ds:RSAKeyValue>
    </ds:KeyValue>
</ds:KeyInfo>""".format(modulus,exponent)
    data=body
    headers={'Content-Type':'application/xml', 'Accept': 'application/xml'}

    r=node_request(
        data=data,
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target,
        url=url,
        )
    return r

def node_connection_feed_access_unencrypted(
    node_name=None,
    connection_url=None,
    feed_id=None,
    target=None,
              ):
    headers={'Accept': 'application/json'}
    r=node_request(url=connection_url,
                   headers=headers,
                   node_name=node_name,
                   target=target)

    connection_feeds_url=r.json()['links']['feeds']

    url="{}/{}".format(connection_feeds_url,
                       feed_id)
    r=node_request(
        url=url,
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target)
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

def node_connections(
    node_name=None,
    target=None,
    ):

    connections=node_request(endpoint_name="connections", node_name=node_name, target=target).json()['result']
    
    return connections

def node_data_providers(
    service_type_url=None,
    target=None,
    ):
    node_names=node_ids(target=target)
    data_providers=[]
    
    for i in node_names:
        service_catalogue=node_service_catalogue_get(i,target=target).json()
        for url in service_catalogue:
            if url == service_type_url:
                data_providers.append(i)

    return data_providers

def node_feed_ids_list(
    service_type_url=None,
    target=None,
    ):
    node_names=node_ids(target=target)
    feed_ids={}
    
    for i in node_names:
        feed_ids[i]=[]
        feeds=node_feed_ids(
            i,
            service_type_url=service_type_url,
            target=target,
            )
        for j in feeds:
            feed_ids[i].append(j)

    return feed_ids

def node_feed_ids(node_name,
                  service_type_url=None,
                  target=None,
                  ):
    query_parameters=None
    if not service_type_url is None:
        query_parameters={'operation':ub_encode(service_type_url)}
    headers={'Accept': 'application/json'}
    r=node_request(endpoint_name="feeds",
                   headers=headers,
                   node_name=node_name,
                   query_parameters=query_parameters,
                   target=target,
                   )
    return r.json()

def node_feed_access_encrypted(
    node_name,
    feed_id,
    exponent=None,
    headers={'Accept': 'application/xml', 'Content-Type': 'application/xml'},
    modulus=None,
    target=target,
    ):

    r=node_request(
        node_name=node_name,
        target=target)
    feeds_endpoint_url=r.json()['links']['feeds']

    url="{}/{}".format(feeds_endpoint_url, feed_id)

    body="""<?xml version="1.0" encoding="UTF-8"?>
<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <ds:KeyValue>
        <ds:RSAKeyValue>
            <ds:Modulus>{}</ds:Modulus>
            <ds:Exponent>{}</ds:Exponent>
        </ds:RSAKeyValue>
    </ds:KeyValue>
</ds:KeyInfo>""".format(modulus,exponent)
    data=body

    r=node_request(
        data=data,
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target,
        url=url,
        )
    return r

def node_feed_access_unencrypted(node_name,feed_id,
              headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
              target=target,
              ):
    r=node_request(
        node_name=node_name,
        target=target)
    feeds_endpoint_url=r.json()['links']['feeds']

    url="{}/{}".format(feeds_endpoint_url, feed_id)

    r=node_request(
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target,
        url=url,
        )
    return r

def node_feed_request(
    body_dot_input=None,
    connection=None,
    orchestrator=None,
    feeds_url=None,
    pid=None,
    relying_party=None,
    service_type_url=None,
    target=None,
    ):

    r=None

    if not feeds_url is None:
        info("feeds_url: {}".format(feeds_url))
        b64_input=None
        if not body_dot_input is None:
            b64_input=b64encode(body_dot_input)
        body={
          "protocol": service_type_url,
          "text": "Requesting feed.",
          "input": b64_input
        }
        data=dumps(body)
        r=node_request(
            data=data,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'password': node_transport_password(node_name=relying_party,target=target)
            },
            operation="post",
            node_name=relying_party,
            target=target,
            url=feeds_url,
            )
        
    elif not connection is None:
        info("connection: {}".format(connection))
        feeds_url=connection['links']['feeds']
        r=node_feed_request(
            body_dot_input=body_dot_input,
            feeds_url=feeds_url,
            relying_party=relying_party,
            service_type_url=service_type_url,
            target=target,
            )

    elif not pid is None:
        info("pid: {}".format(pid))
        connection=node_connection(
            node_name=relying_party,
            pid=pid,
            target=target,
            )

        r=node_feed_request(
            body_dot_input=body_dot_input,
            connection=connection,
            relying_party=relying_party,
            service_type_url=service_type_url,
            target=target,
            )

    elif not orchestrator is None:
        info("orchestrator: {}".format(orchestrator))
        pid=node_pid(
            node_names=[relying_party,orchestrator],
            target=target,
            )

        r=node_feed_request(
            body_dot_input=body_dot_input,
            relying_party=relying_party,
            pid=pid,
            service_type_url=service_type_url,
            target=target,
            )
    
    return r

def node_feeds_access_unencrypted(node_name,feed_id,
              headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
              target=target,
              ):
    body={feed_id: {'input': ''}}
    body=None
    data=dumps(body)
    data=None
#    print(data)
    r=node_request(
        data=data,
        endpoint_name="feeds",
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target)
    return r

def node_feeds_access_unencrypted(node_name,feed_id,
              headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
              target=target,
              ):
    body={feed_id: {'input': ''}}
    body=None
    data=dumps(body)
    data=None
#    print(data)
    r=node_request(
        data=data,
        endpoint_name="feeds",
        headers=headers,
        node_name=node_name,
        operation="post",
        target=target)
    return r

def node_is_accessible(node_name=None,target=None):
    r=node_request(node_name=node_name,target=target)
    return r.status_code==200

def node_orchestrators(
        service_type_url=None,
        target=None
        ):
    orchestrators=[]

    data_providers=node_data_providers(service_type_url=service_type_url,
                                       target=target)
    for i in data_providers:
        for name in node_connected_node_names(i,target=target):
            if not name in orchestrators:
                orchestrators.append(name)
    return orchestrators

def node_pid(
    node_names=None,
    pid=None,
    target=target,
    ):

    pid=None

    if len(node_names)==2:
        pids=[]
        for n in node_names:
            connections=node_connections(n, target=target)
            for c in connections:
                p=c['pid']
                if p in pids:
                    pid=p
                    break
                else:
                    pids.append(p)

    return pid

def node_service_catalogue_get(
    node_name,
    target=None,
    ):
    headers={'Accept': 'application/json'}
    r=node_request(endpoint_name="serviceCatalog",
                   headers=headers,
                   node_name=node_name,
                   target=target)
    return r

def node_service_catalogue_set(
    node_name,
    service_catalogue=None,
    target=None,
    ):
    headers={'Content-Type': 'application/json'}
    data=dumps(service_catalogue)
    r=node_request(
        data=data,
        endpoint_name="serviceCatalog",
        headers=headers,
        node_name=node_name,
        operation="put",
        target=target,
        )
    return r

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
        try:
            service_catalogue=node_service_catalogue_get(i,target=target).json()
            for service_type_url in service_catalogue:
                if not service_type_url in service_types:
                    service_types.append(service_type_url)
        except JSONDecodeError:
            msg="Skipping '{}' for JSONDecodeError".format(i)
            warning(msg)
            continue

    return service_types

def request_to_str(r,r_is_request=False):
    if not r_is_request:
        response=r
        request=response.request
    else:
        response=None
        request=r

    s="\n"
    s=s+"-------------------------------------------------------------------------------------------\n"
    s=s+"Request:\n"
    s=s+"{0} {1} HTTP/1.1\n".format(request.method,request.url)
    s=s+"\n"
    headers=request.headers
    for header in headers:
        if r_is_request:
            s=s+"{0}\n".format(header)
        else:
            s=s+"{0}: {1}\n".format(header,headers[header])
    if r_is_request:
        body=str(request.data)
    else:
        body=request.body
    s=s+str(body)
    if not response is None:
        s=s+"\n"
        s=s+"\n\n"
        s=s+"Response:\n"
        s=s+str(response.status_code)+"\n"
        headers=response.headers
        for header in headers:
            s=s+"{0}: {1}\n".format(header,headers[header])
        s=s+"\n"
        s=s+response.text
    s=s+"\n-------------------------------------------------------------------------------------------\n"
    
    return s

def response_to_str(response):
    s="-------------------------------------------------------------------------------------------\n"
    s=s+"Response:\n"
    s=s+str(response.status_code)+"\n"
    headers=response.headers
    for header in headers:
        s=s+"{0}: {1}\n".format(header,headers[header])
    s=s+"\n"
    s=s+response.text
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

@application.route('/data_provider/<data_provider_name>/service_type/<ub_service_type_url>/service_endpoint/feeds/callback', methods=['get','post'])
def data_provider_service_type_service_endpoint_feeds_callback(data_provider_name,ub_service_type_url):
    info("{} {}".format(data_provider_name,ub_service_type_url))

    feed_id="9238475982347"
    body={
        "id": feed_id
    }
    data=dumps(body)
    headers=None
    response = Response(data, status=201, mimetype='application/json')

    return response


@application.route('/data_provider/<data_provider_name>/service_type/<ub_service_type_url>/service_endpoint/feeds/callback/resolve', methods=['get','post'])
def data_provider_service_type_service_endpoint_feeds_callback_resolve(data_provider_name,ub_service_type_url):
    info("{} {}".format(data_provider_name,ub_service_type_url))

    info("incoming request: '{}'".format(request_to_str(request,r_is_request=True)))

    service_type_url=ub_decode(ub_service_type_url)

    response=""
    headers=None
    data=None

    if not response:
        info("# Check remote address")
        trusted_hosts="127.0.0.1"
        if 'QTT_TRUSTED_HOSTS' in environ:
            trusted_hosts=getenv('QTT_TRUSTED_HOSTS')
        if not request.remote_addr in trusted_hosts:
            warning("Request origin '{}' not in trusted hosts '{}' for service type url {} for Data provider {}.".format(request.remote_addr,trusted_hosts,service_type_url,data_provider_name))
            response = Response(data, status=403, mimetype='text/plain')

    info("# Check data provider")
    if not data_provider_name in node_ids(target=target):
        warning("Data provider {} not found.".format(data_provider_name))
        response = Response(data, status=403, mimetype='text/plain')
    
    if not response:
        info("# Check service type")
        service_catalogue=node_service_catalogue_get(
            node_name=data_provider_name,
            target=target,
            ).json()
        info("service_catalogue: '{}'".format(service_catalogue))
        if not service_type_url in service_catalogue:
            warning("Service type url {} not found for Data provider {} in catalogue '{}'.".format(service_type_url,data_provider_name,dumps(service_catalogue,indent=2)))
            response = Response(data, status=403, mimetype='text/plain')
    
    if not response:
        info("# Check callback url")
        service_endpoint_description=service_catalogue[service_type_url]
        callback_url=request.url.replace("/resolve","")
        if not callback_url == service_endpoint_description['uri']:
            warning("Url '{}' not found for service type url {} for Data provider {}.".format(callback_url,service_type_url,data_provider_name))
            response = Response(data, status=403, mimetype='text/plain')

    if not response:
        info("# Check Content-Type for being application/json")
        if not request.is_json:
            warning("Content-Type is not application/json for service type url {} for Data provider {}".format(service_type_url,data_provider_name))
            response = Response(data, status=403, mimetype='text/plain')

    if not response:
        info("# Check body for being json")
        info("# - headers: '{}'".format(request.headers))

        try:
            if 'Content-Encoding' in request.headers:
                if 'gzip' in request.headers['Content-Encoding']:
                    s=decompress(request.data)
                else:
                    s=request.data.decode()
            else:
                    s=request.data.decode()               
            body=loads(s)
        except JSONDecodeError:
            warning("Body does not contain json for service type url {} for Data provider {}:\nbody: '{}'.".format(service_type_url,data_provider_name,request.get_data()))
            response = Response(data, status=403, mimetype='text/plain')

    if not response:
        info("# Check body format")
        msg=""
        
        info("# Checking body for not being empty")
        if body=={}:
            msg="Empty body"

        if not msg:
            info("# Checking members for containing json objects") # "<feed_id>": { ... }
            for feed_id in body:
                if not type(body[feed_id])==dict:
                    msg="member '{}' does not contain a json object".format(body[feed_id])
                    break
        
        if msg:
            warning("{} for service type url {} for Data provider {} and body: '{}'".format(msg,service_type_url,data_provider_name,request.get_data()))
            response = Response(data, status=403, mimetype='text/plain')

    if not response:
        info("# Process feed ids")
        feed_access_requests=body
        
        body={}
        
        for feed_id in feed_access_requests:
            info("Processing feed id '{}'".format(feed_id))
            access_request_parameters=None
            access_request=feed_access_requests[feed_id]
            if 'input' in access_request:
                b64=access_request['input']
                if not b64 is None:
                    access_request_parameters=b64decode(b64).decode()        
            output=None
            feed_contents=access_feed(
                data_provider_name,
                service_type_url,
                feed_id,
                access_request_parameters,
                )
            body[feed_id]=feed_contents
        
        data=dumps(body)

        if 'Accept-Encoding' in request.headers:
            if 'gzip' in request.headers['Accept-Encoding']:
                data=compress(data.encode())
                headers={'Content-Encoding':'gzip'}

        response = Response(data, headers=headers, status=200, mimetype='application/json')

    info("# Returning data: '{}', headers: '{}', and response: '{}'".format(data,headers,response))

    return response

def access_feed(data_provider_name,
                service_type_url,
                feed_id,
                access_request_parameters):
    feed_contents={'output': None}
    
    feeds_path='.'
    if 'QTT_FEEDS_PATH' in environ:
        feeds_path=expanduser(getenv('QTT_FEEDS_PATH'))
    ub_service_type_url=ub_encode(service_type_url)
    feeds_path=join(feeds_path,ub_service_type_url)
    feed_path=join(feeds_path,feed_id+".json")

    filenames=glob(feed_path)

    if not len(filenames):
        warning("No contents found for feed_id '{}' with path '{}'".format(feed_id,feed_path))
    else:
        filename=filenames[0]
        with open(filename,'r') as f:
            feed_contents=load(f)

    return feed_contents

@application.route('/qiy_nodes_create',methods=['get'])
def qiy_nodes_create():
    info("start")

    node_name = request.args.get('node_name')

    report=""
    status_code=200

    if not node_name in node_ids(target=target):
        report="creating node..."
        r=node_create(
            node_id=str(uuid4()),
            node_name=node_name,
            target=target,
            )
        if r.status_code==201:
            report="node created :-)"
        else:
            status_code=r.status_code
            report="Error creating node :-(, \n{}".format(request_to_str(r))
            
    else:
        report="Node not created; already exists '{}'".format(node_name)
    
    return """
<h1>Qiy node</h1>

node name: {}<br>
<p>

report:<br>
<pre>{}</pre>

<p><a href="/">Up</a>
""".format(
    node_name,
    report,
    )


@application.route('/qiy_nodes/<node_name>')
def qiy_nodes(node_name):
    info("qiy_node({})".format(node_name))

    u_redirect_url=quote_plus("https://test-einwoner.lostlemon.nl/test/qtn/Boxtel")

    body=""
    if not node_is_accessible(node_name=node_name,target=target):
        body="NB: The node is not accessible: please consider removing it's Qiy Node Credential."
    else:
        body="""
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
<li><a href="/qiy_nodes/{0}/proxy/example_request">Proxy (example request)</a>
<li><a href="/qiy_nodes/{0}/pids">Pids</a>
<li><a href="/qiy_nodes/{0}/redirect_to_eformulieren/{1}">Redirect to Lost Lemon eFormulieren</a>
</ul>
""".format(node_name,u_redirect_url)

    return """
<h1>Test Node {0}</h1>

{1}

<p>
<a href="/">Home</a>

""".format(node_name,body)


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


@application.route('/qiy_nodes/<node_name>/action_messages')
def qiy_nodes_action_messages(node_name):
    info("qiy_nodes_action_messages({})".format(node_name))

    action_messages=qiy_nodes_action_messages_json(node_name)
    lis=""
    for amid in action_messages:
        action_message=action_messages[amid]
        li='<li>{0}: <pre>{1}</pre>'.format(amid, dumps(action_message,indent=2))
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


@application.route('/qiy_nodes/<node_name>/action_messages/relay_options/get/<path:b64_relay_option>')
def qiy_nodes_action_messages_relay_options_get(node_name,b64_relay_option):
    info("qiy_nodes_action_messages_relay_options_get({},{})".format(node_name,b64_relay_option))

    relay_option=b64decode(b64_relay_option.encode()).decode()

    r=node_request(node_name=node_name,
            operation="post",
#            operation="put",
            target=target,
            url=relay_option
            )
    s=request_to_str(r)

    return """
<h1>Test Node {0} - Action messages - Relay options - get</h1>

Relay option: {1}
<p>
<pre>
{2}
</pre>
<a href="/qiy_nodes/{0}/action_messages">Up</a>

""".format(node_name,
           relay_option,
           s)


@application.route('/qiy_nodes/<node_name>/connect')
def qiy_nodes_connect(node_name):
    info("{}".format(node_name))

    return """
<h1>Test Node {0}</h1>

<h2>Connect</h2>

<ul>
<li><a href="/qiy_nodes/{0}/connect_using_connect_token/home">Connect using connect token</a>
<li><a href="/qiy_nodes/{0}/connect_with_node">Connect with node</a>
</ul>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name)

@application.route('/qiy_nodes/<node_name>/connect_using_connect_token/connect_token')
def qiy_nodes_connect_using_connect_token_connect_token(node_name):
    info("{}".format(node_name))

    connect_token = request.args.get('connect_token')
    print(connect_token)
    connect_token = loads(connect_token)

    r=node_connect(
        connect_token=connect_token,
        node_name=node_name,
        target=target,
        )

    html="<pre>\n{}\n</pre>".format(escape(request_to_str(r)))

    return """
<h1>Test Node {0}</h1>

<h2>Connect using connect token</h2>
connect_token: {1}

<p>
{2}

<p>
<a href="/qiy_nodes/{0}/connect">Up</a>

""".format(
    node_name,
    connect_token,
    html,
    )


@application.route('/qiy_nodes/<node_name>/connect_using_connect_token/home')
def qiy_nodes_connect_using_connect_token(node_name):
    info("{}".format(node_name))

    html="""
<form action="/qiy_nodes/{}/connect_using_connect_token/connect_token" method="get">
  Connect token:<br>
  <input type="text" name="connect_token" value="">
  <br>
  <input type="submit" value="Submit">
</form>
""".format(node_name)

    return """
<h1>Test Node {0}</h1>

<h2>Connect using connect token</h2>

{1}

<p>
<a href="/qiy_nodes/{0}/connect">Up</a>

""".format(
    node_name,
    html,
    )


@application.route('/qiy_nodes/<node_name>/connect_with_node')
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


@application.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>')
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


@application.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>/with_new_connect_token/as_consumer')
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


@application.route('/qiy_nodes/<node_name>/connect_with_other_node/<other_node_name>/with_new_connect_token/as_producer')
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


@application.route('/qiy_nodes/<node_name>/connected_nodes')
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


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>')
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


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/delete')
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


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feed/<feed_id>/access/encrypted')
def qiy_nodes_connection_feed_access_encrypted(node_name,ub_connection_url,feed_id):
    info("{} {}".format(node_name,ub_connection_url,feed_id))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    exponent="AQAB"
    modulus="6sNhgtNVksGD4ZK1rW2iiGO11O/BzEIZazovnMK37y3RVvvjmv1z44uA505gyyUTziCntHV9tONmJ11bH4koqqJQFZPXuKAyuu9eR3W/pZ4EGBMMIVH2aqSOsPMTI5K9l2YOW8fAoEZQtYVWsCrygOyctBiamJZRJ+AKFZCIY5E="

    r=node_connection_feed_access_encrypted(
        node_name=node_name,
        modulus=modulus,
        connection_url=connection_url,
        exponent=exponent,
        feed_id=feed_id,
        target=target,
        )
    s=escape(request_to_str(r))

    return """
<h1>Test Node {0}</h1>

<h2>Connection feed access encrypted</h2>
connection_url: {1}<br>
feed_id: {2}

<p>
<pre>
{3}
</pre>

<p>
<a href="/qiy_nodes/{0}/connection/{4}/feed/{2}/home">Up</a>

""".format(node_name,
           connection_url,
           feed_id,
           s,
           ub_connection_url,
           )


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feed/<feed_id>/access/unencrypted')
def qiy_nodes_connection_feed_access_unencrypted(node_name,ub_connection_url,feed_id):
    info("{} {}".format(node_name,ub_connection_url,feed_id))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    r=node_connection_feed_access_unencrypted(
        node_name=node_name,
        connection_url=connection_url,
        feed_id=feed_id,
        target=target,
        )
    s=escape(request_to_str(r))

    return """
<h1>Test Node {0}</h1>

<h2>Connection feed access unencrypted</h2>
connection_url: {1}<br>
feed_id: {2}

<p>
<pre>
{3}
</pre>

<p>
<a href="/qiy_nodes/{0}/connection/{4}/feed/{2}/home">Up</a>
""".format(node_name,
           connection_url,
           feed_id,
           s,
           ub_connection_url,
           )


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feed/<feed_id>/home')
def qiy_nodes_connection_feed_home(node_name,ub_connection_url,feed_id):
    info("{} {}".format(node_name,ub_connection_url,feed_id))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    lis=""
    li='<li><a href="/qiy_nodes/{0}/connection/{1}/feed/{2}/access/encrypted">Access feed encrypted</a>'.format(node_name,ub_connection_url,feed_id)
    lis="{}{}\n".format(lis,li)
    li='<li><a href="/qiy_nodes/{0}/connection/{1}/feed/{2}/access/unencrypted">Access feed unencrypted</a>'.format(node_name,ub_connection_url,feed_id)
    lis="{}{}\n".format(lis,li)

    html="""<ul>
{}
</ul>""".format(lis)
    
    return """
<h1>Test Node {0}</h1>

<h2>Connection feed home</h2>
connection_url: {1}<br>
feed_id: {2}

<p>
{3}
<p>
<a href="/qiy_nodes/{0}/connection/{4}/feeds/list">Up</a>

""".format(node_name,
           connection_url,
           feed_id,
           html,
           ub_connection_url,
           )


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds')
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


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds/list')
def qiy_nodes_connection_feeds_list(node_name,ub_connection_url):
    info("{} {}".format(node_name,ub_connection_url))

    connection_url=b64decode(unquote(ub_connection_url)).decode()

    feed_ids=node_connection_feed_ids(node_name,connection_url)

    lis=""
    for feed_id in feed_ids:
        li='<li><a href="/qiy_nodes/{0}/connection/{1}/feed/{2}/home">{2}</a>\n'.format(
            node_name,
            ub_connection_url,
            feed_id,
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


@application.route('/qiy_nodes/<node_name>/connection/<ub_connection_url>/feeds/request')
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


@application.route('/qiy_nodes/<node_name>/connections')
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

@application.route('/qiy_nodes/<node_name>/connections/references')
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

@application.route('/qiy_nodes/<node_name>/connect_tokens')
def qiy_nodes_connect_tokens(node_name):
    info("qiy_nodes_connect_tokens({})".format(node_name))

    connection_tokens=qiy_nodes_connect_tokens_json(node_name)

    new_connect_token=node_connect_token__create(
        node_name=node_name,
        target=target,
        )

    return """
<h1>Test Node {0}  Connect Tokens</h1>

<pre>
{1}
</pre>
<h1>New one</h1>
<pre>
{2}
</pre>

<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(connection_tokens,indent=2),
           dumps(new_connect_token))

@application.route('/qiy_nodes/<node_name>/consume_connect_token')
def qiy_nodes_consume_connect_token(node_name):
    info("qiy_nodes_consume_connect_token({})".format(node_name))

    return """
<h1>Test Node {0}  consume_connect_token</h1>

<ul>
<li><a href="/qiy_nodes/{0}/consume_connect_token/of/{1}">of {1}</a>
</ul>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,"mgd_dev2")

@application.route('/qiy_nodes/<node_name>/consume_connect_token/of/<path:producer>')
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


@application.route('/qiy_nodes/<node_name>/consume_connect_token/value/<path:b64_connect_token>')
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

@application.route('/qiy_nodes/<node_name>/event_callback_addresses')
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

@application.route('/qiy_nodes/<node_name>/events')
def qiy_nodes_events(node_name):
    info("qiy_nodes_events({})".format(node_name))
    return """
<h1>Test Node {0}</h1>
<h2>Listen to events</h2>

<p id="events"></p>
<p>
<a href="/qiy_nodes/{0}">Up</a>

<script>
const url="/qiy_nodes/{0}/events"
fetch(url) // Call the fetch function passing the url of the API as a parameter
.then(function() {{
    // Your code for handling the data you get from the API
    console.log('no problem accessing events source')
}})
.catch(function() {{
    // This is where you run code if the server returns any errors
    console.log('problem accessing events source')
}});
try {{
  var el = document.getElementById('events');
  el.innerHTML = "Start"
  var eventEventSource = new EventSource('/qiy_nodes/{0}/events/source');
  eventEventSource.onmessage = function(m) {{
	console.log(m);
	var el = document.getElementById('events');
	el.innerHTML = m.data + "<br>" + el.innerHTML;
  }}
}}
catch(error) {{
  console.error(error);
}}
</script>

""".format(node_name)


@application.route('/qiy_nodes/<node_name>/events/source')
def qiy_nodes_events_source(node_name):
    info("{0}".format(node_name))

    def gen(node_name) -> Iterator[str]:
            listener_id=generate_id()
            msg="{}: Starting events listener...".format(listener_id)
            info(msg)
            sse=ServerSentEvent(msg,None)
            yield sse.encode()
            
            stop_listening=Event()
            queue=Queue()
            listen_to_node(queue,stop_listening,node_name=node_name)
            info("{}: Events listener started.".format(listener_id))

            while True:
                try:
                    event="{}: '{}'".format(listener_id,queue.get(timeout=100))
                except Empty:
                    msg="{}: catched Empty exception".format(listener_id)
                    warning(msg)
                    sse=ServerSentEvent(event,None)
                    yield sse.encode()
                    
                    if 'QTT_URLLIB_FIXED' in environ:
                        if getenv('QTT_URLLIB_FIXED')=='TRUE':
                            info("{}: QTT_URLLIB_FIXED=='TRUE': Reusing connection on Empty exception".format(listener_id))
                        else:
                            info("{}: QTT_URLLIB_FIXED!='TRUE': Using new connection on Empty exception".format(listener_id))
                            info("event: '{}'".format(event))
                            sse=ServerSentEvent(event,None)
                            yield sse.encode()
                            break
                    else:
                        info("{}: QTT_URLLIB_FIXED not in environ: Using new connection on Empty exception".format(listener_id))
                        info("event: '{}'".format(event))
                        sse=ServerSentEvent(event,None)
                        yield sse.encode()
                        break

                info("event: '{}'".format(event))
                sse=ServerSentEvent(event,None)
                yield sse.encode()

            msg="{}: Stopping events listener...".format(listener_id)
            info(msg)
            
            stop_listening.set()
            msg="{}: Events listener stopped".format(listener_id)
            info(msg)
            sse=ServerSentEvent(msg,None)
            yield sse.encode()

    return Response(
        gen(node_name),
        mimetype="text/event-stream")


@application.route('/qiy_nodes/<node_name>/feed/<feed_id>/access/encrypted')
def qiy_nodes_feed_access_encrypted(node_name,feed_id):
    info("{}, {}".format(node_name,feed_id))

    exponent="AQAB"
    modulus="6sNhgtNVksGD4ZK1rW2iiGO11O/BzEIZazovnMK37y3RVvvjmv1z44uA505gyyUTziCntHV9tONmJ11bH4koqqJQFZPXuKAyuu9eR3W/pZ4EGBMMIVH2aqSOsPMTI5K9l2YOW8fAoEZQtYVWsCrygOyctBiamJZRJ+AKFZCIY5E="

    r=node_feed_access_encrypted(node_name,
                                 feed_id,
                                 exponent=exponent,
                                 modulus=modulus,
                                 target=target,
                                 )
    s=escape(request_to_str(r))

    return """
<h1>Test Node {0}</h1>
<h2>Feed {1} access encrypted</h2>

<pre>
{2}
</pre>

<p>
<a href="/qiy_nodes/{0}/feed/{1}/home">Up</a>
""".format(
    node_name,
    feed_id,
    s,
    )


@application.route('/qiy_nodes/<node_name>/feed/<feed_id>/access/unencrypted')
def qiy_nodes_feed_access_unencrypted(node_name,feed_id):
    info("{}, {}".format(node_name,feed_id))

    r=node_feed_access_unencrypted(node_name,feed_id,target=target)
    s=escape(request_to_str(r))

    return """
<h1>Test Node {0}</h1>
<h2>Feed {1} access unencrypted</h2>

<pre>
{2}
</pre>

<p>
<a href="/qiy_nodes/{0}/feed/{1}/home">Up</a>
""".format(
    node_name,
    feed_id,
    s,
    )


@application.route('/qiy_nodes/<node_name>/feed/<feed_id>/home')
def qiy_nodes_feed_home(node_name,feed_id):
    info("{}, {}".format(node_name,feed_id))

    body=""

    lis=""
    li='<li><a href="/qiy_nodes/{0}/feed/{1}/access/unencrypted">Access feed unencrypted</a>\n'.format(node_name,feed_id)
    lis="{}{}\n".format(lis,li)
    li='<li><a href="/qiy_nodes/{0}/feed/{1}/access/encrypted">Access feed encrypted</a>\n'.format(node_name,feed_id)
    lis="{}{}\n".format(lis,li)

    body="<ul>\n{}</ul>\n".format(lis)

    return """
<h1>Test Node {0}</h1>
<h2>Feed {1} home</h2>

{2}
<p>
<a href="/qiy_nodes/{0}">Up</a>
""".format(
    node_name,
    feed_id,
    body,
    )



@application.route('/qiy_nodes/<node_name>/feeds')
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


@application.route('/qiy_nodes/<node_name>/feeds/list')
def qiy_nodes_feeds_list(node_name):
    info("{}".format(node_name))

    feed_ids=node_feed_ids(node_name,target=target)

    lis=""
    for feed_id in feed_ids:
        li='<li><a href="/qiy_nodes/{0}/feed/{1}/home">{1}</a>\n'.format(
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


@application.route('/qiy_nodes/<node_name>/feeds/list/raw')
def qiy_nodes_feeds_list_raw(node_name):
    info("{}".format(node_name))

    ids=node_feed_ids(node_name)
    
    return dumps(ids,indent=2)

@application.route('/qiy_nodes/<node_name>/feeds/request')
def qiy_nodes_feeds_request(node_name):
    info("qiy_nodes_feeds_request({})".format(node_name))

    connections=qiy_nodes_connections_json(node_name)

    lis=""
    for connection in connections:
        mbox_url=connections[connection]['links']['mbox']
        b64mbox_url=quote_plus(b64encode(mbox_url.encode()).decode())
        url="/qiy_nodes/{}/feeds/request/mbox/{}".format(node_name,b64mbox_url)
        if 'pid' in connections[connection]:
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


@application.route('/qiy_nodes/<node_name>/feeds/request/mbox/<path:b64_mbox_url>')
def qiy_nodes_feeds_request_mbox(node_name,b64_mbox_url,
                                 operationTypeUrl="https://github.com/qiyfoundation/fiKks/tree/master/schema/v1"
                                 ):
    info("{}, {}".format(node_name,b64_mbox_url))

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
    s=request_to_str(r)


    page="""
<h1>Test Node {0} qiy_nodes_feeds_request_mbox</h1>

<pre>
{1}
</pre>
<p>
<a href="/qiy_nodes/{0}/feeds/request">Up</a>

""".format(node_name,s)
    return page


@application.route('/qiy_nodes/<node_name>/messages/since/<path:minutes>')
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

@application.route('/qiy_nodes/<node_name>/pid/<ub_pid>/<ub_connection>')
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

@application.route('/qiy_nodes/<node_name>/pids')
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


#@application.route('/qiy_nodes/<path:node_name>/pids/<ub_pid>/references/<ub_references_url>')
@application.route('/qiy_nodes/<node_name>/pids/references/<ub_references_url>')
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


#@application.route('/qiy_nodes/<path:node_name>/pids/<ub_pid>/references/<ub_references_url>')
@application.route('/qiy_nodes/<node_name>/pids/refs_feeds/<ub_references_url>/<feed_id>')
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


@application.route('/qiy_nodes/<node_name>/proxy/<path:path>',methods=['get'])
def qiy_nodes_proxy(node_name,path):
    info("{}".format(node_name,path))

    # Return webpage for text/html requests.
    print("request.headers: '{}'".format(request.headers))
    accept_header=None
    if 'Accept' in request.headers:
        accept_header=request.headers['Accept']
    elif 'accept' in request.headers:
        accept_header=request.headers['accept']
    print("accept_header: '{}'".format(accept_header))

    received_request=request_to_str(request,r_is_request=True)
    info(received_request)
    received_request=escape(received_request)

    response=None
    if 'text/html' in accept_header:
        # Return received request

        html="""
    <h1>Test Node {0} Proxy</h1>

    <pre>
    {1}
    </pre>

    <a href="/qiy_nodes/{0}">Up</a>

    """.format(node_name,
               received_request,
               )

        response=Response(html)
        response.headers['Access-Control-Allow-Origin'] = '*'
        
    else:
        # Forward to Qiy Trust Network
        stream=None

        node_endpoint_url=node_endpoint(target=target)
        url=node_endpoint_url
        if request.args:
            url=url+"?"
            for parameter in request.args:
                url="{0}{1}={2}&".format(url,parameter,request.args[parameter])
            url=url[0:len(url)-1]
        print("url: {}''".format(url))
        headers={}
        ignore_headers=['Postman-Token',
                        'Host',
                        'X-Mock-Response-Code',
                        'Cache-Control'
                        #'', HIER WAS IK GEBLEVEN...
                        ]
        headers['Accept']='application/json'
#        for name, value in request.headers:
#            headers[name]=value
        data=request.data
        
        # Authenticate authenticated requests
        authorization_header=None
        if 'Authorization' in headers:
            authorization_header=headers['Authorization']
        elif 'authorization' in headers:
            authorization_header=headers['authorization']

        if not authorization_header is None:
            info("Authenticating request...")
            # For now always include transportpassword
            headers['Authorization']=node_auth_header(data=data,node_name=node_name,target=target)
            headers['password']=node_transport_password(node_name=node_name,target=target)
        # Return response

        methods={
            "delete": requests.delete,
            "get": requests.get,
            "options": requests.options,
            "patch": requests.patch,
            "post": requests.post,
            "put": requests.put,
            }
        method=request.method
        method=method.lower()
        r=methods[method](url,headers=headers,data=data,stream=stream)
        info("Response from qtn: '{}'".format(request_to_str(r)))

        mimetype=None
        if 'Content-Type' in r.headers:
            mimetype=r.headers['Content-Type']
        headers={'Access-Control-Allow-Origin':'*'}
        response=Response(r.text, headers=headers, status=r.status_code, mimetype=mimetype)
        #info("Response to qtt client: '{}'".format(response_to_str(response)))

    return response


@application.route('/qiy_nodes/<node_name>/redirect_to_eformulieren/<path:u_url>')
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


@application.route('/qiy_nodes/<node_name>/service_catalogue')
def qiy_nodes_service_catalogue(node_name):
    info("{}".format(node_name))

    service_catalogue=node_service_catalogue_get(node_name,target=target).json()

    page="""
<h1>Test Node {0}</h1>
<h2>Service catalogue</h2>

<pre>
{1}
</pre>
<a href="/qiy_nodes/{0}">Up</a>

""".format(node_name,dumps(service_catalogue,indent=2))
    
    return page

@application.route('/service_types/<ub_service_type>')
def qtt_service_types(ub_service_type):
    info("{}".format(ub_service_type))

    service_type=ub_decode(ub_service_type)

    all_users=node_ids(target=target)
    data_providers=node_data_providers(service_type_url=service_type,
                                       target=target)
    lis=""
    for i in data_providers:
        li='<li><a href="/service_types/{0}/data_providers/{1}/home">{1}</a>'.format(ub_service_type,i)
        lis="{}{}\n".format(lis,li)
    data_provider_lis=lis
    
    orchestrators=node_orchestrators(
        service_type_url=service_type,
        target=target)
       
    lis=""
    for i in orchestrators:
        li='<li><a href="/service_types/{0}/orchestrators/{1}">{1}</a>'.format(ub_service_type,i)
        lis="{}{}\n".format(lis,li)
    orchestrator_lis=lis
    
    relying_parties=[]
    lis=""
    for i in orchestrators:
        for connected_to_orchestrator in node_connected_node_names(i,target=target):
            if not connected_to_orchestrator in data_providers and not connected_to_orchestrator in relying_parties:
                relying_parties.append(connected_to_orchestrator)
    for i in relying_parties:
        li='<li><a href="/service_types/{0}/relying_parties/{1}/home">{1}</a>'.format(ub_service_type,i)
        lis="{}{}\n".format(lis,li)
    relying_party_lis=lis
    
    other_users=[]
    players=relying_parties + orchestrators + data_providers
    lis=""
    for i in all_users:
        if i not in players:
            other_users.append(i)
    for i in other_users:
        li='<li><a href="/qiy_nodes/{0}">{0}</a>'.format(i)
        lis="{}{}\n".format(lis,li)
    other_user_lis=lis
    
    
    return """
<h1>Service type {0}</h1>

<ul>
<li><a href="/service_types/{1}/feeds/list">Feeds</a>
</ul>

<h2>Data providers</h2>
<ul>
{2}
</ul>

<h2>Orchestrators</h2>
<ul>
{3}
</ul>

<h2>Relying parties</h2>
<ul>
{4}
</ul>

<h2>Other users</h2>
<ul>
{5}
</ul>

<a href="/">Up</a>
""".format(service_type,
           ub_service_type,
           data_provider_lis,
           orchestrator_lis,
           relying_party_lis,
           other_user_lis,
           )


@application.route('/service_types/<ub_service_type>/data_providers/<data_provider>/home')
def qtt_service_types_data_providers(ub_service_type,data_provider):
    info("{}".format(ub_service_type,data_provider))

    # Uggly...
    page_url="/service_types/{}/data_providers/{}/home".format(ub_service_type,data_provider)

    service_type=ub_decode(ub_service_type)

    service_catalogue=node_service_catalogue_get(
        node_name=data_provider,
        target=target,
        ).json()

    service_endpoint_description=service_catalogue[service_type]

    # Check for user updates
    update=False
    for i in service_endpoint_description:
        name="service_endpoint_{}".format(i)
        
        
        if name in request.args:
            print("{} in request.args".format(name))
            if not request.args.get(name) == service_endpoint_description[i]:
                update=True
                service_endpoint_description[i]=request.args.get(name)

    # Check for default value
    if service_endpoint_description['uri']=="":
        netloc=urlparse(request.url).netloc
        service_endpoint_description['uri']="https://{}/data_provider/{}/service_type/{}/service_endpoint/feeds/callback".format(
            netloc,
            data_provider,
            ub_service_type,
            )


    # Update service description
    report=""
    if update:
        service_catalogue[service_type]=service_endpoint_description
        r=node_service_catalogue_set(
            node_name=data_provider,
            service_catalogue=service_catalogue,
            target=target,
            )
        if not r.status_code==200:
            report="""
<h2>NB: Update failed</h2>
<pre>
{}
</pre>
""".format(
    escape(request_to_str(r)))
            

    # Create service description form
    service_description_form=""
    rows=""
    for i in service_endpoint_description:
        name="service_endpoint_{}".format(i)
        
        row="""
<tr>
    <td>
        service endpoint {}
    </td>
    <td>
        <input type="text" name="{}" value="{}">
    </td>
</tr>
""".format(i,name,service_endpoint_description[i])
        rows="{}\n{}".format(rows,row)

    service_description_form="""
<form action="{}" method="get">
    <table>
        {}        
    </table>
    <input type="submit" value="Submit">
</form>
""".format(
    page_url,
    rows
    )

    return """
<h1>Service type {0}</h1>

<h2>Data provider {1}</h2>

<h2>Service description</h2>

{2}

<p>
<a href="/service_types/{3}">Up</a>

""".format(service_type,
           data_provider,
           service_description_form,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/feeds/list')
def qtt_service_types_feeds_list(ub_service_type):
    info("{}".format(ub_service_type))

    service_type=ub_decode(ub_service_type)

    feed_ids=node_feed_ids_list(
        service_type_url=service_type,
        target=target,
        )

    lis=""
    for relying_party in feed_ids:
        li='<li><a href="/service_types/{0}/relying_parties/{1}/home">{1}</a>\n<ul>\n'.format(
                ub_service_type,
                relying_party,
            )
        feed_lis=""
        for feed_id in feed_ids[relying_party]:
            has_feeds=True
            feed_li='<li><a href="/service_types/{0}/relying_parties/{1}/feeds/{2}/home">{3}</a>'.format(
                ub_service_type,
                relying_party,
                ub_encode(feed_id),
                feed_id
                )
            feed_lis="{}{}\n".format(feed_lis,feed_li)
        li="{}\n{}\n</ul>".format(li,feed_lis)
        if feed_lis:
            lis="{}{}\n".format(lis,li)

    feed_ids_lis=lis
    return """
<h1>Service type {0}</h1>

<h2>Feeds</h2>
<ul>
{1}
</ul>
<a href="/service_types/{2}">Up</a>

""".format(service_type,
           feed_ids_lis,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/orchestrators/<orchestrator>')
def qtt_service_types_orchestrators(ub_service_type,orchestrator):
    info("{}".format(ub_service_type,orchestrator))

    service_type=ub_decode(ub_service_type)

    return """
<h1>Service type {0}</h1>

<h2>Orchestrator {1}</h2>

tbd

<p>
<a href="/service_types/{2}">Up</a>

""".format(service_type,
           orchestrator,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/relying_parties/<relying_party>/home')
def qtt_service_types_relying_parties(ub_service_type,relying_party):
    info("{}".format(ub_service_type,relying_party))

    service_type=ub_decode(ub_service_type)

    connected_nodes =node_connected_node_names(node_name=relying_party,target=target)
    orchestrators   =node_orchestrators(service_type_url=service_type,target=target)

    connected_orchestrators=[]
    not_connected_orchestrators=[]
    for i in orchestrators:
        if i in connected_nodes:
            connected_orchestrators.append(i)
        else:
            not_connected_orchestrators.append(i)

    lis=""
    for i in not_connected_orchestrators:
        li='<li><a href="/service_types/{0}/relying_parties/{1}/orchestrators/{2}/not_connected">{2}</a>'.format(ub_service_type,relying_party,i)
        lis="{}{}\n".format(lis,li)
    not_connected_orchestrator_lis=lis
    
    lis=""
    for i in connected_orchestrators:
        li='<li><a href="/service_types/{0}/relying_parties/{1}/orchestrators/{2}/connected">{2}</a>'.format(ub_service_type,relying_party,i)
        lis="{}{}\n".format(lis,li)
    connected_orchestrator_lis=lis

    return """
<h1>Service type {0}</h1>

<h2>Relying party {1}</h2>

<h3>Not connected orchestrators</h3>
<ul>
{2}
</ul>

<h3>Connected orchestrators</h3>
<ul>
{3}
</ul>


<p>
<a href="/service_types/{4}">Up</a>

""".format(
    service_type,
    relying_party,
    not_connected_orchestrator_lis,
    connected_orchestrator_lis,
    ub_service_type,
    )


@application.route('/service_types/<ub_service_type>/relying_parties/<relying_party>/feeds/<ub_feed_id>/home')
def qtt_service_types_relying_parties_feeds_home(ub_service_type,relying_party,ub_feed_id):
    info("{}".format(ub_service_type,relying_party,ub_feed_id))

    service_type=ub_decode(ub_service_type)
    feed_id=ub_decode(ub_feed_id)


    return """
<h1>Service type {0}</h1>

<h2>Relying party {1}</h2>
<h2>Feed id {2}</h2>

tbd

<p>
<a href="/service_types/{3}">Service type home</a>

""".format(service_type,
           relying_party,
           feed_id,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/relying_parties/<relying_party>/orchestrators/<orchestrator>/connected')
def qtt_service_types_relying_parties_orchestrators_connected(ub_service_type,relying_party,orchestrator):
    info("{}".format(ub_service_type,relying_party,orchestrator))

    service_type=ub_decode(ub_service_type)


    return """
<h1>Service type {0}</h1>

<h2>Relying party {1}</h2>

<h3>Connected orchestrator '{2}'</h3>

<a href="/service_types/{3}/relying_parties/{1}/orchestrators/{2}/feed_request">Feed request</a>

<p>
<a href="/service_types/{3}/relying_parties/{1}/home">Up</a>

""".format(service_type,
           relying_party,
           orchestrator,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/relying_parties/<relying_party>/orchestrators/<orchestrator>/feed_request')
def qtt_service_types_relying_parties_orchestrators_feed_request(ub_service_type,relying_party,orchestrator):
    info("{}".format(ub_service_type,relying_party,orchestrator))

    service_type=ub_decode(ub_service_type)

    r=node_feed_request(
        relying_party=relying_party,
        orchestrator=orchestrator,
        service_type_url=service_type,
        target=target,
        )

    report="<pre>\n{}\n</pre>".format(
        escape(request_to_str(r)),
        )

    return """
<h1>Service type {0}</h1>

<h2>Relying party {1}</h2>

<h3>Connected orchestrator '{2}' - Feed request</h3>

{3}

<p>
<a href="/service_types/{4}/relying_parties/{1}/home">Up</a>

""".format(service_type,
           relying_party,
           orchestrator,
           report,
           ub_service_type,
           )


@application.route('/service_types/<ub_service_type>/relying_parties/<relying_party>/orchestrators/<orchestrator>/not_connected')
def qtt_service_types_relying_parties_orchestrators_not_connected(ub_service_type,relying_party,orchestrator):
    info("{}".format(ub_service_type,relying_party,orchestrator))

    service_type=ub_decode(ub_service_type)


    return """
<h1>Service type {0}</h1>

<h2>Relying party {1}</h2>

<h3>Not connected orchestrator {2}</h3>
tbd

<p>
<a href="/service_types/{3}/relying_parties/{1}/home">Up</a>

""".format(service_type,
           relying_party,
           orchestrator,
           ub_service_type,
           )


@application.route('/service_types_create',methods=['get'])
def qtt_service_types_create():
    info("start")

    data_provider_name = request.args.get('data_provider_name')
    service_endpoint_method = request.args.get('service_endpoint_method')
    service_endpoint_type = request.args.get('service_endpoint_type')
    service_endpoint_url = request.args.get('service_endpoint_url')
    service_type_url = request.args.get('service_type_url')

    # Check for default value
    if service_endpoint_url=="":
        netloc=urlparse(request.url).netloc
        service_endpoint_url="https://{}/data_provider/{}/service_type/{}/service_endpoint/feeds/callback".format(
            netloc,
            data_provider_name,
            ub_encode(service_type_url),
            )

    report=""
    status_code=200

    if not data_provider_name in node_ids(target=target):
        report="creating node..."
        r=node_create(
            node_id=str(uuid4()),
            node_name=data_provider_name,
            target=target,
            )
        if r.status_code==201:
            report="node created :-)"
            # to be fixed
            # Check and move files to QIY_CREDENTIALS
            filenames=[]
            filenames.append("{}_{}_node_repository.json".format(data_provider_name,target[:2]))
            filenames.append("{}_{}.pem".format(data_provider_name,target[:2]))
            
            creds_path=expanduser(getenv("QIY_CREDENTIALS"))
            for filename in filenames:
                p=Path(join(creds_path,filename))
                if not p.exists():
                    info("moving {} from ./data to {}".format(filename,creds_path))
                    
                    move(join("./data/",filename),creds_path)
                else:
                    info("filename {} ok".format(filename))
                    pass
        else:
            status_code=r.status_code
            report="node not created :-(, {}".format(request_to_str(r))
            
    else:
        report="Using existing node '{}'".format(data_provider_name)

    if status_code < 300:
        service_catalogue=node_service_catalogue_get(
            node_name=data_provider_name,
            target=target,
            ).json()
        if not service_type_url in service_catalogue:
            service_endpoint_description={
                "type": service_endpoint_type,
                "uri": service_endpoint_url,
                "method": service_endpoint_method,
            }
            service_catalogue[service_type_url]=service_endpoint_description
            r=node_service_catalogue_set(
                node_name=data_provider_name,
                service_catalogue=service_catalogue,
                target=target,
                )
            report="""{}
{}
""".format(report,
           escape(request_to_str(r)))
            
        else:
            report="""{}
Service type not added; already existing.
""".format(report)
    
    return """
<h1>Service type</h1>

data provider name: {}<br>
service type: {}<br>
<p>

report:<br>
<pre>{}</pre>

<p><a href="/">Up</a>
""".format(
    data_provider_name,
    service_type_url,
    report,
    )


@application.route('/connection_url_event_source/<path:webhook_url>')
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



