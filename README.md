Argus-CI
========

[![](https://travis-ci.org/cloudbase/cloudbase-init-ci.svg?branch=master)](https://travis-ci.org/cloudbase/cloudbase-init-ci/)
[![](https://readthedocs.org/projects/argus-ci/badge/?style=flat)](http://argus-ci.readthedocs.org/en/latest/?badge=latest)


**argus** is a framework for writing complex integration tests,
for code that needs to run under various different operating systems.

It is used for testing Cloudbase-Init.

How to setup an Argus environment
--------------------------------


> **Note:**
>
> - The following setup is specific for Debian based Linux operating system
> - Openstack needs to be present on the system. In case it's missing, you can find more details about how to deploy it [here][0]: 


### Install the required libraries

```
~ $ sudo apt-get install git vim ntp openssh-server python-setuptools python-dev build-essential
~ $ sudo pip install --upgrade
```

### Install Argus-CI and Tempest

1. Clone the repositories for Argus-CI and tempest as shown below

```
~ $ git clone https://github.com/cloudbase/cloudbase-init-ci
~ $ git clone https://github.com/openstack/tempest
```

2. Create a virtualenv for the CI environment and install the dependencies

```
~ $ virtualenv .venv/argus-ci --python=/usr/bin/python2.7
~ $ source .venv/argus-ci/bin/activate
(argus-ci) ~ $ pip install pip --upgrade
(argus-ci) ~ $ cd cloudbase-init-ci/
(argus-ci) ~ $ pip install -r requirements.txt
(argus-ci) ~ $ pip install -r test-requirements.txt
(argus-ci) ~ $ python setup.py install
(argus-ci) ~ $ cd ../tempest
(argus-ci) ~ $ git checkout 11.0.0
(argus-ci) ~ $ pip install -r requirements.txt
(argus-ci) ~ $ pip install -r test-requirements.txt
(argus-ci) ~ $ python setup.py install
```

3. Create the configuration files for the CI and Tempest

```
~ $ mkdir /etc/tempest/
~ $ cd /etc/tempest
~ $ wget https://raw.githubusercontent.com/alexcoman/scripts/master/argus-ci/mitaka/tempest.conf
~ $ sudo ln -s ~/cloudbase-init-ci/etc /etc/argus
```
> **Note:**
> - Modify the missing fields in the tempest and argus files according to the ID's retrieved from the Openstack environment.

### Optional additional steps for integrating Arestor with Argus

1. Setting up Arestor

```
(argus-ci) ~ $ git clone https://github.com/stefan-caraiman/arestor
(argus-ci) ~ $ cd arestor/
(argus-ci) ~ $ git checkout dev
(argus-ci) ~ $ pip install -r requirements.txt
(argus-ci) ~ $ pip install -r test-requirements.txt
(argus-ci) ~ $ python setup.py install
(argus-ci) ~ $ arestor user add --name "argus" --description "User used by the Argus-CI"
(argus-ci) ~ $ arestor server start &
```

2. Create a new user for Argus client

```
(argus-ci) ~ $ arestor user list | grep "API Key" # Copy the API key for the user
(argus-ci) ~ $ arestor user show-sercret --api-key
```

3. Add the Argus branch with Arestor integration to the CI

```
(argus-ci) ~ $ cd ~/cloudbase-init-ci
(argus-ci) ~ $ git remote add arestor-integration https://github.com/stefan-caraiman/cloudbase-init-ci
(argus-ci) ~ $ git fetch arestor-integration
(argus-ci) ~ $ git branch 
dev
(argus-ci) ~ $ git rebase arestor-integration/poc dev
```

4. Modify argus.conf

`/etc/argus/argus.conf`:
```
[arestor]
api_key = <api_key> # from step 2
secret =  <secret> # as shown in step 2
base_url = <url> # by default localhost
```

[0]: https://github.com/alexcoman/scripts
