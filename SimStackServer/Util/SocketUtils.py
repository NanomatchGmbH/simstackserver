import socket
import random
import string


def get_open_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port


def random_pass(number_of_letters=48):
    """
    Generates an alphanumerical password.
    :param number_of_letters (int): Number of letters of the password
    :return (str): Password
    """
    password = "".join(
        random.choices(
            string.ascii_uppercase + string.ascii_lowercase + string.digits,
            k=number_of_letters,
        )
    )
    return password
    # random_bytes=os.urandom(48)
    # import base64
    # return base64.b64encode(random_bytes).decode("utf8")[:-2]
