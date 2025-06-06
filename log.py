import inspect
import logging
import logging.config
import re
import time

# 1. Define the regex patterns of sensitive data
regex_patterns = [
    # password fields in JSON strings
    r'([Pp]assword\s*":\s*")([^"]*)(")',  # Captures key part (1), value (2), closing quote (3)
]

# Define a list of keys that values are sensitive data
sensitive_keys = (
    "headers",
    "credentials",
    "Authorization",
    "token",
    "password",
)

class SensitiveDataFilter(logging.Filter):
    patterns = regex_patterns
    sensitive_keys = sensitive_keys

    def filter(self, record):
        try:
            record.args = self.mask_sensitive_args(record.args)
            record.msg = self.mask_sensitive_msg(record.msg)
            return True
        except Exception:
            return True

    def mask_sensitive_args(self, args):
        if isinstance(args, dict):
          new_args = args.copy()
          for key in args:
            if key in sensitive_keys:
              new_args[key] = "******"
            else:
              # mask sensitive data in dict values
              new_args[key] = self.mask_sensitive_msg(args[key])
          return new_args
        # when there are multi arg in record.args
        return (self.mask_sensitive_msg(arg) for arg in args)

    def mask_sensitive_msg(self, message):
        # mask sensitive data in multi record.args
        if isinstance(message, dict):
            return self.mask_sensitive_args(message)
        if isinstance(message, str):
            for pattern in self.patterns:
                message = re.sub(pattern, "******", message)
            for key in self.sensitive_keys:
                pattern_str = rf"'{key}': '[^']+'"
                replace = f"'{key}': '******'"
                message = re.sub(pattern_str, replace, message)
        return message


def init_logging(
  log_level: str = "DEBUG", formatter: str = "console"
) -> logging.Logger:
  LOG_CONFIG = {
    "version": 1,
    "handlers": {
      "stdout": {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
        "formatter": formatter,
      }
    },
    "formatters": {
      "json": {
        "format": (
          '{"msg":"%(message)s","level":"%(levelname)s",'
          '"file":"%(filename)s","line":%(lineno)d,'
          '"module":"%(module)s","func":"%(funcName)s"}'
        ),
        "datefmt": "%Y-%m-%dT%H:%M:%SZ",
      },
      "console": {
        "format": "%(asctime)s %(name)s %(levelname)s : %(message)s",
        "datefmt": "%Y-%m-%dT%H:%M:%SZ",
      },
    },
    "loggers": {
      "gabb": {"handlers": ["stdout"], "level": log_level},
    },
    "root": {"handlers": ["stdout"], "level": log_level},
  }
  logging.Formatter.converter = time.gmtime
  logging.config.dictConfig(LOG_CONFIG)
  # HTTPConnection.debuglevel = 1

  # Determine the name of the calling module
  calling_module_name = __name__  # Default to 'log' (name of current module)
  try:
    # inspect.stack()[0] is the current frame (init_logging in log.py)
    # inspect.stack()[1] is the frame of the direct caller of init_logging
    caller_frame_info = inspect.stack()[1]
    caller_module = inspect.getmodule(caller_frame_info[0])

    if caller_module:
      # If the caller has a module (e.g., another .py file, or __main__ for a script)
      calling_module_name = caller_module.__name__
    else:
      # If inspect.getmodule returns None (e.g., exec'd code, interactive session <stdin>)
      if caller_frame_info.filename == "<stdin>":
        calling_module_name = "interactive"
      else:
        # Fallback for other module-less contexts
        calling_module_name = "unknown_caller"
  except IndexError:
    # Call stack is too shallow. Defaults to __name__ ('log').
    pass
  except Exception:
    # Any other error during introspection. Defaults to __name__ ('log').
    pass
  logger = logging.getLogger(calling_module_name)
  logger.setLevel(log_level)
  logger.info("Logging level set to: %s", logging.getLevelName(logger.level))

  return logger
