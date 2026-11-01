import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        try:
            fields = json.loads(message)
            if not isinstance(fields, dict):
                fields = {"message": message}
        except ValueError:
            fields = {"message": message}
        return json.dumps({"level": record.levelname, "logger": record.name, **fields})


def configure_logging(level: str) -> None:
    logger = logging.getLogger("citysense")
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.propagate = False
