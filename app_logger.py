import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger instance.
    Logs are written to 'app.log' and printed to stdout.
    """
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times if get_logger is called repeatedly
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # Create formatters
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File Handler
        file_handler = logging.FileHandler("app.log", encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        
        # Stream Handler (Console)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.INFO)
        
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        
    return logger
