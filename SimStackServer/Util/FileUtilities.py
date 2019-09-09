import os
from lxml import etree


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