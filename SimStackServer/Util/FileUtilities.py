import os
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
    if not mypath.endswith('/') and not mypath == "":
        togenerate.append(mypath)
    first = "A"
    counter = 0
    while first != "" and first != "/":
        counter+=1
        first,second = split(mypath)
        if not first in togenerate:
            if first != "/" and first != "":
                togenerate.append(first)
        mypath = first
        if counter == 5000:
            raise PathSplitError("Directory %s cannot be split into subdirectories"%mypath)

    togenerate.reverse()
    return togenerate



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
    with sserver_open(path,'w') as out:
        out.write(etree.tostring(xml_element))

def file_to_xml(path):
    """

    :param path (str): String to file
    :return (lxml.etree.Element): Parsed XML object
    """
    with sserver_open(path,'r') as infile:
        xml = etree.parse(infile)
    return xml.getroot()