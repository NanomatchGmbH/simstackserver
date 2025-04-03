from lxml import etree


def is_regular_element(element):
    if isinstance(element, etree.CommentBase) or isinstance(element, etree._Comment):
        return False
    return True
