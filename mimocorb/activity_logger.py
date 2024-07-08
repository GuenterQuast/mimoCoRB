import logging  # TODO: Set log level


# set logging format for all loggers globally
logging.basicConfig(
    format="%(asctime)s %(name)s:%(levelname)-8s %(message)s",  # time name:level  message
    datefmt="%Y-%m-%d %H:%M:%S",  # YYYY-MM-DD HH:MM:SS
)


class Logging_manager:
    """
    This class is a callable class that generates loggers with the same level set for all loggers created by this object.
    It allows for changing the logging level for all loggers after their creation.

    Setting the logging level globally is a bad idea because Tk starts flooding stdout with messages.
    Therefore the run_mimoDaq constructor gets a debug flag to set the logging level in an instance of this class
    Afterwards all sub-loggers are created with the same level.
    """

    def __init__(self) -> None:
        self.level = logging.WARNING  # default logging level
        self.logger_pool = []

    def set_level(self, level: int) -> None:
        """
        Set the logging level for all loggers created by this object

        :param level: logging level
        """
        self.level = level
        for logger in self.logger_pool:  # update the level for all loggers
            logger.setLevel(self.level)

    def __call__(self, name: str) -> logging.Logger:
        """
        Generate a logger with the level set for this module

        :param name: name of the logger
        :return: logger object
        """
        logger = logging.getLogger(name)
        logger.setLevel(self.level)
        self.logger_pool.append(logger)  # keep a reference of all created loggers
        return logger


# instantiate global logger_config object to generate configured loggers
Gen_logger = Logging_manager()
