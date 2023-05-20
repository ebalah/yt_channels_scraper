import time


def datem():
    return time.strftime("[%b %d, %Y %H:%M:%S] ~ $")


def file_name_timer():
    return time.strftime("%Y%m%d_%H%M%S")
