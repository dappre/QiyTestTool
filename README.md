# QiyTestTool

QiyTestTool (QTT) is a python web server which allows you to access one or more Qiy Nodes.

# Installation

## Preconditions

This python module requires:
1. python 3.6
2. QiyNodeLib, see [installation instructions](https://github.com/digital-me/QiyNodeLib/blob/master/README.md)

## Unix

1. Clone this repository, say in your home directory.


# Qiy Node Credentials

By default, QTT checks the directory ~/QiyTestTool/data for Qiy Node Credentials, but this can be changed using the QIY_CREDENTIALS environment variable in ~/QiyTestTool/.env

## Format

The Qiy Node Credential of a consists of two files:

```
1. <node name>_<target environment id>_node_repository.json, for example: 'mgd_dev2_de_node_repository.json'.
2. <node name>_<target environment id>.pem, for example: 'mgd_dev2_de.json'
```

Please contact freek.driesenaar@digital-me.nl for more information.

# Starting the server

Enter the following commands to start the server:

```
cd ~/QiyTestTool
export FLASK_APP=QiyTestTool/site/flask_app.py
python3 -m flask run
```

Now start a webbrowser and open the webpage https://127.0.0.1/5000

# Server-Sent Events: fix for reusing sessions

When using the standard urllib package, QTT will not reuse a session with Server-Sent Events.
This can be (temporarily) repaired as follows:
1. Applying this change: https://github.com/psf/requests/issues/4248#issuecomment-429188281
2. Set the environment variable 'QTT_URLLIB_FIXED' to 'TRUE'
