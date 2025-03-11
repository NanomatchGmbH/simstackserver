import io
import logging
import os
import shutil
import zipfile
from functools import wraps
from os.path import join
from pathlib import Path

from lxml import etree


class PathSplitError(Exception):
    pass


def split_directory_in_subdirectories(mypath: str):
    """
    Splits directories into a list of concatenated subdirectories. Has a failsafe at 5000 subdirectories.

    :param mypath (str): Path to be split into subdirectories. (/home/me/test)
    :return (list of str): List of directories, which have to be traversed in order ([/home,/home/me,/home/me/test])

    """
    togenerate = []
    from os.path import split

    if not mypath.endswith("/") and not mypath == "":
        togenerate.append(mypath)
    first = "A"
    counter = 0
    while first != "" and first != "/":
        counter += 1
        first, second = split(mypath)
        if first not in togenerate:
            if first != "/" and first != "":
                togenerate.append(first)
        mypath = first
        if counter == 5000:
            raise PathSplitError(
                "Directory %s cannot be split into subdirectories" % mypath
            )

    togenerate.reverse()
    return togenerate


def abs_resolve_file(directory: str):
    if not directory.startswith("/"):
        home = str(Path.home())
        return join(home, directory)
    return directory


def mkdir_p(path):
    import errno

    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise exc


sserver_open = open


def xml_to_file(xml_element, path):
    """

    :param xml_element (lxml.etree.Element): Element to dump to path
    :param path (str): Path to a file in an existing folder
    :return: Nothing
    """
    with sserver_open(path, "wb") as out:
        out.write(etree.tostring(xml_element))


def file_to_xml(path):
    """

    :param path (str): String to file
    :return (lxml.etree.Element): Parsed XML object
    """
    with sserver_open(path, "r") as infile:
        xml = etree.parse(infile)
    return xml.getroot()


def trace_to_logger(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger = logging.getLogger("TraceLogger")
            logger.exception("Exception occured:")
            raise e

    return wrapper


class StringLoggingHandler(logging.StreamHandler):
    def __init__(self):
        self._stringstream = io.StringIO()
        super().__init__(stream=self._stringstream)

    def getvalue(self):
        return self._stringstream.getvalue()


def copytree(src, dst, symlinks=False, ignore=None):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def copytree_pathlib(srcpath: Path, destpath: Path, symlinks=False, ignore=None):
    if isinstance(srcpath, zipfile.Path):
        zipfilepath = str(srcpath)[:-1]
        zz = zipfile.ZipFile(zipfilepath)
        zz.extractall(destpath)
    elif srcpath.is_dir():
        copytree(str(srcpath), str(destpath), symlinks=symlinks, ignore=ignore)


def filewalker(basedir):
    for root, dirs, files in os.walk(basedir):
        if len(files) > 0:
            for mf in files:
                fullpath = os.path.join(root, mf)
                if os.path.isfile(fullpath):
                    yield fullpath
