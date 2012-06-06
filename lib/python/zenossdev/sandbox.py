import os
from os.path import isdir, abspath, join, dirname
import re
from subprocess import Popen, PIPE
import ConfigParser
from cStringIO import StringIO
import xml.etree.cElementTree as ET

CONFIG_FILE = os.path.expanduser('~/.zenossdev')
_CONFIG_SECTION = 'zenossdev'

# Only available in Python 2.7+ - write equivalent for backwards compat
def _check_output(cmd):
    proc = Popen(cmd, stdout=PIPE)
    stdout, stderr = proc.communicate()
    rc = proc.returncode
    if rc != 0:
        raise Exception('Command failed: %s, rc=%s' % (' '.join(cmd), rc))
    return stdout

class ZenossDevConfig(object):
    def __init__(self, config):
        self._config = config

    def __getattr__(self, attr):
        try:
            return self._config.get(_CONFIG_SECTION, attr)
        except ConfigParser.NoOptionError:
            pass

def _svn_info_xml_parser(basedir):
    xml_output = _check_output(['svn','info','--xml',basedir])
    sio = StringIO(xml_output)
    et = ET.parse(sio)
    sio.close()
    return et

def load_config(filename=CONFIG_FILE):
    parser = ConfigParser.SafeConfigParser()
    if os.path.exists(filename):
        f = open(filename)
        try:
            class SectionWrapper(object):
                def __init__(self):
                    self._wroteHeader = False

                def readline(self):
                    if not self._wroteHeader:
                        self._wroteHeader = True
                        return '[%s]' % _CONFIG_SECTION
                    return f.readline()
            parser.readfp(SectionWrapper())
        finally:
            f.close()
    if not parser.has_section(_CONFIG_SECTION):
        parser.add_section(_CONFIG_SECTION)
    return ZenossDevConfig(parser)

def find_root_checkout(basedir=os.getcwd()):
    """
    Attempts to find the top-level checkout starting at the given base 
    directory. Returns the top-level path for the Zenoss Core or Zenoss
    Enterprise checkout, or raises an exception if it isn't found.
    """
    et = _svn_info_xml_parser(basedir)
    if et:
        for element in et.iter('wcroot-abspath'):
            return abspath(element.text)

    if not isdir(join(basedir, '.svn')):
        raise Exception('Not in SVN repository')
    prevdir = None
    curdir = abspath(basedir)
    while curdir != prevdir:
        if not isdir(join(curdir, '.svn')):
            break
        if is_toplevel(curdir):
            return curdir
        prevdir = curdir
        curdir = abspath(dirname(curdir))
    raise Exception('Unable to find root directory in: %s' % basedir)

def find_base_url(svndir):
    """
    Returns the root of the repository found in the given directory.
    """
    et = _svn_info_xml_parser(svndir)
    if et:
        for element in et.iter('repository'):
            for root_element in element.iterfind('root'):
                return root_element.text
    raise Exception('Unable to determine base url')

def is_toplevel(root_dir):
    """
    Returns true if the given directory is a top level core or enterprise
    checkout, otherwise false.
    """
    return is_core(root_dir) or is_enterprise(root_dir)

def is_core(root_dir):
    """
    Returns true if the given directory is a top-level core checkout.
    """
    for d in ('Products', 'inst'):
        if not isdir(join(root_dir, d)):
            return False
    return True

def is_enterprise(root_dir):
    """
    Returns True if the given directory is a top-level enterprise checkout.
    """
    return isdir(join(root_dir, 'ZenPacks.zenoss.EnterpriseSkin'))

_OFFICIAL_BRANCH_REGEX = re.compile(r'^zenoss-(\d+)(?:\.[\da-z]+?){1,}$')

def is_official_branch(branch_name):
    """
    Return True if the branch name matches an official branch naming scheme.
    (zenoss-*).
    """
    return _OFFICIAL_BRANCH_REGEX.match(branch_name)

_OFFICIAL_TAG_REGEX = re.compile(r'^zenoss-(\d+)(?:\.\d+?){1,}$')

def is_official_tag(branch_name):
    """
    Return True if the branch name matches an official tag naming scheme.
    """
    return _OFFICIAL_TAG_REGEX.match(branch_name)

def find_branch_url(root_dir, branch_name, username=None, guess_branch=True,
                    append_zenpacks=True):
    """
    Given the root of the repository checkout, the branch name, and a username
    this returns the URL of the appropriate branch.
    """
    root_dir = find_root_checkout(root_dir)
    base_url = find_base_url(root_dir)
    official = False
    tag = False
    if guess_branch:
        official = is_official_branch(branch_name)
        tag = is_official_tag(branch_name)
    url = None
    if is_core(root_dir):
        if tag:
            url = '%s/tags/core/%s' % (base_url, branch_name)
        elif official:
            url = '%s/branches/core/%s' % (base_url, branch_name)
        elif branch_name == 'trunk':
            url = '%s/%s/core' % (base_url, branch_name)
        elif username:
            url = '%s/sandboxen/core/%s/%s' % (base_url, username, branch_name)
    elif is_enterprise(root_dir):
        suffix = ''
        if append_zenpacks:
            suffix = '/zenpacks'
        if tag:
            url = '%s/tags/%s' % (base_url, branch_name)
        elif official:
            url = '%s/branches/%s%s' % (base_url, branch_name, suffix)
        elif branch_name == 'trunk':
            url = '%s/%s/enterprise%s' % (base_url, branch_name, suffix)
        elif username:
            url = '%s/sandboxen/%s/%s%s' % (base_url, username, branch_name,
                                            suffix)

    if not url:
        raise Exception('Unable to determine branch path: '
                        'root_dir=%s, branch_name=%s, username=%s' %
                        (root_dir, branch_name, username))
    return url

