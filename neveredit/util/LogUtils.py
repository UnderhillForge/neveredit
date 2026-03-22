"""Utilities for immediate logging with flushing to prevent log loss on crash."""
import sys
import logging

def flushed_log(logger, level, message):
    """Log a message and immediately flush all handlers."""
    if level == 'debug':
        logger.debug(message)
    elif level == 'info':
        logger.info(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)
    
    # Flush all handlers
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass
    sys.stdout.flush()
    sys.stderr.flush()
