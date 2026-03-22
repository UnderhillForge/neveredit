import logging
import os
import sys

# Root logger for neveredit
logger = logging.getLogger('neveredit')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(levelname)s %(module)s: %(message)s'))
logger.addHandler(stream_handler)
logger.setLevel(logging.DEBUG)

# Add file handler with immediate flushing for crash diagnosis
try:
    log_file = os.path.join(os.getcwd(), 'app_debug.log')
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(levelname)s %(module)s: %(message)s'))
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
except Exception:
    pass

logger = logging.getLogger('neveredit.file')
logger.setLevel(logging.DEBUG)

logger = logging.getLogger('neveredit.ui')
logger.setLevel(logging.DEBUG)

logger = logging.getLogger('neveredit.game')
logger.setLevel(logging.DEBUG)
